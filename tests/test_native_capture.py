import pytest
import threading
import time
import io
from types import SimpleNamespace
from unittest.mock import patch

from rocket_league_clips.native_capture import NativeCapture
from rocket_league_clips.capture import ReplayCaptureBase
from rocket_league_clips.replay_buffer import Segment


def test_hotkey_uses_only_segments_closed_before_press():
    capture = NativeCapture(duration=30, fps=60, ffmpeg="ffmpeg")
    capture._closed_history.extend([(100.0, 500.0), (112.0, 510.0), (120.0, 520.0)])
    with patch.object(ReplayCaptureBase, "save") as save:
        capture.save("clip.mp4", requested=115.0)
    assert save.call_args.kwargs["requested"] == 510.0


def test_hotkey_rejects_stale_closed_segments():
    capture = NativeCapture(duration=30, fps=60, ffmpeg="ffmpeg")
    capture._closed_history.append((100.0, 500.0))
    with pytest.raises(RuntimeError, match="stopped producing video"):
        capture.save("clip.mp4", requested=110.0)


def test_retention_uses_media_time_not_wall_time():
    capture = NativeCapture(duration=30, fps=60, ffmpeg="ffmpeg")
    capture._latest_end = 123.0
    assert capture._retention_clock() == 123.0


def test_stalled_segment_writer_is_detected(tmp_path):
    capture = NativeCapture(duration=5, fps=30, ffmpeg="ffmpeg")
    capture._process = SimpleNamespace(poll=lambda: None)
    capture._csv = tmp_path / "missing.csv"
    capture.stall_timeout = 0.25
    thread = threading.Thread(target=capture._segments_loop)
    thread.start()
    thread.join(2)
    assert not thread.is_alive()
    assert capture._stop.is_set()
    assert any("stopped producing segments" in message for message in capture.errors)


def test_native_progress_is_recorded_without_exposing_devices_or_media():
    capture = NativeCapture(duration=5, fps=30, ffmpeg="ffmpeg")
    capture._native = SimpleNamespace(stderr=io.BytesIO(b"CAPTURE_PROGRESS 120 45678\nCAPTURE_PROGRESS invalid\n"), poll=lambda: None)
    capture._native_stderr_loop()
    assert capture.diagnostics() == {"native_progress": (120, 45678), "native_exit_code": None,
                                     "segmenter_exit_code": None, "last_segment": -1}
    assert not capture.errors


def test_manual_recording_keeps_all_segments_past_replay_retention(tmp_path):
    capture = NativeCapture(duration=3, fps=30, ffmpeg="ffmpeg")
    capture._process = SimpleNamespace(poll=lambda: None)
    capture._closed_history.append((time.time(), 2.0))
    capture._latest_end = 2.0
    recording = capture.begin_recording()
    paths = []
    for n in range(1, 21):
        path = tmp_path / f"{n}.mkv"; path.write_bytes(b"segment")
        paths.append(path)
        capture.buffer.add_closed(Segment(path, 2 * n, 2 * n + 2))
    capture._latest_end = 42.0
    capture.buffer.cleanup(100)
    assert all(path.exists() for path in paths)
    with patch.object(capture, "_assemble") as assemble:
        capture.finish_recording(recording, tmp_path / "recording.mp4")
    assert [segment.path for segment in assemble.call_args.args[0]] == paths
    assert assemble.call_args.kwargs["start_at"] == 2.0
    assert capture._active_saves == 0
    capture.buffer.cleanup(100)
    assert not any(path.exists() for path in paths)


def test_manual_recording_preserves_fragments_when_assembly_fails(tmp_path):
    capture = NativeCapture(duration=3, fps=30, ffmpeg="ffmpeg")
    capture._process = SimpleNamespace(poll=lambda: None)
    capture._closed_history.append((time.time(), 2.0))
    capture._latest_end = 2.0
    recording = capture.begin_recording()
    path = tmp_path / "segment.mkv"; path.write_bytes(b"segment")
    capture.buffer.add_closed(Segment(path, 2.0, 3.0))
    capture._latest_end = 3.0
    with patch.object(capture, "_assemble", side_effect=OSError("disk full")):
        with pytest.raises(OSError): capture.finish_recording(recording, tmp_path / "video.mp4")
    assert capture._preserve_temp and capture._active_saves == 0
    capture.buffer.cleanup(100)
    assert path.exists()
