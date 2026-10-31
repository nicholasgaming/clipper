"""Experimental tray UI. See README for validation status and limitations."""
from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import tempfile
import winreg
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QMenu

from rocket_league_clips.ui import SettingsWindow, app_icon, apply_theme
from rocket_league_clips.native_capture import NativeCapture, native_engine_command
from rocket_league_clips.drive import ensure_folder, folder_url, read_settings, upload_and_verify, verify_file, write_settings
from rocket_league_clips.google_auth import AuthError, disconnect, drive_service, get_credentials, verify_drive_access
from rocket_league_clips.hotkey import GlobalHotkey, HotkeyError, MOD_CONTROL, MOD_SHIFT
from rocket_league_clips.single_instance import ActivationEvent, signal_existing
from rocket_league_clips.upload_queue import UploadQueue, UploadWorker
from rocket_league_clips.windows_displays import displays

APP_NAME = "Clipper"
ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RocketLeagueClips"
APP_SETTINGS = ROOT / "app.json"
SHORTCUTS = {"F8": (0x77, 0), "F9": (0x78, 0), "F10": (0x79, 0), "Ctrl+Shift+F8": (0x77, MOD_CONTROL | MOD_SHIFT)}


def clip_folder() -> Path:
    # Keep existing recordings and their queue paths during the rename.
    return Path.home() / "Videos" / "Rocket League Clips"


def set_startup(enabled: bool):
    if getattr(sys, "frozen", False):
        command = subprocess.list2cmdline([sys.executable, "--background"])
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        script = Path(__file__).resolve().parent.parent / "run_app.py"
        command = subprocess.list2cmdline([str(pythonw), str(script), "--background"])
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def audio_devices():
    result = subprocess.run(native_engine_command() + ["--list-devices"], capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=10, check=True)
    devices = json.loads(result.stdout.decode("utf-8"))
    return devices["outputs"], devices["microphones"]


class Bridge(QObject):
    save = Signal()
    message = Signal(str, str, bool)
    recording_error = Signal(str)
    devices = Signal(object, object, object)


def icon(color: str) -> QIcon:
    return app_icon(color)


class Controller(QObject):
    def __init__(self, app, *, open_on_start=True):
        super().__init__()
        self.app = app
        ROOT.mkdir(parents=True, exist_ok=True)
        self.log = logging.getLogger("rocket_league_clips.app")
        if not self.log.handlers:
            handler = RotatingFileHandler(ROOT / "app.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.log.addHandler(handler); self.log.setLevel(logging.INFO); self.log.propagate = False
        self.settings = read_settings(APP_SETTINGS)
        if not self.settings.get("clipper_cleanup_migrated"):
            # The user requested automatic cleanup for new uploads. Existing
            # videos are left for the explicit cleanup button.
            self.settings.update({"clipper_cleanup_migrated": True, "delete_after_upload": True,
                                  "retention_days": 0, "auto_cleanup_since": time.time()})
            write_settings(APP_SETTINGS, self.settings)
        self.clips = Path(self.settings.get("clips_folder") or clip_folder()); self.clips.mkdir(parents=True, exist_ok=True)
        self.queue = UploadQueue(ROOT / "uploads.db"); self.worker = UploadWorker(self.queue)
        self.bridge = Bridge(); self.bridge.save.connect(self.request_save); self.bridge.message.connect(self.notify); self.bridge.recording_error.connect(self.report_error)
        self.recorder = None; self.hotkey = None; self.hotkey_error = None; self.window = None; self.manual_recording = None
        previous = self.queue.list(); self.last_clip = Path(previous[-1]["local_path"]).name if previous else None
        self.recording_status = "Starting"; self.drive_status = "Not checked"; self._save_threads = set(); self._names_lock = threading.Lock(); self._reserved = set(); self._upload_states = None
        self._paused = False; self._retry_at = 0.0; self._restart_attempts = 0; self._upload_notices = {}; self._cleanup_next = 0.0; self._cleanup_lock = threading.Lock()
        self.tray = QSystemTrayIcon(icon("#4ade80"), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        for label, callback in (("Save replay", self.request_save), ("Pause recording", self.pause), ("Resume recording", self.resume), ("Open settings", self.open_settings), ("Open local clips folder", self.open_clips), ("Open Google Drive folder", self.open_drive), ("View upload queue", self.open_queue), ("Test Google Drive connection", self.test_drive), ("Exit", self.exit)):
            action = QAction(label, self); action.triggered.connect(callback); menu.addAction(action)
        self.tray.setContextMenu(menu); self.tray.activated.connect(self.tray_activated); self.tray.show()
        # Recover clips saved just before a crash or queue-write failure.
        for pattern in ("RL_Clip_*.mp4", "Clipper_*.mp4"):
            for path in self.clips.glob(pattern):
                if path.is_file() and not path.name.endswith(".partial.mp4"):
                    self.queue.enqueue(path)
        self.worker.start()
        self.register_hotkey(self.settings.get("shortcut", "F8"))
        self.resume()
        self._check_drive_silently()
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(2000)
        self.notify(APP_NAME, "Clipper is running.", False)
        if open_on_start or not self.settings.get("setup_done") or not self.settings.get("start_minimized", True):
            QTimer.singleShot(0, self.open_settings)

    def save_settings(self):
        write_settings(APP_SETTINGS, self.settings)

    def register_hotkey(self, name):
        old = self.hotkey
        if old: old.stop()
        key, modifiers = SHORTCUTS.get(name, SHORTCUTS["F8"])
        self.hotkey = GlobalHotkey(self.bridge.save.emit, key=key, modifiers=modifiers)
        try: self.hotkey.start(); self.hotkey_error = None
        except HotkeyError as exc:
            self.hotkey = None; self.hotkey_error = str(exc); self.bridge.message.emit("Shortcut unavailable", str(exc), True)
            return False
        return True

    def resume(self, automatic=False):
        self._paused = False
        if self.recorder: return
        if not automatic: self._restart_attempts = 0
        try:
            encoder = self.settings.get("encoder", "Automatic")
            # Earlier builds let users select a vendor. The new Windows media
            # engine chooses an available hardware encoder automatically.
            if encoder in ("NVIDIA NVENC", "AMD AMF", "Intel Quick Sync"):
                encoder = "Automatic"
            self.recorder = NativeCapture(duration=int(self.settings.get("duration", 30)), fps=int(self.settings.get("fps", 60)), audio_device_name=self.settings.get("audio_device"), microphone_name=self.settings.get("microphone"), encoder=encoder, quality=int(self.settings.get("quality", 20)), resolution=self.settings.get("resolution", "native"), monitor_name=self.settings.get("monitor"))
            self.recorder.start(); self.recording_status = "Buffering"; self._restart_attempts = 0
        except Exception as exc:
            if self.recorder: self.recorder.stop()
            self.recorder = None
            self._restart_attempts += 1
            self._retry_at = time.monotonic() + min(60, 5 * (2 ** min(self._restart_attempts - 1, 4)))
            self.recording_status = "Error: Recording could not start: " + str(exc)
            if not automatic: self.notify(APP_NAME, self.recording_status, True)

    def pause(self):
        if self.manual_recording:
            self.notify(APP_NAME, "Stop the video recording before pausing capture.", True)
            return
        self._paused = True
        if self.recorder:
            self.recorder.stop(); self.recorder = None
        self.recording_status = "Paused"

    def apply_settings(self, options):
        if self.manual_recording:
            self.notify(APP_NAME, "Stop the video recording before changing recording settings.", True)
            return
        old_shortcut = self.settings.get("shortcut", "F8")
        if options["shortcut"] != old_shortcut and not self.register_hotkey(options["shortcut"]):
            self.register_hotkey(old_shortcut)
            return
        self.settings.update(options); self.save_settings()
        self.pause(); self.resume()

    def _space_available(self):
        try:
            if shutil.disk_usage(self.clips).free < 1024 ** 3:
                self.notify("Low disk space", "At least 1 GB of free space is required.", True); return False
        except OSError:
            self.notify("Storage unavailable", "The local clips folder cannot be accessed.", True); return False
        return True

    def _reserve_output(self, prefix, timestamp):
        base = datetime.fromtimestamp(timestamp).strftime(prefix + "_%Y-%m-%d_%H-%M-%S")
        with self._names_lock:
            path = self.clips / (base + ".mp4"); suffix = 1
            try:
                while path.exists() or str(path) in self._reserved or self.queue.contains_path(path):
                    path = self.clips / f"{base}_{suffix}.mp4"; suffix += 1
            except Exception:
                # Keep recording even if the queue database is temporarily
                # inaccessible; avoid reusing any historical timestamp name.
                import uuid
                path = self.clips / f"{base}_{uuid.uuid4().hex[:8]}.mp4"
            self._reserved.add(str(path))
        return path

    def request_save(self):
        recorder = self.recorder
        if not recorder:
            self.notify("Replay unavailable", "Recording is paused or unavailable.", True); return
        if not self._space_available(): return
        timestamp = time.time()
        path = self._reserve_output("Clipper_Clip", timestamp)
        def job():
            try:
                recorder.save(path, requested=timestamp)
                self.last_clip = path.name
                try:
                    self.queue.enqueue(path)
                except Exception:
                    self.bridge.message.emit("Clip saved locally", f"{path.name} was saved, but the upload queue is unavailable. It will be recovered on restart.", True)
                else:
                    self.bridge.message.emit("Clip saved", f"Saved {path.name}; upload queued.", False)
            except Exception as exc:
                self.bridge.message.emit("Could not save clip", str(exc), True)
            finally:
                with self._names_lock:
                    self._reserved.discard(str(path)); self._save_threads.discard(threading.current_thread())
        thread = threading.Thread(target=job, name="save-replay", daemon=True)
        with self._names_lock: self._save_threads.add(thread)
        thread.start()

    def toggle_recording(self):
        if self.manual_recording:
            self._finish_manual_recording()
            return
        if not self.recorder or not self._space_available():
            if not self.recorder: self.notify("Recording unavailable", "Resume capture before starting a video.", True)
            return
        try:
            handle = self.recorder.begin_recording()
        except Exception as exc:
            self.notify("Could not start recording", str(exc), True)
            return
        self.manual_recording = (self.recorder, handle, time.time())
        if self.window: self.window.refresh()
        self.notify("Recording started", "Press Stop recording when you are finished.", False)

    def _finish_manual_recording(self, interrupted=False):
        if not self.manual_recording: return
        recorder, handle, started = self.manual_recording
        self.manual_recording = None
        path = self._reserve_output("Clipper_Recording", started)
        if self.window: self.window.refresh()
        def job():
            try:
                recorder.finish_recording(handle, path)
                self.last_clip = path.name
                try:
                    self.queue.enqueue(path)
                except Exception:
                    self.bridge.message.emit("Video saved locally", "Upload queue unavailable; the video will be recovered on restart.", True)
                else:
                    message = "The video was saved and queued for upload."
                    if interrupted: message = "Capture was interrupted; the available video was saved and queued."
                    self.bridge.message.emit("Video saved", message, interrupted)
            except Exception as exc:
                location = recorder._temp.name if recorder._temp else "the temporary recording folder"
                self.bridge.message.emit("Video could not be saved", f"{exc} Recording fragments were kept in {location}.", True)
            finally:
                with self._names_lock:
                    self._reserved.discard(str(path)); self._save_threads.discard(threading.current_thread())
        thread = threading.Thread(target=job, name="save-recording", daemon=True)
        with self._names_lock: self._save_threads.add(thread)
        thread.start()

    def refresh(self):
        rows = self.queue.list(); uploading = any(row["state"] == "uploading" for row in rows)
        errors = any(row["state"] in ("failed", "waiting_for_authentication") for row in rows)
        if self._upload_states is not None:
            for row in rows:
                old = self._upload_states.get(row["id"])
                if old != row["state"]:
                    if row["state"] == "completed":
                        self.notify("Google Drive", "Clip successfully uploaded.", False)
                        self._upload_notices.pop(row["id"], None)
                    elif row["state"] in ("failed", "waiting_for_authentication"):
                        if time.monotonic() - self._upload_notices.get(row["id"], -1e20) >= 300:
                            self.notify("Upload queued", row["error"] or "Upload will be retried.", True)
                            self._upload_notices[row["id"]] = time.monotonic()
        self._upload_states = {row["id"]: row["state"] for row in rows}
        if self.recorder and (self.recorder._stop.is_set() or self.recorder._process.poll() is not None):
            message = self.recorder.errors[-1] if self.recorder.errors else "Capture stopped unexpectedly."
            if self.manual_recording: self._finish_manual_recording(interrupted=True)
            self.recorder.stop(); self.recorder = None
            self.recording_status = "Error: " + message
            self.notify("Recording interrupted", message + " Reconnecting; the replay buffer will refill.", True)
            self._restart_attempts = 1; self._retry_at = time.monotonic() + 1
        if not self._paused and not self.recorder and time.monotonic() >= self._retry_at:
            self.resume(automatic=True)
        if self.manual_recording and self.recorder and self.recorder._temp:
            try:
                low_space = min(shutil.disk_usage(self.clips).free, shutil.disk_usage(self.recorder._temp.name).free) < 1024 ** 3
            except OSError:
                low_space = True
            if low_space:
                self._finish_manual_recording(interrupted=True)
                self.notify("Recording stopped", "Low or unavailable disk space. Saving the available recording.", True)
        if self.settings.get("delete_after_upload", False) and time.monotonic() >= self._cleanup_next:
            self._cleanup_next = time.monotonic() + 60
            self._clean_completed_clips(created_since=float(self.settings.get("auto_cleanup_since", 0)))
        if self.window: self.window.refresh()
        color = "#f87171" if errors or self.hotkey_error or self.recording_status.startswith("Error") else "#60a5fa" if uploading else "#9ca3af" if not self.recorder else "#4ade80"
        self.tray.setIcon(icon(color)); self.tray.setToolTip(APP_NAME + " — " + self.recording_status)

    def notify(self, title, message, error=False):
        if error:
            self.log.error("%s: %s", title, message[:500])
        if self.settings.get("notifications", True) or error:
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Warning if error else QSystemTrayIcon.MessageIcon.Information, 5000)

    def report_error(self, message):
        self.recording_status = "Error: " + message; self.notify(APP_NAME, message, True)

    def open_settings(self):
        if not self.window:
            self.window = SettingsWindow(self, SHORTCUTS, startup_enabled, set_startup)
            self.bridge.devices.connect(self.window.populate_devices)
            def load_devices():
                try: outputs, microphones = audio_devices()
                except Exception: outputs, microphones = [], []
                try: monitors = displays()
                except Exception: monitors = []
                self.bridge.devices.emit(outputs, microphones, monitors)
            threading.Thread(target=load_devices, name="ui-devices", daemon=True).start()
        if not self.settings.get("setup_done"):
            self.window.tabs.setCurrentIndex(3)
            self.settings["setup_done"] = True; self.save_settings()
        self.window.refresh(); self.window.showNormal(); self.window.raise_(); self.window.activateWindow()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick): self.open_settings()

    def open_queue(self):
        self.open_settings(); self.window.tabs.setCurrentIndex(2)

    def open_clips(self): os.startfile(self.clips)

    def open_drive(self):
        import webbrowser
        try:
            folder = read_settings(ROOT / "settings.json").get("drive_folder_id")
            if not folder: self.notify(APP_NAME, "Connect Google Drive to create the destination folder.", True); return
            webbrowser.open(folder_url(folder))
        except Exception: self.notify(APP_NAME, "Could not open the Google Drive folder.", True)

    def retry_uploads(self): self.queue.retry()

    def delete_uploaded_local(self):
        answer = QMessageBox.question(self.window, APP_NAME,
            "Permanently delete local videos that are still verified in Google Drive? Pending, changed or unverified videos will be kept.")
        if answer == QMessageBox.StandardButton.Yes:
            self._clean_completed_clips(created_since=0, interactive=True)

    def _clean_completed_clips(self, *, created_since, interactive=False):
        if not self._cleanup_lock.acquire(blocking=False): return
        def job():
            try:
                service = drive_service(get_credentials(allow_interactive=False))
                folder = ensure_folder(service)
                def verify_remote(row):
                    verify_file(service, row["drive_file_id"], folder, row["file_md5"], row["file_size"])
                    return True
                failures = self.queue.delete_completed_local_files(self.clips, 0, verify_remote=verify_remote, created_since=created_since)
                if failures: self.bridge.message.emit("Local cleanup", "Some uploaded clips could not be removed; they will be retried.", True)
                elif interactive: self.bridge.message.emit("Local cleanup", "Verified uploaded videos were removed from this local folder.", False)
            except Exception:
                self.bridge.message.emit("Local cleanup", "Could not check uploaded clips for cleanup.", True)
            finally:
                self._cleanup_lock.release()
        threading.Thread(target=job, name="clip-retention", daemon=True).start()

    def _check_drive_silently(self):
        def job():
            try:
                service = drive_service(get_credentials(allow_interactive=False))
                verify_drive_access(service)
                self.drive_status = "Connected"
            except Exception:
                self.drive_status = "Offline or authorization needed"
        threading.Thread(target=job, name="google-status", daemon=True).start()

    def test_drive(self):
        def job():
            try:
                service = drive_service(get_credentials()); verify_drive_access(service); ensure_folder(service)
                self.drive_status = "Connected"; self.queue.retry()
                self.bridge.message.emit("Google Drive", "Connection verified.", False)
            except AuthError as exc:
                self.drive_status = "Needs attention"; self.bridge.message.emit("Google Drive", str(exc), True)
            except Exception:
                self.drive_status = "Needs attention"; self.bridge.message.emit("Google Drive", "Connection test failed. Check the network and account authorization.", True)
        threading.Thread(target=job, name="google-connect", daemon=True).start()

    def test_upload(self):
        def job():
            try:
                service = drive_service(get_credentials(allow_interactive=False)); folder = ensure_folder(service)
                with tempfile.TemporaryDirectory(prefix="rlc_upload_test_") as directory:
                    path = Path(directory) / "Rocket League Clips upload test.txt"
                    path.write_text("Rocket League Clips Google Drive upload test.\n", encoding="utf-8")
                    upload_and_verify(service, path, folder, mime_type="text/plain")
                self.bridge.message.emit("Google Drive", "Test file uploaded and verified in the destination folder.", False)
            except AuthError as exc:
                self.bridge.message.emit("Google Drive", str(exc), True)
            except Exception:
                self.bridge.message.emit("Google Drive", "Test upload failed. Check the network and account authorization.", True)
        threading.Thread(target=job, name="google-upload-test", daemon=True).start()

    def disconnect_drive(self):
        def job():
            try:
                disconnect(); self.drive_status = "Disconnected"
                self.bridge.message.emit("Google Drive", "Account disconnected. Uploads will wait for authentication.", False)
            except AuthError as exc:
                self.bridge.message.emit("Google Drive", str(exc), True)
        threading.Thread(target=job, name="google-disconnect", daemon=True).start()

    def exit(self):
        self.timer.stop()
        if self.hotkey: self.hotkey.stop()
        if self.manual_recording: self._finish_manual_recording()
        with self._names_lock: threads = list(self._save_threads)
        if threads: self.notify(APP_NAME, "Finishing clips before exiting.", False)
        for thread in threads: thread.join()
        self.pause(); self.worker.stop()
        for handler in list(self.log.handlers):
            handler.close(); self.log.removeHandler(handler)
        self.tray.hide(); self.app.quit()


def main():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_bool
    mutex = kernel32.CreateMutexW(None, False, "Local\\RocketLeagueClipsSingleton")
    if not mutex: raise OSError("Could not create application instance mutex")
    already_running = ctypes.get_last_error() == 183
    activation = None
    try:
        background = "--background" in sys.argv[1:]
        if already_running:
            if background or signal_existing():
                return 0
            app = QApplication(sys.argv)
            QMessageBox.warning(None, APP_NAME, "The app is already running, but its window could not be opened. Close it from the system tray and start it again.")
            return 1
        # Create the wake-up event before initializing capture, so a second
        # launch during startup can request the window without a race.
        activation = ActivationEvent()
        app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
        apply_theme(app)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, APP_NAME, "A Windows system tray is required.")
            return 1
        controller = Controller(app, open_on_start=not background)
        activation_timer = QTimer(app)
        def check_activation():
            try:
                if activation.requested():
                    controller.open_settings()
            except Exception:
                controller.log.exception("Could not open the app window")
        activation_timer.timeout.connect(check_activation)
        activation_timer.start(200)
        return app.exec()
    finally:
        if activation: activation.close()
        kernel32.CloseHandle(mutex)
