"""Windows Graphics Capture + Media Foundation replay backend.

The native process captures/encodes once. FFmpeg only copies encoded packets
into short closed segments; saving a replay also copies packets without encoding.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

from rocket_league_clips.capture import CREATE_NO_WINDOW, ReplayCaptureBase
from rocket_league_clips.process_job import KillOnCloseJob
from rocket_league_clips.replay_buffer import ReplayBuffer


def native_engine_command() -> list[str]:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        executable = root / "native-capture" / "RocketLeagueCaptureEngine.exe"
        if executable.is_file():
            return [str(executable)]
    root = Path(__file__).resolve().parent.parent
    published = root / "native-capture" / "RocketLeagueCaptureEngine" / "publish" / "RocketLeagueCaptureEngine.exe"
    if published.is_file():
        return [str(published)]
    dotnet = root / "build" / "dotnet-sdk" / "dotnet.exe"
    dll = root / "native-capture" / "RocketLeagueCaptureEngine" / "bin" / "x64" / "Release" / "net10.0" / "RocketLeagueCaptureEngine.dll"
    if dotnet.is_file() and dll.is_file():
        return [str(dotnet), str(dll)]
    raise RuntimeError("The Windows Graphics Capture engine is missing; rebuild the application.")


class NativeCapture(ReplayCaptureBase):
    """Native capture with the existing safe segmented replay retention."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # MP4 demuxing and segment closure trail wall time. Retain enough
        # extra history that the requested interval is still available when
        # its newest segment finally closes.
        self.buffer = ReplayBuffer(self.duration + max(20, 3 * self.segment_seconds))
        self._native = None
        self._started_wall = None
        self._closed_history = deque(maxlen=2000)
        # Allow process initialization as well as a long keyframe occasionally
        # produced by the Media Foundation encoder before declaring a stall.
        self.stall_timeout = 20
        self._preserve_temp = False

    def start(self):
        if self._process is not None or self._native is not None:
            raise RuntimeError("Capture has already started")
        if self.encoder not in ("Automatic", "CPU"):
            raise RuntimeError("The Windows capture engine supports Automatic or CPU encoding; choose one in settings.")
        self._temp = tempfile.TemporaryDirectory(prefix="rocket-league-replay-")
        root = Path(self._temp.name)
        self._csv = root / "segments.csv"
        sizes = {"native": (0, 0), "1920x1080": (1920, 1080), "1280x720": (1280, 720)}
        width, height = sizes[self.resolution]
        bitrate = 28_000_000 if self.quality <= 18 else 20_000_000 if self.quality <= 20 else 10_000_000
        config = {"Fps": self.fps, "Bitrate": bitrate, "Width": width, "Height": height,
                  "HardwareEncoding": self.encoder != "CPU", "Monitor": self.monitor_name,
                  "AudioDevice": self.audio_device_name, "Microphone": self.microphone_name}
        config_path = root / "capture.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        self._job = KillOnCloseJob()
        try:
            self._native = subprocess.Popen(native_engine_command() + [str(config_path)],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
            self._job.assign(self._native)
            args = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-probesize", "32",
                    "-analyzeduration", "0", "-f", "mp4", "-i", "pipe:0",
                    "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-f", "segment",
                    "-segment_format", "matroska", "-segment_time", str(self.segment_seconds),
                    "-reset_timestamps", "1", "-segment_list_flags", "+live",
                    "-segment_list_size", str(max(128, int(self.duration / self.segment_seconds) + 20)),
                    "-segment_list", str(self._csv), str(root / "segment%08d.mkv")]
            self._process = subprocess.Popen(args, stdin=self._native.stdout, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
            self._job.assign(self._process)
            self._native.stdout.close()
            self._threads = [threading.Thread(target=self._native_stderr_loop, daemon=True),
                             threading.Thread(target=self._segments_loop, daemon=True),
                             threading.Thread(target=self._stderr_loop, daemon=True)]
            for thread in self._threads:
                thread.start()
        except Exception:
            self.stop()
            raise

    def _native_stderr_loop(self):
        for raw in iter(self._native.stderr.readline, b""):
            message = raw.decode("utf-8", errors="replace").strip()[:500]
            if message.startswith("CAPTURE_FIRST_FRAME_MS "):
                try:
                    self._started_wall = int(message.split()[-1]) / 1000
                except ValueError:
                    self._errors.append("Native capture returned an invalid start timestamp.")
                    self._stop.set()
            elif message.startswith("Capture failed:"):
                self._errors.append(message)
                self._stop.set()
            with self._changed:
                self._changed.notify_all()

    def _retention_clock(self):
        # Segment timestamps are on the encoded media timeline, which can
        # advance more slowly than wall time under GPU load. Prune relative
        # to the latest encoded segment instead of discarding needed history.
        return self._latest_end

    def _on_segment_closed(self, end):
        # Called while holding _changed. A closed segment only contains data
        # captured before this observation time, unlike a guessed mapping from
        # frame count to wall time when the hardware encoder drops frames.
        self._closed_history.append((time.time(), end))

    def save(self, output: Path, *, timeout=15, requested=None):
        requested = time.time() if requested is None else requested
        with self._changed:
            eligible = [(observed, end) for observed, end in self._closed_history if observed <= requested]
            if not eligible:
                raise RuntimeError("No completed replay segment was available when the shortcut was pressed.")
            observed, media_request = eligible[-1]
            if requested - observed > 5:
                raise RuntimeError("Recording has stopped producing video; the replay was not saved.")
        return super().save(output, timeout=timeout, requested=media_request)

    def begin_recording(self):
        """Reserve subsequent segments without starting a second encoder."""
        with self._changed:
            if self._process is None or self._stop.is_set() or not self._closed_history:
                raise RuntimeError("Recording is still starting. Please try again in a few seconds.")
            observed, start = self._closed_history[-1]
            if time.time() - observed > 5:
                raise RuntimeError("Recording is not producing video.")
            reservation = self.buffer.reserve_from(start)
            self._active_saves += 1
            return reservation, start

    def finish_recording(self, recording, output: Path, timeout=15):
        reservation, start = recording
        succeeded = False
        try:
            deadline = time.monotonic() + timeout
            with self._changed:
                while self._latest_end <= start and not self._stop.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RuntimeError("No video was produced during this recording.")
                    self._changed.wait(remaining)
                end = self._latest_end
            segments = self.buffer.reserved_segments(reservation, end)
            if not segments or any(b.start - a.end > 0.15 for a, b in zip(segments, segments[1:])):
                raise RuntimeError("Recording segments are missing or have a gap.")
            with self._assembly_slots:
                self._assemble(segments, end, Path(output), start_at=start)
            succeeded = True
        except Exception:
            # Keep raw fragments if remuxing fails, including after a capture
            # interruption, so the user's recorded material can be recovered.
            self._preserve_temp = True
            self.buffer.limit(reservation, max(start, self._latest_end))
            raise
        finally:
            if succeeded: self.buffer.release(reservation)
            with self._changed:
                self._active_saves -= 1
                self._changed.notify_all()

    def stop(self):
        # Closing the job kills both children even after crashes. The base
        # class waits for saves before removing their pinned segment files.
        super().stop()
        if self._native:
            try:
                self._native.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._native.kill()
                self._native.wait()
            for stream in (self._native.stdin, self._native.stderr):
                if stream:
                    try: stream.close()
                    except OSError: pass
            self._native = None
