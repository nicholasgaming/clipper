"""Non-uploading packaged-build smoke test; output contains no credentials."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from rocket_league_clips.app import audio_devices
from rocket_league_clips.capture import find_ffmpeg
from rocket_league_clips.native_capture import NativeCapture
from rocket_league_clips.google_auth import drive_service, get_credentials, verify_drive_access
from rocket_league_clips.hotkey import GlobalHotkey, MOD_ALT, MOD_CONTROL, MOD_SHIFT


def run(report_path: str) -> int:
    report = {}
    recorder = None
    hotkey = None
    try:
        app = QApplication([])
        report["system_tray"] = QSystemTrayIcon.isSystemTrayAvailable()
        ffmpeg = find_ffmpeg()
        report["capture_engine"] = "Windows Graphics Capture / Media Foundation"
        outputs, microphones = audio_devices()
        report["audio_sources_available"] = bool(outputs)
        report["microphone_sources_available"] = bool(microphones)
        hotkey = GlobalHotkey(lambda: None, key=0x7B, modifiers=MOD_CONTROL | MOD_ALT | MOD_SHIFT)
        hotkey.start(); report["global_hotkey_registration"] = True
        creds_path = os.environ.get("RLC_SELFTEST_CREDENTIALS")
        if creds_path:
            verify_drive_access(drive_service(get_credentials(Path(creds_path), allow_interactive=False)))
            report["google_drive_request"] = True
        recorder = NativeCapture(duration=3, fps=30, ffmpeg=ffmpeg)
        recorder.start(); time.sleep(12)
        with tempfile.TemporaryDirectory(prefix="rlc_packaged_selftest_") as folder:
            clip = Path(folder) / "clip.mp4"
            recorder.save(clip)
            ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe"))
            info = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(clip)], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            metadata = json.loads(info.stdout)
            report["recorded_seconds"] = round(float(metadata["format"]["duration"]), 2)
            report["stream_types"] = sorted(stream["codec_type"] for stream in metadata["streams"])
            report["capture_active_after_save"] = recorder._process.poll() is None
            report["capture_errors"] = recorder.errors
        passed = (report["system_tray"] and report["audio_sources_available"] and report["global_hotkey_registration"]
                  and report["stream_types"] == ["audio", "video"] and 2.8 <= report["recorded_seconds"] <= 3.2
                  and report["capture_active_after_save"] and not report["capture_errors"])
        report["success"] = bool(passed)
        return 0 if passed else 1
    except Exception as exc:
        report["success"] = False
        report["error"] = type(exc).__name__
        return 1
    finally:
        if recorder: recorder.stop()
        if hotkey: hotkey.stop()
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
