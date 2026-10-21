"""Settings: LED lighting and theme customisation, plus capture options. All saved."""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from theme import EFFECTS, PRESETS, GlowButton

BACKENDS = [
    ("Auto (recommended)", ""),
    ("FFmpeg", "ffmpeg"),
    ("Windows Media Foundation", "windows"),
]


def slider(low, high):
    s = QSlider(Qt.Horizontal)
    s.setRange(low, high)
    return s


class SettingsTab(QWidget):
    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.settings = QSettings("AscendToolkit", "AscendToolkit")

        # ---------- lighting ----------
        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS) + ["Custom"])
        self.effect = QComboBox()
        self.effect.addItems(EFFECTS)
        self.speed = slider(1, 100)
        self.brightness = slider(10, 100)
        self.glow = slider(0, 100)
        self.frame = QCheckBox("Light strip around the whole window")
        self.title_glow = QCheckBox("Glow behind the title")

        led_box = QGroupBox("LED lighting")
        lf = QFormLayout(led_box)
        lf.setLabelAlignment(Qt.AlignRight)
        lf.addRow("Colours", self.preset)
        lf.addRow("Effect", self.effect)
        lf.addRow("Speed", self.speed)
        lf.addRow("Brightness", self.brightness)
        lf.addRow("Glow", self.glow)
        lf.addRow("", self.frame)
        lf.addRow("", self.title_glow)

        # ---------- custom colours ----------
        self.swatches = {}
        colours_row = QHBoxLayout()
        for key, label in (("bg", "Background"), ("panel", "Panels"), ("text", "Text"),
                           ("muted", "Labels")):
            colours_row.addWidget(self._swatch(key, label))
        colours_row.addStretch()
        self.grad_buttons = []
        grad_row = QHBoxLayout()
        for i in range(3):
            b = QPushButton()
            b.setObjectName("Swatch")
            b.setToolTip("LED colour {}".format(i + 1))
            b.clicked.connect(lambda _c=False, n=i: self._pick_gradient(n))
            self.grad_buttons.append(b)
            grad_row.addWidget(b)
        rainbow_btn = GlowButton("Full rainbow")
        rainbow_btn.clicked.connect(self._full_rainbow)
        grad_row.addSpacing(8)
        grad_row.addWidget(rainbow_btn)
        grad_row.addStretch()
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 16)
        self.radius = slider(0, 20)
        reset = QPushButton("Reset the look")

        look_box = QGroupBox("Your own colours and shape")
        tf = QFormLayout(look_box)
        tf.setLabelAlignment(Qt.AlignRight)
        tf.addRow("Surfaces", colours_row)
        tf.addRow("LED colours", grad_row)
        tf.addRow("Text size", self.font_size)
        tf.addRow("Roundness", self.radius)
        tf.addRow("", reset)

        # ---------- capture and startup ----------
        self.autostart = QCheckBox("Start the capture card as soon as the app opens")
        self.autofull = QCheckBox("Open straight into fullscreen")
        self.mjpeg = QCheckBox("Prefer MJPEG capture formats")
        self.backend = QComboBox()
        for label, _v in BACKENDS:
            self.backend.addItem(label)
        self.priority = QCheckBox("Run at high priority for smoother video")
        self.maximized = QCheckBox("Open the window maximised")
        note = QLabel("Video engine changes apply next time you open the app. If the "
                      "picture freezes now and then, try the other engine.")
        note.setObjectName("Muted")
        note.setWordWrap(True)

        cap_box = QGroupBox("Capture and startup")
        cf = QFormLayout(cap_box)
        cf.setLabelAlignment(Qt.AlignRight)
        cf.addRow("", self.autostart)
        cf.addRow("", self.autofull)
        cf.addRow("", self.mjpeg)
        cf.addRow("Video engine", self.backend)
        cf.addRow("", note)
        cf.addRow("", self.priority)
        cf.addRow("", self.maximized)

        keys = QLabel("Shortcuts:  F11 fullscreen,  Esc leave fullscreen,  F12 screenshot,  "
                      "Ctrl+R record,  double-click the picture for fullscreen.")
        keys.setObjectName("Muted")
        keys.setWordWrap(True)

        inner = QWidget()
        il = QVBoxLayout(inner)
        il.addWidget(led_box)
        il.addWidget(look_box)
        il.addWidget(cap_box)
        il.addWidget(keys)
        il.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(inner)
        scroll.viewport().setAutoFillBackground(False)
        inner.setAutoFillBackground(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._load()
        self.preset.activated.connect(lambda _i: self.theme.set("preset", self.preset.currentText()))
        self.effect.activated.connect(lambda _i: self.theme.set("effect", self.effect.currentText()))
        self.speed.valueChanged.connect(lambda v: self.theme.set("speed", v))
        self.brightness.valueChanged.connect(lambda v: self.theme.set("brightness", v))
        self.glow.valueChanged.connect(lambda v: self.theme.set("glow", v))
        self.frame.toggled.connect(lambda v: self.theme.set("led_frame", v))
        self.title_glow.toggled.connect(lambda v: self.theme.set("glow_title", v))
        self.font_size.valueChanged.connect(lambda v: self.theme.set("font_size", v))
        self.radius.valueChanged.connect(lambda v: self.theme.set("radius", v))
        reset.clicked.connect(self.theme.reset)
        self.theme.changed.connect(self._load)

        self.autostart.toggled.connect(lambda v: self.settings.setValue("capture/autostart", v))
        self.autofull.toggled.connect(lambda v: self.settings.setValue("capture/autofull", v))
        self.mjpeg.toggled.connect(lambda v: self.settings.setValue("capture/prefer_mjpeg", v))
        self.backend.currentIndexChanged.connect(
            lambda i: self.settings.setValue("capture/backend", BACKENDS[i][1]))
        self.priority.toggled.connect(lambda v: self.settings.setValue("app/high_priority", v))
        self.maximized.toggled.connect(lambda v: self.settings.setValue("app/maximized", v))

    def _swatch(self, key, label):
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 8, 0)
        b = QPushButton()
        b.setObjectName("Swatch")
        b.clicked.connect(lambda: self._pick(key))
        self.swatches[key] = b
        row.addWidget(b)
        row.addWidget(QLabel(label))
        return w

    def _pick(self, key):
        colour = QColorDialog.getColor(QColor(self.theme.palette()[key]), self, "Pick a colour")
        if colour.isValid():
            self.theme.set_custom(key, colour.name())

    def _pick_gradient(self, n):
        pal = self.theme.palette()
        grad = list(pal["gradient"])
        if len(grad) != 3:
            grad = [grad[0], grad[len(grad) // 2], grad[-1]]
        colour = QColorDialog.getColor(QColor(grad[n]), self, "Pick an LED colour")
        if not colour.isValid():
            return
        grad[n] = colour.name()
        self.theme.set_custom("rainbow", False)  # your own colours replace the hue wheel
        self.theme.set_custom("accent", grad[1])
        self.theme.set_custom("gradient", grad)

    def _full_rainbow(self):
        self.theme.set("preset", "RGB Rainbow")
        self.theme.set("effect", "Rainbow wave")

    def _load(self):
        p = self.theme.palette()
        widgets = (self.preset, self.effect, self.speed, self.brightness, self.glow,
                   self.frame, self.title_glow, self.font_size, self.radius, self.autostart,
                   self.autofull, self.mjpeg, self.backend, self.priority, self.maximized)
        for w in widgets:
            w.blockSignals(True)
        self.preset.setCurrentText(self.theme.get("preset"))
        self.effect.setCurrentText(self.theme.get("effect"))
        self.speed.setValue(int(self.theme.get("speed")))
        self.brightness.setValue(int(self.theme.get("brightness")))
        self.glow.setValue(int(self.theme.get("glow")))
        self.frame.setChecked(bool(self.theme.get("led_frame")))
        self.title_glow.setChecked(bool(self.theme.get("glow_title")))
        self.font_size.setValue(int(self.theme.get("font_size")))
        self.radius.setValue(int(self.theme.get("radius")))
        for key, b in self.swatches.items():
            b.setStyleSheet("background: {}; border: 2px solid #888;".format(p[key]))
        grad = p["gradient"]
        three = grad if len(grad) == 3 else [grad[0], grad[len(grad) // 2], grad[-1]]
        for b, c in zip(self.grad_buttons, three):
            b.setStyleSheet("background: {}; border: 2px solid #888;".format(c))
        s = self.settings
        self.autostart.setChecked(s.value("capture/autostart", False, type=bool))
        self.autofull.setChecked(s.value("capture/autofull", False, type=bool))
        self.mjpeg.setChecked(s.value("capture/prefer_mjpeg", False, type=bool))
        backend = s.value("capture/backend", "")
        self.backend.setCurrentIndex(next((i for i, b in enumerate(BACKENDS) if b[1] == backend), 0))
        self.priority.setChecked(s.value("app/high_priority", True, type=bool))
        self.maximized.setChecked(s.value("app/maximized", True, type=bool))
        for w in widgets:
            w.blockSignals(False)
