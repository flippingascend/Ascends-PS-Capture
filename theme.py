"""Themes and RGB LED lighting.

Everything that glows is painted here from one shared colour source
(ThemeManager.sample), so the window frame, the strips, the tabs, the buttons
and the title all flow together like a PC's RGB lighting. Static Qt stylesheet
colours come from the same preset.
"""
import json
import math

from PySide6.QtCore import QObject, QPointF, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QPushButton, QTabBar, QWidget

EFFECTS = ["Rainbow wave", "Color cycle", "Breathing", "Static", "Off"]

PRESETS = {
    "Studio": {
        "bg": "#13161c", "panel": "#1a1e26", "text": "#edf0f6", "muted": "#a2aab8",
        "line": "#303640", "accent": "#77beed", "rainbow": False,
        "gradient": ["#77beed", "#77beed"],
    },
    "RGB Rainbow": {
        "bg": "#07060d", "panel": "#110f1c", "text": "#f2f0fb", "muted": "#8d88a8",
        "line": "#262140", "accent": "#00d5ff", "rainbow": True,
        "gradient": ["#ff0040", "#ffd000", "#00ff6a", "#00d5ff", "#7a00ff"],
    },
    "Cyber Blue": {
        "bg": "#050912", "panel": "#0c1424", "text": "#e9f2ff", "muted": "#7f93b3",
        "line": "#1c2a47", "accent": "#12b8ff", "rainbow": False,
        "gradient": ["#0050ff", "#12b8ff", "#8af3ff"],
    },
    "Neon Pink": {
        "bg": "#0a0510", "panel": "#150b20", "text": "#fbeaff", "muted": "#a283b5",
        "line": "#2d1745", "accent": "#ff2bd6", "rainbow": False,
        "gradient": ["#ff1f8f", "#b300ff", "#00d5ff"],
    },
    "Toxic Green": {
        "bg": "#040a06", "panel": "#0a150d", "text": "#e6ffee", "muted": "#7fae8b",
        "line": "#173322", "accent": "#00ff6a", "rainbow": False,
        "gradient": ["#00ff6a", "#b6ff00", "#00ffd5"],
    },
    "Ember": {
        "bg": "#0d0605", "panel": "#1a0d0a", "text": "#fff0e8", "muted": "#b4917f",
        "line": "#3a1c14", "accent": "#ff7a00", "rainbow": False,
        "gradient": ["#ff1f00", "#ff7a00", "#ffd000"],
    },
    "Ice White": {
        "bg": "#080a0e", "panel": "#12161d", "text": "#f4f8ff", "muted": "#8b97a8",
        "line": "#252d3a", "accent": "#bfe4ff", "rainbow": False,
        "gradient": ["#ffffff", "#9fd8ff", "#d6c4ff"],
    },
    "Midnight": {
        "bg": "#0a0b10", "panel": "#13151d", "text": "#eceef7", "muted": "#8a8fa6",
        "line": "#23273a", "accent": "#7a86ff", "rainbow": False,
        "gradient": ["#7a86ff", "#7a86ff"],
    },
    "Light": {
        "bg": "#eceaf4", "panel": "#ffffff", "text": "#1b1830", "muted": "#6a6585",
        "line": "#d4d0e4", "accent": "#5a3cff", "rainbow": True,
        "gradient": ["#ff0040", "#ff9a00", "#00c853", "#00a8e8", "#7a00ff"],
    },
}

DEFAULTS = {
    "preset": "Studio",
    "effect": "Static",
    "speed": 35,         # animation speed, 1-100
    "brightness": 100,   # LED brightness, 10-100
    "glow": 15,          # strength of the glow around the LEDs, 0-100
    "led_frame": False,   # light strip around the whole window
    "glow_title": False,
    "font_size": 11,     # points
    "radius": 8,         # corner roundness, px
}

_THEME = None


def current():
    return _THEME


def ui_family():
    """Best available UI font: Bahnschrift (built into Windows 10/11) looks closest to a
    gaming-hardware app; Segoe UI is the safe fallback."""
    families = QFontDatabase.families()
    for name in ("Segoe UI Variable Text", "Segoe UI", "Arial"):
        if name in families:
            return name
    return QFont().family()


def mix(a, b, t):
    ca, cb = QColor(a), QColor(b)
    return QColor(
        round(ca.red() + (cb.red() - ca.red()) * t),
        round(ca.green() + (cb.green() - ca.green()) * t),
        round(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def gradient_qss(colors):
    if len(colors) == 1:
        colors = colors * 2
    stops = ", ".join("stop:{:.3f} {}".format(i / (len(colors) - 1), c)
                      for i, c in enumerate(colors))
    return "qlineargradient(x1:0, y1:0, x2:1, y2:0, {})".format(stops)


class ThemeManager(QObject):
    """Current look + LED animation. `tick` fires ~30x a second while an effect moves."""

    changed = Signal()
    tick = Signal()

    def __init__(self):
        super().__init__()
        global _THEME
        _THEME = self
        self.settings = QSettings("AscendToolkit", "AscendToolkit")
        self.values = dict(DEFAULTS)
        self.custom = None
        saved = self.settings.value("theme/json2", "")
        if saved:
            try:
                self.values.update(json.loads(saved))
            except ValueError:
                pass
        self.custom = self.values.get("custom")
        if self.values["preset"] not in PRESETS and self.values["preset"] != "Custom":
            self.values["preset"] = DEFAULTS["preset"]
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.changed.connect(self._sync_animation)
        self._sync_animation()

    # ---------- reading ----------
    def palette(self):
        name = self.values["preset"]
        base = dict(PRESETS.get(name, PRESETS["RGB Rainbow"]))
        if name == "Custom" and self.custom:
            base.update(self.custom)
        return base

    def get(self, key):
        return self.values.get(key, DEFAULTS.get(key))

    def glow(self):
        return self.get("glow") / 100.0

    # ---------- LED colour source ----------
    def _base(self, t, v):
        t %= 1.0
        pal = self.palette()
        if pal.get("rainbow"):
            return QColor.fromHsvF(t, 1.0, v)
        colors = list(pal["gradient"])
        if colors[0] != colors[-1]:
            colors.append(colors[0])
        seg = t * (len(colors) - 1)
        i = min(int(seg), len(colors) - 2)
        f = seg - i
        a, b = QColor(colors[i]), QColor(colors[i + 1])
        return QColor(
            round((a.red() + (b.red() - a.red()) * f) * v),
            round((a.green() + (b.green() - a.green()) * f) * v),
            round((a.blue() + (b.blue() - a.blue()) * f) * v),
        )

    def sample(self, pos):
        """Colour of the light at position `pos` (0..1 along a strip, wraps)."""
        effect = self.get("effect")
        v = self.get("brightness") / 100.0
        if effect == "Off":
            return QColor(self.palette()["line"])
        if effect == "Rainbow wave":
            return self._base(pos - self.phase, v)
        if effect == "Color cycle":
            return self._base(-self.phase, v)
        if effect == "Breathing":
            pulse = 0.5 + 0.5 * math.sin(self.phase * 2 * math.pi)
            return self._base(pos, v * (0.25 + 0.75 * pulse))
        return self._base(pos, v)  # Static

    def gradient(self, p0, p1, pos_a=0.0, pos_b=1.0, alpha=1.0):
        """Linear gradient from p0 to p1 lit by the LED effect between pos_a and pos_b."""
        g = QLinearGradient(p0, p1)
        n = 48
        for i in range(n + 1):
            t = i / n
            c = self.sample(pos_a + (pos_b - pos_a) * t)
            c.setAlphaF(max(0.0, min(1.0, alpha)))
            g.setColorAt(t, c)
        return g

    # ---------- writing ----------
    def set(self, key, value):
        self.values[key] = value
        self._save()

    def set_custom(self, key, value):
        if not self.custom:
            self.custom = dict(self.palette())
        self.custom[key] = value
        self.values["custom"] = self.custom
        self.values["preset"] = "Custom"
        self._save()

    def reset(self):
        self.values = dict(DEFAULTS)
        self.custom = None
        self._save()

    def _save(self):
        self.settings.setValue("theme/json2", json.dumps(self.values))
        self.changed.emit()

    def _sync_animation(self):
        if self.get("effect") in ("Static", "Off"):
            self.timer.stop()
        else:
            self.timer.start(33)

    def _advance(self):
        if self.get("effect") in ("Static", "Off"):
            return
        self.phase = (self.phase + self.get("speed") / 6000.0) % 1.0
        self.tick.emit()

    # ---------- stylesheet (the static, non-glowing parts) ----------
    def stylesheet(self):
        p = self.palette()
        bg, panel, text, muted, line = p["bg"], p["panel"], p["text"], p["muted"], p["line"]
        accent = p["accent"]
        g = gradient_qss(p["gradient"])
        fs = int(self.get("font_size"))
        r = int(self.get("radius"))
        input_bg = mix(panel, bg, 0.45)
        hover = mix(panel, text, 0.08)
        on_accent = "#111111" if QColor(accent).lightness() > 140 else "#ffffff"
        display = ui_family()
        return """
* {{ font-family: "{display}"; font-size: {fs}pt; }}
QMainWindow, QDialog, QWidget#Root {{ background: {bg}; }}
QWidget {{ color: {text}; }}
QLabel {{ background: transparent; border: none; padding: 0; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: {bg}; border: none; }}
QLabel#Muted {{ color: {muted}; }}
QLabel#PageTitle {{ font-size: 26px; font-weight: 600; padding: 14px 0 10px 0; }}
QLabel#Brand {{ font-size: 12px; font-weight: 500; color: {muted}; }}
QListWidget {{ background: {input_bg}; color: {text}; border: 1px solid {line}; border-radius: {r}px; padding: 6px; }}
QListWidget::item {{ padding: 12px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {line}; color: {accent}; }}
QListWidget::item:hover {{ background: {hover}; }}
QListWidget#Navigation {{ background: transparent; border: none; padding: 0; }}
QListWidget#Navigation::item {{ background: transparent; padding: 15px 12px; font-weight: 500; border-radius: 0; color: {muted}; }}
QListWidget#Navigation::item:selected {{ background: transparent; color: {text}; border-left: 2px solid {accent}; }}
QListWidget#Navigation::item:hover {{ background: transparent; color: {text}; }}
QToolButton {{ color: {text}; background: {panel}; border: 1px solid {line}; border-radius: 6px; padding: 6px; }}
QToolButton:hover {{ border-color: {accent}; }}
QGraphicsView {{ border: none; background: black; }}
QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{ background: transparent; color: {muted}; padding: 12px 18px; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {text}; border-bottom-color: {accent}; }}
QTabBar::tab:hover {{ color: {text}; }}
QLabel#BigValue {{ font-family: "{display}"; font-size: {big}pt; font-weight: 600; }}
QToolTip {{ background: {panel}; color: {text}; border: 1px solid {line}; padding: 4px; }}
QStackedWidget {{ background: transparent; }}

QGroupBox {{
    background: {panel}; border: 1px solid {line}; border-radius: {r}px;
    margin-top: 0px; padding: 3em 12px 16px 12px; font-family: "{display}"; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: border; subcontrol-position: top left; top: 16px; left: 24px; padding: 0; color: {text}; background: transparent; }}
QFrame#Card {{ background: {panel}; border: 1px solid {line}; border-radius: {r}px; }}

QPushButton {{
    background: transparent; color: {text}; border: 1px solid transparent; border-radius: {r}px;
    padding: 9px 14px; font-family: "{display}"; font-weight: 600;
}}
QPushButton#Primary {{ background: {accent}; color: #111820; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {text}; }}
QPushButton:hover {{ border: 1px solid {accent}; background: {hover}; }}
QPushButton:pressed {{ background: {line}; }}
QPushButton:checked {{ border: 1px solid {line}; color: {accent}; }}
QPushButton:disabled {{ color: {muted}; }}
QPushButton#Danger {{ background: #b3203c; color: white; border: 1px solid #ff4d6d; }}
QPushButton#Danger:hover {{ background: #d02a4a; }}
QPushButton#Swatch {{ min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
    padding: 0; border-radius: 13px; }}

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {input_bg}; color: {text}; border: 1px solid {line}; border-radius: {r}px;
    padding: 6px 8px; selection-background-color: {accent}; selection-color: {on_accent};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {panel}; color: {text}; border: 1px solid {line};
    selection-background-color: {accent}; selection-color: {on_accent}; outline: none; }}

QTreeWidget, QTableWidget {{
    background: {input_bg}; alternate-background-color: {panel}; color: {text};
    border: 1px solid {line}; border-radius: {r}px; gridline-color: {line};
    selection-background-color: {accent}; selection-color: {on_accent};
}}
QHeaderView::section {{ background: {panel}; color: {muted}; border: none;
    border-bottom: 1px solid {line}; padding: 6px; font-family: "{display}"; font-weight: 600; }}
QTableCornerButton::section {{ background: {panel}; border: none; }}
QHeaderView {{ background: {panel}; }}

QProgressBar {{ background: {input_bg}; border: 1px solid {line}; border-radius: {r}px;
    text-align: center; color: {text}; min-height: 18px; }}
QProgressBar::chunk {{ background: {g}; border-radius: {r}px; }}

QSlider::groove:horizontal {{ height: 6px; background: {line}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {g}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {text}; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {line}; background: {input_bg}; }}
QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {line}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {line}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {panel}; color: {text}; border: 1px solid {line}; }}
QMenu::item:selected {{ background: {accent}; color: {on_accent}; }}
""".format(fs=fs, big=fs + 8, bg=bg, panel=panel, text=text, muted=muted, line=line,
           accent=accent, g=g, r=r, input_bg=input_bg, hover=hover, on_accent=on_accent,
           display=display)


# ---------------------------------------------------------------------------
# painted widgets
# ---------------------------------------------------------------------------
class Animated:
    """Mixin: repaint with the LED animation, but only while the widget is visible."""

    def _hook(self, on):
        if on == getattr(self, "_hooked", False):
            return
        self._hooked = on
        for sig in (self.theme.tick, self.theme.changed):
            if on:
                sig.connect(self._anim_update)
            else:
                sig.disconnect(self._anim_update)

    def showEvent(self, event):
        self._hook(True)
        super().showEvent(event)

    def hideEvent(self, event):
        self._hook(False)
        super().hideEvent(event)

    def _anim_update(self, *_):
        self.update()


def _glow_bands(height):
    """(thickness, strength) layers painted under the bright core, widest first."""
    return ((height, 0.10), (height * 0.68, 0.20), (height * 0.42, 0.34))


class LedStrip(Animated, QWidget):
    """Glowing horizontal LED line."""

    def __init__(self, theme, height=12):
        super().__init__()
        self.theme = theme
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        mid = h / 2.0
        glow = self.theme.glow()
        a, b = QPointF(0, 0), QPointF(w, 0)
        cycles = max(1, round(w / 700.0))
        if glow > 0:
            for thick, strength in _glow_bands(h):
                g = self.theme.gradient(a, b, 0, cycles, strength * glow)
                p.fillRect(QRectF(0, mid - thick / 2, w, thick), QBrush(g))
        g = self.theme.gradient(a, b, 0, cycles, 1.0)
        p.fillRect(QRectF(0, mid - 1.25, w, 2.5), QBrush(g))


class LedEdge(Animated, QWidget):
    """One side of the light strip that runs around the whole window.

    Four of these (not one big overlay) so only the thin edges repaint, never the video.
    """

    THICKNESS = 8

    def __init__(self, theme, side, parent):
        super().__init__(parent)
        self.theme = theme
        self.side = side
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def place(self, w, h):
        t = self.THICKNESS
        geo = {"top": (0, 0, w, t), "bottom": (0, h - t, w, t),
               "left": (0, t, t, h - 2 * t), "right": (w - t, t, t, h - 2 * t)}[self.side]
        self.setGeometry(*geo)

    def paintEvent(self, _event):
        par = self.parentWidget()
        W, H = par.width(), par.height()
        t = self.THICKNESS
        perim = float(2 * (W + H))
        cyc = max(2.0, round(perim / 900.0))
        w, h = self.width(), self.height()
        s = self.side
        if s == "top":
            p0, p1, a, b = QPointF(0, 0), QPointF(w, 0), 0, W
        elif s == "bottom":
            p0, p1, a, b = QPointF(0, 0), QPointF(w, 0), 2 * W + H, W + H
        elif s == "right":
            p0, p1, a, b = QPointF(0, 0), QPointF(0, h), W + t, W + H - t
        else:
            p0, p1, a, b = QPointF(0, 0), QPointF(0, h), 2 * W + 2 * H - t, 2 * W + H + t
        pa, pb = a / perim * cyc, b / perim * cyc
        glow = self.theme.glow()
        p = QPainter(self)

        def band(thick):  # strips hug the outer edge of the window and glow inward
            return {"top": QRectF(0, 0, w, thick), "bottom": QRectF(0, h - thick, w, thick),
                    "left": QRectF(0, 0, thick, h), "right": QRectF(w - thick, 0, thick, h)}[s]

        if glow > 0:
            for thick, strength in _glow_bands(t):
                g = self.theme.gradient(p0, p1, pa, pb, strength * glow)
                p.fillRect(band(thick), QBrush(g))
        g = self.theme.gradient(p0, p1, pa, pb, 1.0)
        p.fillRect(band(2.5), QBrush(g))


class GlowButton(Animated, QPushButton):
    """Main action button: dark body with an animated LED outline that flares on hover."""

    def __init__(self, text=""):
        super().__init__(text)
        self.theme = current()
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(36)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self.text()) + 40, 38)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        theme = self.theme
        pal = theme.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        rad = float(theme.get("radius"))
        hot = self.underMouse() and self.isEnabled()
        glow = theme.glow() * (1.0 if self.isEnabled() else 0.0)
        a, b = r.topLeft(), r.topRight()
        p.setBrush(Qt.NoBrush)
        if glow > 0:
            boost = 1.9 if hot else 1.0
            for width, strength in ((6.0, 0.10), (4.0, 0.18), (2.4, 0.30)):
                g = theme.gradient(a, b, 0, 1, min(1.0, strength * glow * boost))
                p.setPen(QPen(QBrush(g), width))
                p.drawRoundedRect(r, rad, rad)
        fill = QColor(pal["bg"] if self.isDown() else pal["panel"])
        if hot and not self.isDown():
            fill = QColor(mix(pal["panel"], pal["text"], 0.07))
        p.setBrush(fill)
        p.setPen(QPen(QBrush(theme.gradient(a, b, 0, 1, 1.0 if self.isEnabled() else 0.3)), 1.6))
        p.drawRoundedRect(r, rad, rad)
        font = QFont(ui_family(), max(9, int(theme.get("font_size"))))
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        p.setPen(QColor(pal["text"] if self.isEnabled() else pal["muted"]))
        p.drawText(self.rect(), Qt.AlignCenter, self.text())


class LedTabBar(Animated, QTabBar):
    """Flat tabs; the selected one gets a glowing LED underline."""

    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def _font(self):
        font = QFont(ui_family(), max(10, int(self.theme.get("font_size")) + 1))
        font.setWeight(QFont.DemiBold)
        return font

    def tabSizeHint(self, index):
        fm = QFontMetrics(self._font())
        return QSize(fm.horizontalAdvance(self.tabText(index)) + 34, 44)

    def mouseMoveEvent(self, event):
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):
        theme = self.theme
        pal = theme.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._font())
        cursor = self.mapFromGlobal(QCursor.pos())
        total = max(self.width(), 1)
        glow = theme.glow()
        for i in range(self.count()):
            r = self.tabRect(i)
            selected = i == self.currentIndex()
            if not selected and r.contains(cursor):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(pal["panel"]))
                p.drawRoundedRect(QRectF(r).adjusted(2, 6, -2, -6), 8, 8)
            p.setPen(QColor(pal["text"] if selected else pal["muted"]))
            p.drawText(r, Qt.AlignCenter, self.tabText(i))
            if selected:
                x0, x1 = r.left() + 6, r.right() - 6
                y = r.bottom() - 4
                a, b = QPointF(x0, 0), QPointF(x1, 0)
                pa, pb = x0 / total, x1 / total
                if glow > 0:
                    for thick, strength in ((9.0, 0.12), (6.0, 0.22), (3.8, 0.36)):
                        g = theme.gradient(a, b, pa, pb, strength * glow)
                        p.fillRect(QRectF(x0, y - thick / 2, x1 - x0, thick), QBrush(g))
                g = theme.gradient(a, b, pa, pb, 1.0)
                p.fillRect(QRectF(x0, y - 1.25, x1 - x0, 2.5), QBrush(g))


class LedTitle(Animated, QWidget):
    """App name filled with the LED colours, with a soft glow behind it."""

    def __init__(self, theme, text):
        super().__init__()
        self.theme = theme
        self.text = text
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedHeight(46)
        self.setFixedWidth(self._font_metrics_width() + 14)

    def _font(self):
        font = QFont(ui_family(), 19)
        font.setWeight(QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        return font

    def _font_metrics_width(self):
        fm = QFontMetrics(self._font())
        return fm.horizontalAdvance(self.text) + 3 * len(self.text)

    def paintEvent(self, _event):
        theme = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = self._font()
        fm = QFontMetrics(font)
        path = QPainterPath()
        path.addText(4, (self.height() + fm.ascent() - fm.descent()) / 2.0, font, self.text)
        w = max(self.width(), 1)
        a, b = QPointF(0, 0), QPointF(w, 0)
        if theme.get("glow_title") and theme.glow() > 0:
            for width, strength in ((9.0, 0.10), (5.0, 0.20)):
                g = theme.gradient(a, b, 0, 1, strength * theme.glow())
                p.setPen(QPen(QBrush(g), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(theme.gradient(a, b, 0, 1, 1.0)))
        p.drawPath(path)
