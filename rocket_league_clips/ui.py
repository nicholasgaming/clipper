"""Clipper's native desktop interface and shared visual language."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QInputDialog,
    QFrame, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPushButton,
    QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)


STYLE = """
QWidget { color: #1d1d1f; font-family: 'Segoe UI'; font-size: 13px; }
QDialog, QStackedWidget, QScrollArea, QWidget#Page { background: #f5f5f7; }
QFrame#Sidebar { background: #ebedf0; border-right: 1px solid #dcdfe4; }
QLabel { background: transparent; border: none; }
QLabel#Brand { font-size: 22px; font-weight: 700; letter-spacing: -0.7px; }
QLabel#Eyebrow { color: #777c85; font-size: 10px; font-weight: 600; letter-spacing: 1.3px; }
QLabel#PageTitle { font-size: 29px; font-weight: 700; letter-spacing: -0.8px; }
QLabel#Subtitle { color: #72757d; font-size: 13px; }
QLabel#SectionTitle { font-size: 14px; font-weight: 600; }
QLabel#Detail { color: #737780; font-size: 12px; }
QLabel#Metric { font-size: 20px; font-weight: 600; letter-spacing: -0.4px; }
QLabel#ReplayNumber { font-size: 68px; font-weight: 600; letter-spacing: -3px; }
QLabel#ReplayUnit { color: #777c85; font-size: 19px; padding-bottom: 13px; }
QLabel#HeroTitle { font-size: 19px; font-weight: 600; letter-spacing: -0.4px; }
QLabel#Keycap { background: #f2f3f6; border: 1px solid #e0e2e6; border-radius: 5px;
    padding: 4px 9px; color: #555b66; font-size: 11px; font-weight: 600; }
QLabel#Status { font-size: 11px; font-weight: 600; border-radius: 10px; padding: 4px 10px; }
QLabel#Status[tone="green"] { color: #267447; background: #edf6ef; }
QLabel#Status[tone="neutral"] { color: #67707d; background: #eef0f4; }
QLabel#Status[tone="red"] { color: #bf3e3e; background: #fff0ef; }
QLabel#Status[tone="blue"] { color: #0069d9; background: #edf4ff; }
QFrame#Card { background: white; border: 1px solid #e2e4e9; border-radius: 13px; }
QFrame#Separator { background: #eceef1; border: none; max-height: 1px; }
QPushButton { background: #fff; border: 1px solid #d9dce2; border-radius: 7px;
    padding: 8px 15px; font-weight: 500; min-height: 17px; }
QPushButton:hover { background: #f6f7fa; border-color: #bfc4cd; }
QPushButton:pressed { background: #e9edf3; }
QPushButton:focus-visible { border: 1px solid #007aff; }
QPushButton:disabled { color: #a4a8b1; background: #f2f3f6; border-color: #e6e8ec; }
QPushButton#Primary { background: #007aff; color: white; border: 1px solid #007aff; font-weight: 600; }
QPushButton#Primary:hover { background: #006bea; border-color: #006bea; }
QPushButton#Primary:pressed { background: #005dce; }
QPushButton#Primary:disabled { background: #c9def8; border-color: #c9def8; color: #fff; }
QPushButton#RecordActive { color: #c63e40; background: #fff1f1; border-color: #f4cfd0; }
QPushButton#Danger { color: #c43e40; }
QPushButton#Link { color: #0074e8; background: transparent; border: none; padding: 3px 0; text-align: left; }
QPushButton#Link:hover { color: #0056b8; }
QPushButton#Nav { background: transparent; border: none; text-align: left; padding: 10px 14px;
    border-radius: 7px; color: #5a606b; font-weight: 500; }
QPushButton#Nav:hover { background: #e2e5eb; }
QPushButton#Nav:checked { color: #0768d3; background: #dce7f7; font-weight: 600; }
QPushButton#SidebarAction { background: transparent; border: none; text-align: left;
    color: #626875; padding: 7px 12px; }
QPushButton#SidebarAction:hover { background: #e1e4e9; }
QPushButton#More { padding: 8px; }
QPushButton#More::menu-indicator { image: none; width: 0; }
QComboBox { background: #f6f7f9; border: 1px solid #dfe2e8; border-radius: 6px;
    padding: 7px 30px 7px 11px; min-height: 17px; selection-background-color: #007aff; }
QComboBox:hover { border-color: #b9c0cb; }
QComboBox:focus { border-color: #007aff; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView { background: white; color: #1d1d1f; border: 1px solid #dfe2e8;
    selection-background-color: #e5efff; selection-color: #0069d9; padding: 4px; outline: 0; }
QScrollArea { border: none; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 6px 1px; }
QScrollBar::handle:vertical { background: #cdd1d8; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTableWidget { background: white; border: none; gridline-color: #eceef2;
    selection-background-color: #edf4ff; selection-color: #1d1d1f; outline: 0; }
QTableWidget::item { padding: 10px 12px; border-bottom: 1px solid #eff0f3; }
QHeaderView::section { background: #f8f9fb; color: #7b808a; border: none;
    border-bottom: 1px solid #e8ebf0; padding: 9px 12px; font-size: 11px; font-weight: 600; text-align: left; }
QMenu { background: #fff; border: 1px solid #dcdfe5; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 20px; border-radius: 4px; }
QMenu::item:selected { background: #e6f0ff; color: #0069d9; }
QToolTip { background: #fff; color: #444953; border: 1px solid #dfe2e7; padding: 6px; }
QMessageBox { background: #f5f5f7; }
"""


def apply_theme(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())


def glyph(name, color="#6b7482", size=20):
    """Small vector-drawn icons that stay sharp at Windows display scaling."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(2)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name in ("capture", "brand"):
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 4, 4)
        path = QPainterPath(QPointF(10, 8.5))
        path.lineTo(15, 12); path.lineTo(10, 15.5); path.closeSubpath()
        p.setBrush(QColor(color)); p.drawPath(path)
    elif name == "record":
        p.drawEllipse(QRectF(3, 3, 18, 18))
        p.setBrush(QColor(color)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(8, 8, 8, 8))
    elif name == "settings":
        for x, y in ((5, 8), (12, 16), (19, 10)):
            p.drawLine(QPointF(x, 4), QPointF(x, y - 3))
            p.drawLine(QPointF(x, y + 3), QPointF(x, 20))
            p.drawRoundedRect(QRectF(x - 2.5, y - 2.5, 5, 5), 1.5, 1.5)
    elif name == "cloud":
        path = QPainterPath(QPointF(7, 18))
        path.cubicTo(0, 18, 1, 9, 7, 10)
        path.cubicTo(8, 2, 19, 3, 19, 11)
        path.cubicTo(25, 12, 22, 18, 18, 18)
        path.closeSubpath(); p.drawPath(path)
    elif name == "folder":
        path = QPainterPath(QPointF(3, 7))
        path.lineTo(3, 19); path.lineTo(21, 19); path.lineTo(21, 7)
        path.lineTo(11, 7); path.lineTo(9, 4); path.lineTo(3, 4); path.closeSubpath()
        p.drawPath(path)
    elif name == "download":
        p.drawLine(12, 3, 12, 14); p.drawLine(8, 10, 12, 14); p.drawLine(12, 14, 16, 10)
        p.drawLine(5, 15, 5, 20); p.drawLine(5, 20, 19, 20); p.drawLine(19, 20, 19, 15)
    elif name == "pause":
        p.drawLine(9, 5, 9, 19); p.drawLine(15, 5, 15, 19)
    elif name == "play":
        path = QPainterPath(QPointF(8, 5)); path.lineTo(19, 12); path.lineTo(8, 19)
        path.closeSubpath(); p.drawPath(path)
    elif name == "stop":
        p.setBrush(QColor(color)); p.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    elif name == "storage":
        p.drawRoundedRect(QRectF(3, 5, 18, 14), 3, 3)
        p.drawLine(4, 14, 20, 14); p.drawPoint(17, 17)
    elif name == "dots":
        p.setBrush(QColor(color)); p.setPen(Qt.PenStyle.NoPen)
        for x in (5, 12, 19): p.drawEllipse(QPointF(x, 12), 1.6, 1.6)
    p.end()
    return QIcon(pixmap)


def app_icon(color="#007aff"):
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color)); p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(4, 4, 120, 120), 29, 29)
    glyph("capture", "#ffffff", 84).paint(p, 22, 22, 84, 84)
    p.end()
    return QIcon(pixmap)


def label(text="", role=None, wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if role: item.setObjectName(role)
    item.setWordWrap(wrap)
    return item


def button(text, callback=None, role=None, symbol=None):
    item = QPushButton(text)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.setAutoDefault(False)
    if role: item.setObjectName(role)
    if symbol: item.setIcon(glyph(symbol, "#ffffff" if role == "Primary" else "#6b7482"))
    if callback: item.clicked.connect(callback)
    return item


def card(padding=22):
    frame = QFrame(); frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(13)
    return frame, layout


def separator():
    line = QFrame(); line.setObjectName("Separator"); line.setFixedHeight(1)
    return line


class Switch(QCheckBox):
    """A checkbox with a compact switch appearance and keyboard accessibility."""
    def __init__(self, name, checked=False):
        super().__init__()
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setChecked(checked)
        self.setFixedSize(38, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#007aff" if self.isChecked() else "#cbd0d8"))
        p.drawRoundedRect(QRectF(1, 3, 36, 21), 10.5, 10.5)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(19 if self.isChecked() else 3, 5, 17, 17))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor("#80baff"), 1))
            p.drawRoundedRect(QRectF(0.5, 1, 37, 24), 12, 12)


class SettingsCombo(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#78818e"), 1.5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        x, y = self.width() - 18, self.height() / 2
        path = QPainterPath(QPointF(x - 3, y - 1.5))
        path.lineTo(x, y + 1.5); path.lineTo(x + 3, y - 1.5)
        p.drawPath(path)


class SettingsWindow(QDialog):
    def __init__(self, controller, shortcuts, startup_read, startup_write):
        super().__init__()
        self.c = controller
        self._startup_write = startup_write
        self._queue_snapshot = None
        self.setWindowTitle("Clipper")
        self.setWindowIcon(app_icon())
        self.resize(1040, 790)
        self.setMinimumSize(880, 650)
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        sidebar = QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(206)
        side = QVBoxLayout(sidebar); side.setContentsMargins(16, 30, 16, 18); side.setSpacing(5)
        brand = QHBoxLayout(); brand.setContentsMargins(10, 0, 0, 0); brand.setSpacing(11)
        mark = QLabel(); mark.setPixmap(app_icon().pixmap(36, 36))
        brand.addWidget(mark); brand.addWidget(label("Clipper", "Brand")); brand.addStretch()
        side.addLayout(brand); side.addSpacing(36)
        eyebrow = label("WORKSPACE", "Eyebrow"); eyebrow.setContentsMargins(14, 0, 0, 8)
        side.addWidget(eyebrow)
        self.tabs = QStackedWidget()
        self.navigation = QButtonGroup(self)
        for index, (text, symbol) in enumerate((("Capture", "capture"), ("Recording", "record"),
                                               ("Google Drive", "cloud"), ("General", "settings"))):
            nav = button(text, role="Nav", symbol=symbol)
            nav.setCheckable(True); nav.setIconSize(QSize(19, 19))
            self.navigation.addButton(nav, index); side.addWidget(nav)
        self.navigation.idClicked.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(lambda i: self.navigation.button(i).setChecked(True))
        side.addStretch()
        side.addWidget(button("Local clips", self.c.open_clips, "SidebarAction", "folder"))
        side.addSpacing(12); side.addWidget(separator()); side.addSpacing(12)
        build = label("EXPERIMENTAL BUILD", "Eyebrow"); build.setContentsMargins(12, 0, 0, 0)
        side.addWidget(build)
        hint = label("Made for the moments\nworth keeping.", "Detail"); hint.setContentsMargins(12, 5, 0, 0)
        side.addWidget(hint)
        root.addWidget(sidebar); root.addWidget(self.tabs, 1)

        self._build_capture()
        self._build_recording(shortcuts)
        self._build_drive()
        self._build_general(startup_read)
        self.navigation.button(0).setChecked(True)
        self.clock = QTimer(self); self.clock.setInterval(1000)
        self.clock.timeout.connect(self._update_recording_clock); self.clock.start()
        self.refresh()

    def _page(self, title, subtitle):
        page = QWidget(); page.setObjectName("Page")
        layout = QVBoxLayout(page); layout.setContentsMargins(34, 29, 34, 24); layout.setSpacing(18)
        heading = QVBoxLayout(); heading.setSpacing(6)
        heading.addWidget(label(title, "PageTitle"))
        heading.addWidget(label(subtitle, "Subtitle", True)); layout.addLayout(heading); layout.addSpacing(3)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        outer = QVBoxLayout(container); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        outer.addWidget(scroll)
        self.tabs.addWidget(container)
        return layout

    def _setting(self, layout, title, subtitle, control, *, first=False):
        if not first: layout.addWidget(separator())
        row = QHBoxLayout(); row.setSpacing(20)
        copy = QVBoxLayout(); copy.setSpacing(4)
        title_label = label(title); title_label.setBuddy(control); copy.addWidget(title_label)
        if subtitle: copy.addWidget(label(subtitle, "Detail", True))
        row.addLayout(copy, 1); row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(row)

    def _combo(self, name):
        combo = SettingsCombo(); combo.setAccessibleName(name); combo.setFixedWidth(222)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        return combo

    def _build_capture(self):
        page = self._page("Capture", "A great moment deserves a second look.")
        hero, content = card(25)
        top = QHBoxLayout(); top.addWidget(label("INSTANT REPLAY", "Eyebrow")); top.addStretch()
        self.status = label(role="Status"); top.addWidget(self.status); content.addLayout(top)
        number = QHBoxLayout(); number.setSpacing(10)
        self.replay_duration = label(role="ReplayNumber")
        number.addWidget(self.replay_duration); number.addWidget(label("seconds", "ReplayUnit"), 0, Qt.AlignmentFlag.AlignBottom)
        number.addStretch(); content.addLayout(number)
        content.addWidget(label("Save what just happened.", "HeroTitle"))
        self.capture_description = label("Keep the last moments of your screen with a single keystroke.", "Subtitle", True)
        content.addWidget(self.capture_description); content.addSpacing(7)
        actions = QHBoxLayout(); actions.setSpacing(10)
        self.save_button = button("Save replay", self.c.request_save, "Primary", "download")
        self.save_button.setMinimumWidth(145); actions.addWidget(self.save_button)
        self.shortcut_key = label(role="Keycap"); actions.addWidget(self.shortcut_key)
        actions.addStretch()
        self.pause_button = button("Pause", self.toggle_capture, "Link")
        actions.addWidget(self.pause_button); content.addLayout(actions)
        self.capture_warning = label(role="Detail", wrap=True); content.addWidget(self.capture_warning)
        page.addWidget(hero)

        manual, manual_layout = card(20)
        row = QHBoxLayout(); row.setSpacing(14)
        mark = QLabel(); mark.setPixmap(glyph("record", "#eb6967", 30).pixmap(30, 30)); row.addWidget(mark)
        copy = QVBoxLayout(); copy.setSpacing(5)
        copy.addWidget(label("Stay in the moment", "SectionTitle"))
        self.manual_status = label(role="Detail", wrap=True); copy.addWidget(self.manual_status)
        row.addLayout(copy, 1)
        self.record_button = button("Start recording", self.c.toggle_recording)
        row.addWidget(self.record_button); manual_layout.addLayout(row); page.addWidget(manual)

        metrics = QHBoxLayout(); metrics.setSpacing(16)
        drive, drive_layout = card(20); drive_layout.addWidget(label("GOOGLE DRIVE", "Eyebrow"))
        self.drive_status = label(role="Metric", wrap=True); drive_layout.addWidget(self.drive_status)
        self.pending = label(role="Detail"); drive_layout.addWidget(self.pending)
        drive_layout.addWidget(button("View uploads  →", lambda: self.tabs.setCurrentIndex(2), "Link"))
        metrics.addWidget(drive, 1)
        storage, storage_layout = card(20); storage_layout.addWidget(label("LOCAL STORAGE", "Eyebrow"))
        self.space = label(role="Metric"); storage_layout.addWidget(self.space)
        storage_layout.addWidget(label("Available for your next clip", "Detail"))
        storage_layout.addWidget(button("Open clips folder  →", self.c.open_clips, "Link")); metrics.addWidget(storage, 1)
        page.addLayout(metrics)
        self.last = label(role="Detail", wrap=True); page.addWidget(self.last)
        page.addStretch()

    def _build_recording(self, shortcuts):
        page = self._page("Recording", "Your screen. Your sound. Just the way you like it.")
        self.duration = self._combo("Replay duration"); self.duration.addItems(["15", "30", "60", "120"])
        self.duration.setCurrentText(str(self.c.settings.get("duration", 30)))
        self.fps = self._combo("Frame rate"); self.fps.addItems(["30", "60"])
        self.fps.setCurrentText(str(self.c.settings.get("fps", 60)))
        self.resolution = self._combo("Resolution")
        for title, value in (("Match display", "native"), ("1920 × 1080", "1920x1080"), ("1280 × 720", "1280x720")):
            self.resolution.addItem(title, value)
        self.monitor = self._combo("Display"); self.monitor.addItem("Primary display", None)
        self.audio = self._combo("System audio"); self.audio.addItem("Windows default", None)
        self.mic = self._combo("Microphone"); self.mic.addItem("Off", None)
        self.shortcut = self._combo("Save shortcut"); self.shortcut.addItems(list(shortcuts))
        self.shortcut.setCurrentText(self.c.settings.get("shortcut", "F8"))
        self.encoder = self._combo("Encoder"); self.encoder.addItems(["Automatic", "CPU"])
        self.encoder.setCurrentText(self.c.settings.get("encoder", "Automatic"))
        self.quality = self._combo("Quality")
        for title, value in (("High", 18), ("Balanced", 20), ("Smaller files", 26)): self.quality.addItem(title, value)
        # Device enumeration is deferred until after the first paint.
        for widget, key, default in ((self.resolution, "resolution", "native"), (self.quality, "quality", 20)):
            index = widget.findData(self.c.settings.get(key, default))
            if index >= 0: widget.setCurrentIndex(index)
        for widget, key in ((self.monitor, "monitor"), (self.audio, "audio_device"), (self.mic, "microphone")):
            value = self.c.settings.get(key)
            if value:
                widget.addItem(value, value); widget.setCurrentIndex(widget.count() - 1)
        page.addWidget(label("REPLAY", "Eyebrow"))
        replay, content = card(19)
        self._setting(content, "Replay length", "Seconds to keep when you save a replay.", self.duration, first=True)
        self._setting(content, "Save shortcut", "Works while Clipper is in the system tray.", self.shortcut)
        page.addWidget(replay)
        page.addWidget(label("VIDEO", "Eyebrow"))
        video, content = card(19)
        for i, (title, subtitle, control) in enumerate((("Display", "Choose the screen to capture.", self.monitor),
            ("Resolution", "The size of your saved video.", self.resolution), ("Frame rate", "Frames per second.", self.fps),
            ("Quality", "Balance detail and file size.", self.quality),
            ("Encoder", "Automatic uses available hardware encoding.", self.encoder))):
            self._setting(content, title, subtitle, control, first=i == 0)
        page.addWidget(video)
        page.addWidget(label("AUDIO", "Eyebrow"))
        audio, content = card(19)
        self._setting(content, "System audio", "Sound from your selected playback device.", self.audio, first=True)
        self._setting(content, "Microphone", "Add your voice to your clips.", self.mic); page.addWidget(audio)
        self.shortcut_warning = label(wrap=True); self.shortcut_warning.setStyleSheet("color: #c43e40;")
        footer = QWidget()
        actions = QHBoxLayout(footer); actions.setContentsMargins(34, 17, 34, 20); actions.setSpacing(18)
        copy = QVBoxLayout(); copy.setSpacing(4)
        copy.addWidget(label("Changes restart capture and refill the replay buffer.", "Detail", True))
        copy.addWidget(self.shortcut_warning); actions.addLayout(copy, 1)
        self.apply_button = button("Apply changes", self.apply, "Primary"); actions.addWidget(self.apply_button)
        outer = self.tabs.widget(1).layout()
        outer.addWidget(separator()); outer.addWidget(footer)
        page.addStretch()

    def populate_devices(self, outputs, microphones, monitors):
        """Populate on the UI thread; retain the user's saved device if offline."""
        for widget, entries in ((self.audio, [(name, name) for name in outputs]),
                                (self.mic, [(name, name) for name in microphones]),
                                (self.monitor, [(f"{m['name']} · {m['width']} × {m['height']}", m['name']) for m in monitors])):
            for title, value in entries:
                index = widget.findData(value)
                if index < 0: widget.addItem(title, value)
                else: widget.setItemText(index, title)

    def _build_drive(self):
        page = self._page("Google Drive", "Your highlights, ready wherever you are.")
        account, content = card(22)
        row = QHBoxLayout(); row.setSpacing(14)
        mark = QLabel(); mark.setPixmap(glyph("cloud", "#007aff", 32).pixmap(32, 32)); row.addWidget(mark)
        copy = QVBoxLayout(); copy.setSpacing(5); copy.addWidget(label("Keep your clips in sync", "SectionTitle"))
        self.account_status = label(role="Detail", wrap=True); copy.addWidget(self.account_status); row.addLayout(copy, 1)
        self.connect_button = button("Connect Drive", self.c.test_drive, "Primary"); row.addWidget(self.connect_button)
        content.addLayout(row); content.addWidget(separator())
        row = QHBoxLayout(); row.addWidget(label("Clips upload to your private app folder.", "Detail", True)); row.addStretch()
        row.addWidget(button("Open folder  →", self.c.open_drive, "Link")); content.addLayout(row); page.addWidget(account)

        destination, content = card(20)
        self.drive_folder_label = label(role="Detail", wrap=True)
        row = QHBoxLayout(); row.setSpacing(16)
        copy = QVBoxLayout(); copy.setSpacing(5)
        copy.addWidget(label("Drive folder name", "SectionTitle")); copy.addWidget(self.drive_folder_label)
        row.addLayout(copy, 1)
        self.rename_drive_button = button("Rename…", self.choose_drive_name)
        self.rename_drive_button.setToolTip("Rename the folder where Clipper uploads videos")
        row.addWidget(self.rename_drive_button); content.addLayout(row); page.addWidget(destination)

        heading = QHBoxLayout(); heading.addWidget(label("UPLOAD ACTIVITY", "Eyebrow")); heading.addStretch()
        heading.addWidget(button("Retry uploads", self.c.retry_uploads, "Link"))
        more = button("", role="More", symbol="dots")
        more.setAccessibleName("More Google Drive actions"); more.setToolTip("More actions"); more.setFixedWidth(37)
        menu = QMenu(more)
        for title, callback in (("Upload a test file", self.c.test_upload), ("Disconnect account", self.c.disconnect_drive)):
            menu.addAction(title, callback)
        more.setMenu(menu); heading.addWidget(more); page.addLayout(heading)
        activity, activity_layout = card(0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["File", "Status", "Progress", "Details"])
        self.table.setShowGrid(False); self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False); self.table.setMinimumHeight(220)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(44)
        activity_layout.addWidget(self.table)
        self.empty_uploads = QWidget()
        empty = QVBoxLayout(self.empty_uploads); empty.setContentsMargins(24, 48, 24, 48); empty.setSpacing(10)
        cloud = QLabel(); cloud.setPixmap(glyph("cloud", "#aab3c1", 38).pixmap(38, 38)); cloud.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.addWidget(cloud)
        for text, role in (("A home for your highlights", "SectionTitle"),
                           ("Save a replay and its upload will appear here.", "Detail")):
            copy = label(text, role, True); copy.setAlignment(Qt.AlignmentFlag.AlignCenter); empty.addWidget(copy)
        activity_layout.addWidget(self.empty_uploads); page.addWidget(activity)
        cleanup, content = card(20)
        self._setting(content, "Free up local space", "Remove local videos already verified in Drive.",
                      button("Clean up…", self.c.delete_uploaded_local), first=True)
        page.addWidget(cleanup); page.addStretch()

    def _build_general(self, startup_read):
        page = self._page("General", "Small preferences. A smoother everyday.")
        page.addWidget(label("EVERYDAY", "Eyebrow"))
        everyday, content = card(20)
        self.startup = Switch("Launch at sign-in", startup_read()); self.startup.toggled.connect(self.change_startup)
        self.minimized = Switch("Start in the system tray", self.c.settings.get("start_minimized", True))
        self.minimized.toggled.connect(self.change_minimized)
        self.notifications = Switch("Show notifications", self.c.settings.get("notifications", True))
        self.notifications.toggled.connect(self.change_notifications)
        for i, (title, subtitle, control) in enumerate((("Launch at sign-in", "Ready to capture when Windows starts.", self.startup),
            ("Start in the system tray", "Keep Clipper quietly in the background.", self.minimized),
            ("Notifications", "Know when a clip is saved or uploaded.", self.notifications))):
            self._setting(content, title, subtitle, control, first=i == 0)
        page.addWidget(everyday)
        page.addWidget(label("STORAGE", "Eyebrow"))
        storage, content = card(20)
        row = QHBoxLayout(); row.addWidget(label("Clips folder", "SectionTitle")); row.addStretch()
        row.addWidget(button("Change…", self.choose_folder)); content.addLayout(row)
        self.clip_path = label(str(self.c.clips), "Detail", True)
        self.clip_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); content.addWidget(self.clip_path)
        self.delete_local = Switch("Delete local videos after upload", self.c.settings.get("delete_after_upload", False))
        self.delete_local.toggled.connect(self.change_retention)
        self._setting(content, "Free up space automatically", "Delete new local videos after a verified upload.", self.delete_local)
        page.addWidget(storage)
        page.addWidget(label("Pending, changed or unverified videos are always kept.", "Detail", True))
        page.addSpacing(6)
        about, content = card(20)
        content.addWidget(label("A note about this build", "SectionTitle"))
        content.addWidget(label("Clipper is experimental. Recording boundaries are approximate and the final seconds may be missing. Review important recordings before relying on them.", "Detail", True))
        page.addWidget(about); page.addStretch()

    def closeEvent(self, event):
        event.ignore(); self.hide()

    def toggle_capture(self):
        if self.c.recorder: self.c.pause()
        else: self.c.resume()
        self.refresh()

    def change_startup(self, checked):
        try:
            self._startup_write(checked)
            self.c.settings["startup"] = checked; self.c.save_settings()
        except OSError:
            self.startup.blockSignals(True); self.startup.setChecked(not checked); self.startup.blockSignals(False)
            QMessageBox.warning(self, "Clipper", "Windows startup could not be changed for this account.")

    def change_notifications(self, checked):
        self.c.settings["notifications"] = checked; self.c.save_settings()

    def change_minimized(self, checked):
        self.c.settings["start_minimized"] = checked; self.c.save_settings()

    def change_retention(self, *_):
        self.c.settings["delete_after_upload"] = self.delete_local.isChecked()
        self.c.settings["retention_days"] = 0
        self.c.save_settings(); self.c._cleanup_next = 0

    def apply(self):
        options = {"duration": int(self.duration.currentText()), "fps": int(self.fps.currentText()),
                   "monitor": self.monitor.currentData(), "resolution": self.resolution.currentData(),
                   "audio_device": self.audio.currentData(), "microphone": self.mic.currentData(),
                   "shortcut": self.shortcut.currentText(), "encoder": self.encoder.currentText(),
                   "quality": self.quality.currentData()}
        self.c.apply_settings(options)
        self.refresh()

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Choose clips folder", str(self.c.clips))
        if selected:
            self.c.clips = Path(selected); self.c.settings["clips_folder"] = selected
            self.c.save_settings(); self.clip_path.setText(selected); self.refresh()

    def choose_drive_name(self):
        name, accepted = QInputDialog.getText(self, "Rename Drive folder",
            "Choose a name for your Clipper folder in Google Drive:",
            text=self.c.drive_folder_name or "Clipper")
        if accepted:
            name = name.strip()
            if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
                QMessageBox.warning(self, "Clipper", "Enter a folder name between 1 and 255 characters without control characters.")
            elif name != self.c.drive_folder_name:
                self.c.rename_drive_folder(name)

    def _update_recording_clock(self):
        if self.c.manual_recording:
            elapsed = max(0, int(time.time() - self.c.manual_recording[2]))
            self.manual_status.setText(f"Recording  ·  {elapsed // 60:02d}:{elapsed % 60:02d}")
        else:
            self.manual_status.setText("Start a longer video. Stop when you're ready.")

    def refresh(self):
        status = self.c.recording_status
        if self.c.recorder and self.c.recorder.failure: status = "Error: " + self.c.recorder.failure
        error = status.startswith("Error")
        active = bool(self.c.recorder) and not error
        ready = active and bool(getattr(self.c.recorder, "_closed_history", ()))
        self.status.setText("Capture needs attention" if error else "Capturing" if ready else "Warming up" if active else "Paused")
        self.status.setProperty("tone", "red" if error else "green" if ready else "neutral")
        self.status.style().unpolish(self.status); self.status.style().polish(self.status)
        self.status.setToolTip(status)
        self.replay_duration.setText(str(self.c.settings.get("duration", 30)))
        self.shortcut_key.setText(self.c.settings.get("shortcut", "F8"))
        self.save_button.setEnabled(ready)
        self.save_button.setToolTip("Save the available replay" if ready else "Wait for capture to produce video" if active else "Resume capture to save a replay")
        self.pause_button.setText("Pause" if self.c.recorder else "Resume capture")
        self.pause_button.setEnabled(not self.c.manual_recording)
        self.record_button.setEnabled(ready or bool(self.c.manual_recording))
        self.record_button.setText("Stop recording" if self.c.manual_recording else "Start recording")
        role = "RecordActive" if self.c.manual_recording else ""
        if self.record_button.objectName() != role:
            self.record_button.setObjectName(role)
            self.record_button.style().unpolish(self.record_button); self.record_button.style().polish(self.record_button)
        self._update_recording_clock()
        self.capture_warning.setText(status if error else self.c.hotkey_error or "Replay timing is approximate; the final seconds may be missing.")
        self.capture_warning.setStyleSheet("color: #c43e40;" if error or self.c.hotkey_error else "")
        self.shortcut_warning.setText(self.c.hotkey_error or "")
        self.shortcut_warning.setVisible(bool(self.c.hotkey_error))
        self.apply_button.setEnabled(not self.c.manual_recording)
        self.drive_status.setText("Connected" if self.c.drive_status == "Connected" else "Checking…" if self.c.drive_status == "Not checked" else "Not connected")
        self.account_status.setText(self.c.drive_status)
        self.connect_button.setText("Check connection" if self.c.drive_status == "Connected" else "Connect Drive")
        self.drive_folder_label.setText("Renaming…" if self.c.drive_folder_busy else self.c.drive_folder_name or
                                        ("Choose a name for your uploads." if self.c.drive_status == "Connected" else "Connect Google Drive to choose a folder name."))
        self.rename_drive_button.setEnabled(self.c.drive_status == "Connected" and not self.c.drive_folder_busy)
        self.last.setText("Latest clip  ·  " + self.c.last_clip if self.c.last_clip else "Your next highlight starts here.")
        rows = self.c.queue.list()
        pending = sum(row["state"] != "completed" for row in rows)
        self.pending.setText(f"{pending} upload{'s' if pending != 1 else ''} waiting" if pending else "All uploads up to date" if rows else "Saved clips upload automatically")
        try: self.space.setText("%.1f GB free" % (shutil.disk_usage(self.c.clips).free / 1e9))
        except OSError: self.space.setText("Unavailable")
        snapshot = tuple((row["id"], row["state"], row["progress"], row["error"]) for row in rows)
        if snapshot == self._queue_snapshot: return
        self._queue_snapshot = snapshot
        self.table.setVisible(bool(rows)); self.empty_uploads.setVisible(not rows)
        self.table.setRowCount(len(rows))
        state_names = {"completed": "Uploaded", "uploading": "Uploading", "pending": "Queued",
                       "failed": "Will retry", "waiting_for_authentication": "Sign-in needed"}
        for n, row in enumerate(reversed(rows)):
            values = (Path(row["local_path"]).name, state_names.get(row["state"], row["state"]),
                      f"{row['progress'] * 100:.0f}%", row["error"] or "")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value); item.setToolTip(value)
                if column == 1: item.setForeground(QColor("#267447" if row["state"] == "completed" else "#0074e8" if row["state"] in ("pending", "uploading") else "#b75c31"))
                self.table.setItem(n, column, item)
