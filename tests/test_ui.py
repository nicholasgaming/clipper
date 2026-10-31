"""UI interaction checks with capture, storage and cloud side effects isolated."""
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QAbstractItemView, QInputDialog, QScrollArea

from rocket_league_clips.ui import SettingsWindow, apply_theme


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    yield app


@pytest.fixture
def window(qt_app, tmp_path):
    controller = Mock()
    controller.settings = {"duration": 30, "fps": 60, "shortcut": "F8", "quality": 20,
                           "microphone": "Saved microphone", "monitor": "Saved display"}
    controller.clips = tmp_path
    controller.recorder = None
    controller.manual_recording = None
    controller.recording_status = "Paused"
    controller.drive_status = "Disconnected"
    controller.drive_folder_name = None
    controller.drive_folder_busy = False
    controller.hotkey_error = None
    controller.last_clip = None
    controller.queue.list.return_value = []
    item = SettingsWindow(controller, {"F8": (), "F9": ()}, lambda: False, Mock())
    item.show()
    qt_app.processEvents()
    yield item
    item.clock.stop()
    item.hide()
    item.deleteLater()
    qt_app.processEvents()


def test_navigation_works_from_sidebar_and_queue_shortcut(window):
    QTest.mouseClick(window.navigation.button(1), Qt.MouseButton.LeftButton)
    assert window.tabs.currentIndex() == 1
    window.tabs.setCurrentIndex(2)
    assert window.navigation.checkedId() == 2


def test_capture_actions_follow_video_availability_and_errors(window):
    assert not window.save_button.isEnabled()
    window.c.recorder = SimpleNamespace(errors=[], failure=None, _closed_history=[])
    window.refresh()
    assert window.status.text() == "Warming up"
    assert not window.record_button.isEnabled()
    window.c.recorder._closed_history.append((time.time(), 2))
    window.refresh()
    QTest.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
    window.c.request_save.assert_called_once()
    window.c.recorder.errors = ["Display disconnected"]
    window.c.recorder.failure = "Display disconnected"
    window.refresh()
    assert not window.save_button.isEnabled()
    assert "Display disconnected" in window.capture_warning.text()


def test_old_capture_warning_does_not_disable_replay_saving(window):
    window.c.recorder = SimpleNamespace(errors=["Old segment warning"], failure=None,
                                        _closed_history=[(time.time(), 30)])
    window.refresh()
    assert window.save_button.isEnabled()
    assert window.status.text() == "Capturing"


def test_settings_keep_saved_offline_devices_and_apply_user_choices(window):
    window.tabs.setCurrentIndex(1)
    window.duration.setCurrentText("60")
    window.shortcut.setCurrentText("F9")
    QTest.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    options = window.c.apply_settings.call_args.args[0]
    assert options["duration"] == 60
    assert options["shortcut"] == "F9"
    assert options["microphone"] == "Saved microphone"
    assert options["monitor"] == "Saved display"


def test_device_discovery_preserves_selection_and_does_not_duplicate(window):
    monitors = [{"name": "Saved display", "width": 1920, "height": 1080}]
    for _ in range(2): window.populate_devices(["Headphones"], ["Saved microphone"], monitors)
    assert window.mic.count() == 2
    assert window.mic.currentData() == "Saved microphone"
    assert window.monitor.count() == 2
    assert window.monitor.currentData() == "Saved display"
    assert "1920" in window.monitor.currentText()


def test_active_recording_can_stop_and_blocks_capture_restart(window):
    window.c.manual_recording = (None, None, time.time() - 65)
    window.refresh()
    assert window.record_button.isEnabled()
    assert window.record_button.text() == "Stop recording"
    assert "01:05" in window.manual_status.text()
    assert not window.pause_button.isEnabled()
    assert not window.apply_button.isEnabled()
    QTest.mouseClick(window.record_button, Qt.MouseButton.LeftButton)
    window.c.toggle_recording.assert_called_once()


def test_upload_activity_is_readonly_and_keeps_selection_on_poll(window):
    window.tabs.setCurrentIndex(2)
    window.c.queue.list.return_value = [
        {"id": "clip-1", "local_path": str(window.c.clips / "highlight.mp4"),
         "state": "completed", "progress": 1, "error": None},
        {"id": "clip-2", "local_path": str(window.c.clips / "second.mp4"),
         "state": "waiting_for_authentication", "progress": 0, "error": "Reconnect Drive"},
    ]
    window.refresh()
    assert not window.empty_uploads.isVisible()
    assert window.table.item(0, 0).text() == "second.mp4"
    assert window.table.item(0, 1).text() == "Sign-in needed"
    assert window.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    window.table.selectRow(1)
    window.refresh()
    assert window.table.currentRow() == 1


def test_switches_support_keyboard_and_persist_preferences(window):
    window.tabs.setCurrentIndex(3)
    window.notifications.setFocus()
    QTest.keyClick(window.notifications, Qt.Key.Key_Space)
    assert window.c.settings["notifications"] is False
    window.c.save_settings.assert_called_once()


def test_compact_recording_settings_keep_apply_visible_while_scrolling(window, qt_app):
    window.resize(880, 650)
    window.tabs.setCurrentIndex(1)
    qt_app.processEvents()
    scroll = window.tabs.widget(1).findChild(QScrollArea)
    assert scroll.verticalScrollBar().maximum() > 0
    before = window.apply_button.mapTo(window, window.apply_button.rect().center())
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    qt_app.processEvents()
    assert window.apply_button.mapTo(window, window.apply_button.rect().center()) == before
    assert window.rect().contains(before)
    assert window.mic.isVisible()


def test_drive_folder_rename_uses_current_folder_and_custom_name(window, monkeypatch):
    window.c.drive_status = "Connected"
    window.c.drive_folder_name = "Old clips"
    window.tabs.setCurrentIndex(2)
    window.refresh()
    assert window.drive_folder_label.text() == "Old clips"
    def choose_name(*args, **kwargs):
        assert kwargs["text"] == "Old clips"
        return "  My best goals  ", True
    monkeypatch.setattr(QInputDialog, "getText", choose_name)
    QTest.mouseClick(window.rename_drive_button, Qt.MouseButton.LeftButton)
    window.c.rename_drive_folder.assert_called_once_with("My best goals")


def test_drive_folder_rename_is_disabled_when_disconnected(window):
    window.tabs.setCurrentIndex(2)
    window.refresh()
    assert not window.rename_drive_button.isEnabled()
