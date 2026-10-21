"""Ascend: console profiles, capture, payload vault, LAN manager and music."""
import os
import sys

from PySide6.QtCore import QSettings, Qt, QTime, QTimer

# The video engine has to be chosen before Qt Multimedia loads.
_settings = QSettings("AscendToolkit", "AscendToolkit")
_backend = _settings.value("capture/backend", "")
if _backend and "QT_MEDIA_BACKEND" not in os.environ:
    os.environ["QT_MEDIA_BACKEND"] = _backend

from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from capture_tab import CaptureTab  # noqa: E402
from payload_tab import PayloadTab
from music_tab import MusicTab
from web_tab import WebManagerTab
from ftp_tab import FtpTab
from brand import asset
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import QListWidget, QAbstractItemView, QScrollArea
from PySide6.QtGui import QIcon  # noqa: E402
from home_tab import HomeTab  # noqa: E402
from network_tab import NetworkTab  # noqa: E402
from settings_tab import SettingsTab  # noqa: E402
from theme import LedEdge, LedStrip, LedTabBar, LedTitle, ThemeManager, ui_family  # noqa: E402


def raise_priority():
    if not _settings.value("app/high_priority", True, type=bool):
        return
    try:
        import psutil
        proc = psutil.Process()
        if sys.platform.startswith("win"):
            proc.nice(psutil.HIGH_PRIORITY_CLASS)
        else:
            proc.nice(-5)
    except Exception:
        pass  # not allowed on this system; run at normal priority


def style_titlebar(win, theme):
    """Colour the Windows title bar to match the theme (no white strip on top)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        from ctypes import wintypes
        pal = theme.palette()
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                              ctypes.c_void_p, wintypes.DWORD]
        hwnd = wintypes.HWND(int(win.winId()))

        def put(attr, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        def colorref(hex_color):
            c = QColor(hex_color)
            return c.red() | (c.green() << 8) | (c.blue() << 16)

        dark = int(QColor(pal["bg"]).lightness() < 128)
        put(20, dark)                      # dark title bar (Windows 10 20H1+ and 11)
        put(19, dark)                      # same switch on older Windows 10 builds
        put(35, colorref(pal["bg"]))       # caption colour (Windows 11)
        put(36, colorref(pal["text"]))     # caption text colour
        put(34, colorref(pal["bg"]))       # window border colour
    except Exception:
        pass


class Root(QWidget):
    """Central widget; keeps the four LED edge strips on the window border."""

    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.edges = []

    def resizeEvent(self, event):
        for edge in self.edges:
            edge.place(self.width(), self.height())
            edge.raise_()
        super().resizeEvent(event)


class Navigation(QListWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('Navigation')
        self.setFixedWidth(178)
        self.setSpacing(6)
        self.setFocusPolicy(Qt.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    def addTab(self, text):
        self.addItem(text)
    def setCurrentIndex(self, index):
        self.setCurrentRow(index)

class MainWindow(QMainWindow):
    PAGES = ("Capture Studio", "Console Setup", "Payload Holder", "Web Manager", "Music", "Network", "FTP", "Settings")

    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setWindowTitle("Ascends PS Capture program")
        self.setWindowIcon(QIcon(asset("ascend.ico")))
        self.resize(1440, 900)
        self.setMinimumSize(900, 620)
        self.cinema = False
        self.was_maximized = False

        # ---- pages ----
        self.capture = CaptureTab()
        self.home = HomeTab(theme)
        self.payloads = PayloadTab()
        self.web = WebManagerTab()
        self.music = MusicTab()
        self.network = NetworkTab()
        self.ftp = FtpTab()
        self.settings_tab = SettingsTab(theme)
        self.tabbar = Navigation()
        self.stack = QStackedWidget()
        for name, page in zip(self.PAGES, (self.capture, self.home, self.payloads, self.web, self.music,
                                           self.network, self.ftp, self.settings_tab)):
            self.tabbar.addTab(name)
            if page in (self.music,self.network):
                scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame)
                scroll.setWidget(page); self.stack.addWidget(scroll)
            else:
                self.stack.addWidget(page)
        self.tabbar.currentRowChanged.connect(self.stack.setCurrentIndex)

        # ---- header: name, tabs, PS3 status, clock ----
        self.console_pill = QLabel("PS5 • FW " + str(_settings.value("console/firmware", "")))
        self.console_pill.setObjectName("Muted")
        self.console_pill.setWordWrap(False)
        self.console_pill.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.console_pill.setTextFormat(Qt.PlainText)
        self.clock = QLabel()
        self.clock.setObjectName("Muted")
        self.clock.setFixedWidth(52)
        self.clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.header = QWidget()
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(20, 12, 20, 12)
        hl.setSpacing(0)
        brand = QLabel("Ascends PS Capture program"); brand.setObjectName("Brand")
        hl.addWidget(brand)
        hl.addSpacing(22)
        hl.addStretch(1)
        hl.addWidget(self.console_pill)
        hl.addSpacing(16)
        hl.addWidget(self.clock)
        self.strip = LedStrip(theme, 2)

        self.body = QWidget()
        self.body_layout = QHBoxLayout(self.body)
        self.body_layout.setSpacing(24)
        self.nav_container = QWidget()
        nav = QVBoxLayout(self.nav_container)
        nav.setContentsMargins(0, 12, 12, 0)
        logo = QSvgWidget(asset('ascend.svg')); logo.setFixedSize(178, 48)
        nav.addWidget(logo)
        subtitle = QLabel('CAPTURE PROGRAM'); subtitle.setObjectName('LogoSubtitle')
        subtitle.setStyleSheet('color: #c3d0df; font-size: 10pt; font-weight: 600; padding-left: 6px;')
        nav.addWidget(subtitle); nav.addSpacing(22); nav.addWidget(self.tabbar, 1)
        self.body_layout.addWidget(self.nav_container)
        self.body_layout.addWidget(self.stack, 1)

        self.root = Root()
        self.root_layout = QVBoxLayout(self.root)
        self.root_layout.setSpacing(0)
        self.root_layout.addWidget(self.header)
        self.root_layout.addWidget(self.strip)
        self.root_layout.addWidget(self.body, 1)
        for side in ("top", "bottom", "left", "right"):
            self.root.edges.append(LedEdge(theme, side, self.root))
        self.setCentralWidget(self.root)
        # Reserve the Qt Quick composition surface before this window is shown.
        # Chromium adds a Quick surface on first use; without this reservation
        # Qt recreates the visible native window when opening Web Manager.
        from PySide6.QtQuickWidgets import QQuickWidget
        self.graphics_anchor = QQuickWidget(self.root)
        self.graphics_anchor.setClearColor(Qt.transparent)
        self.graphics_anchor.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.graphics_anchor.setGeometry(0, 0, 1, 1)
        self.graphics_anchor.lower()

        # ---- wiring ----
        self.network.console_found.connect(self._use_console_ip)
        self.home.host_changed.connect(lambda host: self._console_status(False, host))
        self.home.profile_changed.connect(self._refresh_profile)
        self.home.profile_changed.connect(self.ftp.apply_profile)
        self.capture.health_changed.connect(self.home.update_capture_health)
        self.home.update_capture_health(self.capture.health_snapshot())
        self.capture.fullscreen_requested.connect(self.toggle_cinema)
        theme.changed.connect(self._apply_theme)
        self._apply_theme()
        self._refresh_profile()
        self.tabbar.setCurrentIndex(0)

        for keys, func in (
            ("F11", self.toggle_cinema),
            ("Escape", lambda: self.cinema and self.toggle_cinema()),
            ("F12", self.capture.screenshot),
            ("Ctrl+R", self.capture.toggle_record),
        ):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(func)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(
            lambda: self.clock.setText(QTime.currentTime().toString("HH:mm")))
        self.clock_timer.start(15000)
        self.clock.setText(QTime.currentTime().toString("HH:mm"))

    def showEvent(self, event):
        super().showEvent(event)
        style_titlebar(self, self.theme)

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(self.theme.stylesheet())
        self.tabbar.setFixedWidth(max(178,int(self.theme.get("font_size"))*16))
        style_titlebar(self, self.theme)
        self._layout_for_mode()

    def _layout_for_mode(self):
        frame = self.theme.get("led_frame") and not self.cinema
        edge = 8 if frame else 0
        self.root_layout.setContentsMargins(edge, edge, edge, edge)
        for e in self.root.edges:
            e.setVisible(frame)
            e.raise_()
        self.body_layout.setContentsMargins(*((0, 0, 0, 0) if self.cinema else (12, 10, 12, 10)))

    def _use_console_ip(self, ip):
        self.home.set_host(ip)
        self.tabbar.setCurrentIndex(1)

    def _refresh_profile(self):
        console = _settings.value('console/type', 'PS5')
        firmware = _settings.value('console/firmware', '')
        loader = _settings.value('console/loader', 'Stock / official')
        self.console_pill.setText(f'{console}   ·   FW {firmware or "—"}')
        self.console_pill.setToolTip(f'{console} · {loader}\nOpen Console Setup to edit your profile.')

    def _console_status(self, online, host):
        self._refresh_profile()
        return

    # ---- edge-to-edge fullscreen for the capture picture ----
    def toggle_cinema(self):
        self.cinema = not self.cinema
        on = self.cinema
        if on:
            self.was_maximized = self.isMaximized()
            self.tabbar.setCurrentIndex(0)
        self.nav_container.setVisible(not on)
        self.header.setVisible(not on)
        self.strip.setVisible(not on)
        self.capture.set_cinema(on)
        self._layout_for_mode()
        if on:
            self.showFullScreen()
        elif self.was_maximized:
            self.showMaximized()
        else:
            self.showNormal()

    def closeEvent(self, event):
        for tab in (self.capture, self.home, self.payloads, self.web, self.music, self.network, self.ftp):
            tab.shutdown()
        super().closeEvent(event)


def main():
    raise_priority()
    if sys.platform.startswith('win'):
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Ascend.PSCapture.Program')
    # Share graphics contexts before Chromium creates its first embedded surface.
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(asset('ascend.ico')))
    app.setApplicationName("Ascends PS Capture program")
    app.setStyle("Fusion")
    font = QFont(ui_family(), 11)
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferDefaultHinting)
    app.setFont(font)
    theme = ThemeManager()
    app.setStyleSheet(theme.stylesheet())
    # Finish setup before constructing capture or browser pages.
    setup = HomeTab(theme)
    if not setup.onboarding():
        setup.deleteLater()
        return
    setup.deleteLater()
    from boot_screen import BootScreen
    boot = BootScreen()
    boot.exec()
    boot.deleteLater()
    win = MainWindow(theme)
    if _settings.value("app/maximized", True, type=bool):
        win.showMaximized()
    else:
        win.show()
    if _settings.value("capture/autofull", False, type=bool):
        QTimer.singleShot(500, win.toggle_cinema)
    if "--music" in sys.argv:
        QTimer.singleShot(800, lambda: (win.tabbar.setCurrentIndex(4), win.music.tabs.setCurrentIndex(1)))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
