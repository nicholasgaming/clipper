"""Closed-segment replay retention and lossless MP4 assembly."""
from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from rocket_league_clips.replay_buffer import ReplayBuffer, Segment

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_ffmpeg() -> str:
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "ffmpeg.exe"
        if bundled.is_file():
            return str(bundled)
    found = shutil.which("ffmpeg")
    if found:
        return found
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    candidates = sorted(root.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"))
    if candidates:
        return str(candidates[-1])
    raise RuntimeError("FFmpeg was not found. Install a Windows build with MP4 and Matroska support.")


class ReplayCaptureBase:
    """Shared retention and replay saving for an encoded capture stream."""

    def __init__(self, duration=30, fps=60, segment_seconds=1, ffmpeg=None, audio_device_name=None, microphone_name=None, encoder="Automatic", quality=20, resolution="native", monitor_name=None):
        if duration <= 0 or fps not in (30, 60) or segment_seconds <= 0 or not 0 <= int(quality) <= 51 or resolution not in ("native", "1920x1080", "1280x720"):
            raise ValueError("Invalid capture settings")
        self.duration = duration
        self.fps = fps
        self.segment_seconds = segment_seconds
        self.stall_timeout = max(8, segment_seconds * 5)
        self.ffmpeg = ffmpeg or find_ffmpeg()
        self.audio_device_name = audio_device_name
        self.microphone_name = microphone_name
        self.encoder = encoder
        self.quality = int(quality)
        self.resolution = resolution
        self.monitor_name = monitor_name
        self.buffer = ReplayBuffer(duration + 3 * segment_seconds)
        self._stop = threading.Event()
        self._changed = threading.Condition()
        self._active_saves = 0
        self._assembly_slots = threading.Semaphore(2)
        self._errors = deque(maxlen=20)
        self._last_segment_number = -1
        self._latest_end = 0.0
        self._started_wall = None
        self._process = None
        self._threads = []
        self._temp = None
        self._job = None
        self._csv_offset = 0

    def _read_segment_rows(self):
        # The segmenter appends complete CSV lines. Only consume complete
        # records, keeping reads bounded even in a multi-day capture session.
        with self._csv.open("rb") as file:
            file.seek(self._csv_offset)
            data = file.read(64 * 1024)
        end = data.rfind(b"\n") + 1
        if not end:
            return []
        rows = list(csv.reader(io.StringIO(data[:end].decode("utf-8"))))
        self._csv_offset += end
        return rows

    def _stderr_loop(self):
        for raw in iter(self._process.stderr.readline, b""):
            message = raw.decode("utf-8", errors="replace").strip()[:500]
            if message:
                self._errors.append(message)

    def _segments_loop(self):
        last_progress = time.monotonic()
        last_cleanup = 0.0
        while not self._stop.wait(0.2):
            if self._process.poll() is not None:
                self._errors.append("Capture process stopped unexpectedly.")
                self._stop.set()
                break
            if time.monotonic() - last_progress > self.stall_timeout:
                self._errors.append("Capture stopped producing segments; recording will restart.")
                self._stop.set()
                break
            try:
                if not self._csv.exists():
                    continue
                if self._started_wall is None:
                    continue
                rows = self._read_segment_rows()
                for row in rows:
                    if len(row) != 3:
                        continue
                    path = Path(self._temp.name) / Path(row[0]).name
                    if not path.stem.startswith("segment") or not path.stem[7:].isdigit():
                        continue
                    number = int(path.stem[7:])
                    if number <= self._last_segment_number:
                        continue
                    start, end = float(row[1]), float(row[2])
                    # FFmpeg timestamps are relative to capture startup.
                    start += self._started_wall
                    end += self._started_wall
                    self.buffer.add_closed(Segment(path, start, end))
                    self._last_segment_number = number
                    last_progress = time.monotonic()
                    with self._changed:
                        self._latest_end = end
                        self._on_segment_closed(end)
                        self._changed.notify_all()
                if time.monotonic() - last_cleanup >= 2:
                    for failed in self.buffer.cleanup(self._retention_clock()):
                        self._errors.append("Could not remove old replay segment: " + failed.name)
                    last_cleanup = time.monotonic()
            except (OSError, ValueError, csv.Error) as exc:
                self._errors.append("Could not update replay segments: " + type(exc).__name__)
        with self._changed:
            self._changed.notify_all()

    def _retention_clock(self):
        return time.time()

    def _on_segment_closed(self, end):
        pass

    def save(self, output: Path, *, timeout=12, requested=None):
        """Save synchronously; callers must run this off the GUI thread."""
        with self._changed:
            if self._process is None or self._stop.is_set():
                raise RuntimeError("Recording is not running.")
            self._active_saves += 1
        try:
            self._save_requested(output, timeout=timeout, requested=requested)
        finally:
            with self._changed:
                self._active_saves -= 1
                self._changed.notify_all()

    def _save_requested(self, output: Path, *, timeout: float, requested=None):
        requested = time.time() if requested is None else requested
        deadline = time.monotonic() + timeout
        # Pin the old end of the requested interval while waiting for the
        # currently open segment to close, then pin the complete selection.
        with self.buffer.snapshot(requested):
            with self._changed:
                while self._latest_end < requested and not self._stop.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("Timed out waiting for a closed replay segment.")
                    self._changed.wait(remaining)
            if self._stop.is_set():
                raise RuntimeError("Recording stopped before the replay could be saved.")
            with self.buffer.snapshot(requested) as segments:
                selected = [s for s in segments if s.end > requested - self.duration and s.start < requested]
                if not selected:
                    raise RuntimeError("No completed recording segments are available yet.")
                if selected[0].start > requested - self.duration + 0.1:
                    raise RuntimeError("The replay buffer is still filling; wait until the full replay duration is available.")
                if any(b.start - a.end > 0.15 for a, b in zip(selected, selected[1:])):
                    raise RuntimeError("A gap was detected in the replay buffer; the clip was not saved.")
                with self._assembly_slots:
                    self._assemble(selected, requested, Path(output))

    def _assemble(self, segments, requested, output, *, start_at=None):
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            raise FileExistsError(output)
        first = segments[0].start
        start = max(first, requested - self.duration if start_at is None else start_at)
        duration = requested - start
        if duration <= 0:
            raise RuntimeError("The replay contains no recorded time.")
        # Write a temporary manifest beside the private segment files.
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".ffconcat", dir=self._temp.name, delete=False) as manifest:
            for segment in segments:
                value = str(segment.path).replace("\\", "/").replace("'", "'\\''")
                manifest.write("file '" + value + "'\n")
                manifest.write("duration " + str(segment.end - segment.start) + "\n")
            manifest_path = Path(manifest.name)
        partial = output.with_name(output.stem + "." + uuid.uuid4().hex + ".partial.mp4")
        try:
            if partial.exists():
                raise FileExistsError(partial)
            # The rolling segments are already encoded. Copy their video and
            # audio packets into MP4 instead of decoding and re-encoding the
            # entire replay on the CPU while the game is running. Input seek
            # may keep up to one GOP of preroll for the MP4 edit list.
            args = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(max(0, start - first)),
                    "-f", "concat", "-safe", "0", "-i", str(manifest_path), "-t", str(duration),
                    "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-movflags", "+faststart", "-n", str(partial)]
            flags = CREATE_NO_WINDOW | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags, timeout=max(60, duration * 4))
            if result.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
                raise RuntimeError("FFmpeg could not assemble the replay: " + result.stderr.decode("utf-8", errors="replace")[-500:])
            os.rename(partial, output)
        finally:
            manifest_path.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)

    def stop(self):
        with self._changed:
            self._stop.set()
            self._changed.notify_all()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        if self._job:
            self._job.close()
            self._job = None
        for thread in self._threads:
            thread.join(timeout=3)
        if self._temp:
            with self._changed:
                active = self._active_saves
            if active:
                threading.Thread(target=self._cleanup_after_saves, daemon=True).start()
            else:
                self._dispose_temp()
                self._temp = None

    def _cleanup_after_saves(self):
        with self._changed:
            self._changed.wait_for(lambda: self._active_saves == 0)
            if self._temp:
                self._dispose_temp()
                self._temp = None

    def _dispose_temp(self):
        if getattr(self, "_preserve_temp", False):
            self._temp._finalizer.detach()
        else:
            self._temp.cleanup()

    @property
    def errors(self):
        return list(self._errors)

    @property
    def failure(self):
        if self._stop.is_set() or (self._process is not None and self._process.poll() is not None):
            return self._errors[-1] if self._errors else "Capture stopped unexpectedly."
        return None
