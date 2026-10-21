"""Live capture-card viewer.

Qt Multimedia draws the picture on the GPU, which keeps latency low. The best
format the card offers is picked automatically: 60 fps first, then proper 16:9
modes, then the
biggest resolution, then raw pixel formats over MJPEG.

The camera is only (re)started when you press Start or change the device or
mode yourself. Windows device-change notifications only refresh the lists.
"""
import os
import time

from PySide6.QtCore import QElapsedTimer, QSettings, Qt, QTimer, QUrl, Signal, QSizeF
from PySide6.QtGui import QDesktopServices, QPainter
from PySide6.QtMultimedia import (
    QAudioInput,
    QAudioOutput,
    QCamera,
    QMediaCaptureSession,
    QMediaDevices,
    QMediaFormat,
    QMediaRecorder,
    QVideoFrameFormat,
)
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QDialog, QScrollArea, QFormLayout, QGridLayout, QSizePolicy
from PySide6.QtWidgets import (
    QFileDialog,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from theme import GlowButton

PF = QVideoFrameFormat.PixelFormat
RAW_FORMATS = {
    PF.Format_NV12, PF.Format_YUYV, PF.Format_UYVY, PF.Format_YUV420P,
    PF.Format_P010, PF.Format_BGRA8888, PF.Format_ARGB8888, PF.Format_XRGB8888,
}
CAPTURE_HINTS = (
    "capture", "hdmi", "elgato", "cam link", "avermedia", "live gamer",
    "usb video", "usb3", "video", "razer ripsaw", "magewell", "evga",
    "genki", "digital audio", "ezcap", "mirabox", "uvc", "fifine", "ms2109", "ms2130", "4k video",
)
FIT, FILL, STRETCH = 0, 1, 2
FIT_MODES = ["Fit whole picture", "Fill (crops the edges)", "Stretch"]
ASPECTS = [("Auto", 0.0), ("16:9", 16 / 9), ("4:3", 4 / 3), ("5:4", 5 / 4), ("21:9", 21 / 9)]


def captures_dir():
    path = QSettings("AscendToolkit", "AscendToolkit").value("capture/output", "") or os.path.join(os.path.expanduser("~"), "Videos", "Ascend Toolkit")
    os.makedirs(path, exist_ok=True)
    return path


def pixel_format_name(pf):
    return getattr(pf, "name", str(pf)).replace("Format_", "")


def is_widescreen(size):
    return size.height() > 0 and abs(size.width() / size.height() - 16 / 9) < 0.03


def format_score(fmt, prefer_mjpeg=False):
    size = fmt.resolution()
    fps = fmt.maxFrameRate()
    raw = fmt.pixelFormat() in RAW_FORMATS
    return (
        1 if fps >= 59 else 0,                 # 60 fps first
        1 if is_widescreen(size) else 0,       # then real 16:9 modes
        size.width() * size.height(),          # then the biggest picture
        round(fps),
        (not raw) if prefer_mjpeg else raw,    # raw skips a decode step
    )


def describe_format(fmt):
    size = fmt.resolution()
    return "{}x{} @ {:.0f} fps ({})".format(
        size.width(), size.height(), fmt.maxFrameRate(), pixel_format_name(fmt.pixelFormat()))


class VideoView(QGraphicsView):
    double_clicked = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.item = QGraphicsVideoItem()
        self.item.setAspectRatioMode(Qt.IgnoreAspectRatio)
        self.scene.addItem(self.item)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignCenter)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setStyleSheet('background: black; border: none;')
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    def videoSink(self):
        return self.item.videoSink()
    def mouseDoubleClickEvent(self,event):
        self.double_clicked.emit()

class VideoStage(QWidget):
    """The graphics viewport clips all zoom/fill drawing inside the video region."""
    def __init__(self):
        super().__init__()
        self.setObjectName('VideoStage')
        self.setStyleSheet('#VideoStage { background: black; }')
        self.video=VideoView(self)
        self.mode=FIT; self.forced_aspect=0.0; self.zoom=1.0; self.source=(16,9)
        self.setMinimumSize(200,160)

    def configure(self,mode=None,aspect=None,zoom=None,source=None):
        if mode is not None: self.mode=mode
        if aspect is not None: self.forced_aspect=aspect
        if zoom is not None: self.zoom=zoom
        if source is not None: self.source=source
        self._place()

    def resizeEvent(self,event):
        super().resizeEvent(event); self._place()

    def _place(self):
        self.video.setGeometry(self.rect())
        w,h=self.video.viewport().width(),self.video.viewport().height()
        if w<2 or h<2: return
        sw,sh=self.source
        if sw<=0 or sh<=0: return
        src=self.forced_aspect or sw/sh
        if self.mode==STRETCH: bw,bh=w,h
        elif (src>w/h)==(self.mode==FIT): bw,bh=w,w/src
        else: bw,bh=h*src,h
        self.video.item.setSize(QSizeF(sw,sh))
        self.video.scene.setSceneRect(0,0,sw,sh)
        self.video.resetTransform()
        self.video.scale(bw*self.zoom/sw,bh*self.zoom/sh)
        self.video.centerOn(sw/2,sh/2)


class CaptureTab(QWidget):
    fullscreen_requested = Signal()
    health_changed = Signal(dict)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("AscendToolkit", "AscendToolkit")
        self.media_devices = QMediaDevices(self)
        self.session = QMediaCaptureSession(self)
        self.recorder = QMediaRecorder(self)
        self.session.setRecorder(self.recorder)
        self.camera = None
        self.audio_in = None
        self.audio_out = QAudioOutput(self)
        self.formats = []
        self.frames = 0
        self.last_size = None
        self.last_tick = time.monotonic()
        self.frame_clock = QElapsedTimer()
        self.record_started = 0.0

        self.stage = VideoStage()
        self.empty = QLabel("READY TO CAPTURE\n\nConnect a capture card and press Start.\nChoose your console in Console Setup.", self.stage)
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet("color: #8baccb; background: #080e19; font-size: 16px;")
        stage_layout = QVBoxLayout(self.stage)
        stage_layout.addWidget(self.empty)
        self.video = self.stage.video
        self.session.setVideoOutput(self.video.item)
        self.video.videoSink().videoFrameChanged.connect(self._on_frame)
        self.video.double_clicked.connect(self.fullscreen_requested.emit)

        # ---- controls ----
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(['1080p · 60 FPS', '1440p · 60 FPS', '4K · 60 FPS', '720p · 60 FPS'])
        saved_profile = self.settings.value('capture/profile', '1080p · 60 FPS')
        saved_profile = {'Balanced 1080p60':'1080p · 60 FPS', 'Quality 4K60':'4K · 60 FPS', 'Compatibility 720p60':'720p · 60 FPS'}.get(saved_profile, saved_profile)
        self.profile_combo.setCurrentText(saved_profile)
        self.profile_combo.activated.connect(self._profile_chosen)
        self.device_combo = QComboBox()
        self.format_combo = QComboBox()
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("Primary")
        self.shot_btn = QPushButton("Screenshot")
        self.rec_btn = QPushButton("Record")
        self.full_btn = QPushButton("Fullscreen")
        self.more_btn = QPushButton("Options")
        self.more_btn.setCheckable(True)
        self.shot_btn.setToolTip("F12")
        self.rec_btn.setToolTip("Ctrl+R")
        self.full_btn.setToolTip("F11")

        self.audio_check = QCheckBox("Audio")
        self.audio_check.setChecked(self.settings.value("capture/audio", True, type=bool))
        self.audio_combo = QComboBox()
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(self.settings.value("capture/volume", 100)))
        self.volume.setFixedWidth(110)
        self.audio_out.setVolume(self.volume.value() / 100)
        self.fit_combo = QComboBox()
        self.fit_combo.addItems(FIT_MODES)
        self.fit_combo.setCurrentIndex(int(self.settings.value("capture/fit2", FIT)))
        self.aspect_combo = QComboBox()
        for label, _v in ASPECTS:
            self.aspect_combo.addItem(label)
        self.aspect_combo.setCurrentIndex(int(self.settings.value("capture/aspect", 0)))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(100, 140)
        self.zoom_slider.setValue(int(self.settings.value("capture/zoom", 100)))
        self.zoom_slider.setFixedWidth(110)
        self.zoom_label = QLabel()
        self.zoom_label.setMinimumWidth(40)
        self.refresh_btn = QPushButton("Refresh devices")
        self.folder_btn = QPushButton("Open captures folder")
        self.output_btn = QPushButton("Save location…")
        self.output_btn.clicked.connect(self._choose_output)

        self.status = QLabel("Pick your capture card and press Start.")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        self.stats = QLabel("")
        self.stats.setWordWrap(False)
        self.stats.setMinimumWidth(230)
        self.stats.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        for combo in (self.profile_combo,self.device_combo,self.format_combo,self.audio_combo):
            combo.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
            combo.setMinimumWidth(100)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10)
        self.controls=QFrame(); self.controls.setObjectName('Card')
        cl=QVBoxLayout(self.controls); cl.setContentsMargins(12,10,12,10); cl.setSpacing(8)
        grid=QGridLayout()
        for col,(label,control) in enumerate((('Capture source',self.device_combo),('Resolution',self.profile_combo))):
            grid.addWidget(QLabel(label),0,col); grid.addWidget(control,1,col); grid.setColumnStretch(col,1)
        cl.addLayout(grid)
        actions=QHBoxLayout()
        for button in (self.start_btn,self.shot_btn,self.rec_btn,self.full_btn,self.more_btn): actions.addWidget(button)
        cl.addLayout(actions)
        self.options=QDialog(self); self.options.setWindowTitle('Ascend • Capture options')
        self.options.resize(580,520); self.options.setMinimumSize(420,340)
        ol=QVBoxLayout(self.options)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); ol.addWidget(scroll)
        fields=QWidget(); scroll.setWidget(fields); form=QFormLayout(fields)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        for label,control in (('Advanced driver mode',self.format_combo),('Capture audio',self.audio_check),('Audio device',self.audio_combo),('Monitor volume',self.volume),('Picture fit',self.fit_combo),('Aspect ratio',self.aspect_combo),('Zoom',self.zoom_slider),('Zoom level',self.zoom_label)):
            form.addRow(label,control)
        form.addRow(self.refresh_btn); form.addRow(self.folder_btn); form.addRow(self.output_btn)
        reset=QPushButton('Reset picture to fit'); reset.clicked.connect(self.reset_picture); form.addRow(reset)
        diagnostics=QPushButton('Copy device diagnostics'); diagnostics.clicked.connect(self.copy_diagnostics); form.addRow(diagnostics)
        hint=QLabel('Fit shows the entire picture. Fill and zoom crop inside the viewer; controls stay outside it. Advanced driver modes show the formats reported by your card. Resolution presets select the closest supported mode, up to 60 FPS.')
        hint.setWordWrap(True); form.addRow(hint)
        close=QPushButton('Done'); close.clicked.connect(self.options.close); ol.addWidget(close)
        self.options.finished.connect(lambda _:self.more_btn.setChecked(False))
        self.info_bar = QWidget()
        info = QHBoxLayout(self.info_bar)
        info.setContentsMargins(4, 0, 4, 0)
        info.addWidget(self.status, 1)
        info.addWidget(self.stats)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.controls)
        layout.addWidget(self.stage, 1)
        layout.addWidget(self.info_bar)

        # ---- wiring ----
        self.device_combo.activated.connect(self._device_chosen)
        self.format_combo.activated.connect(self._manual_format_chosen)
        self.audio_combo.activated.connect(self._audio_changed)
        self.audio_check.toggled.connect(self._audio_changed)
        self.volume.valueChanged.connect(self._volume_changed)
        self.fit_combo.currentIndexChanged.connect(self._apply_view)
        self.aspect_combo.currentIndexChanged.connect(self._apply_view)
        self.zoom_slider.valueChanged.connect(self._apply_view)
        self.more_btn.toggled.connect(self._toggle_options)
        self.start_btn.clicked.connect(self._toggle)
        self.full_btn.clicked.connect(self.fullscreen_requested.emit)
        self.shot_btn.clicked.connect(self.screenshot)
        self.rec_btn.clicked.connect(self.toggle_record)
        self.folder_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(captures_dir())))
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.recorder.recorderStateChanged.connect(self._recorder_state)
        self.recorder.errorOccurred.connect(
            lambda _e, msg: self.status.setText("Recording error: " + msg))

        # Windows can fire several device-change notifications in a row; wait for them
        # to settle, and only refresh the lists (never restart a running capture).
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(1500)
        self.debounce.timeout.connect(self.refresh_devices)
        self.media_devices.videoInputsChanged.connect(self.debounce.start)
        self.media_devices.audioInputsChanged.connect(self.debounce.start)

        self.stats_timer = QTimer(self)
        self.stats_timer.timeout.connect(self._update_stats)
        self.stats_timer.start(1000)
        self.stall_timer = QTimer(self)
        self.stall_timer.timeout.connect(self._check_stall)
        self.stall_timer.start(1000)

        self._apply_view()
        self.refresh_devices()
        if self.settings.value("capture/autostart", False, type=bool) and \
                self.device_combo.count():
            QTimer.singleShot(300, self.start)

    # ---------- device discovery ----------
    def refresh_devices(self):
        """Refresh device lists. Never restarts a running capture."""
        running_id = self.camera.cameraDevice().id() if self.camera else None
        saved_id = self.settings.value("capture/device", b"")
        keep_id = running_id or (self.device_combo.currentData().id()
                                 if self.device_combo.currentData() else saved_id)

        devices = QMediaDevices.videoInputs()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        best = 0
        for i, dev in enumerate(devices):
            self.device_combo.addItem(dev.description(), dev)
            name = dev.description().lower()
            if keep_id and dev.id() == keep_id:
                best = i
            elif not keep_id and any(h in name for h in CAPTURE_HINTS) \
                    and "webcam" not in name and "integrated" not in name:
                best = i
        if devices:
            self.device_combo.setCurrentIndex(best)
        self.device_combo.blockSignals(False)

        current_audio = self.audio_combo.currentText()
        self.audio_combo.blockSignals(True)
        self.audio_combo.clear()
        for dev in QMediaDevices.audioInputs():
            self.audio_combo.addItem(dev.description(), dev)
        self.audio_combo.blockSignals(False)

        if running_id and not any(d.id() == running_id for d in devices):
            self.stop()
            self.status.setText("The capture card was unplugged or reset. Plug it back in "
                                "and press Start.")
        if not devices:
            self.format_combo.clear()
            self.status.setText("No capture card found. Plug it in and press Refresh devices.")
            return
        if self.camera is None:
            self._load_formats()
        elif current_audio:
            i = self.audio_combo.findText(current_audio)
            if i >= 0:
                self.audio_combo.setCurrentIndex(i)

    def _pick_audio_for(self, video_name):
        saved = self.settings.value("capture/audio_device", "")
        i = self.audio_combo.findText(saved) if saved else -1
        if i >= 0:
            self.audio_combo.setCurrentIndex(i)
            return
        video_words = {w for w in video_name.lower().split() if len(w) > 2}
        best_i, best_score = -1, 0
        for i in range(self.audio_combo.count()):
            name = self.audio_combo.itemText(i).lower()
            score = len(video_words & set(name.split())) * 2
            score += sum(1 for h in CAPTURE_HINTS if h in name)
            if "microphone array" in name or "realtek" in name:
                score -= 3
            if score > best_score:
                best_i, best_score = i, score
        if best_i >= 0:
            self.audio_combo.setCurrentIndex(best_i)

    def _load_formats(self):
        dev = self.device_combo.currentData()
        if dev is None:
            return
        prefer_mjpeg = self.settings.value("capture/prefer_mjpeg", False, type=bool)
        unique = {describe_format(fmt): fmt for fmt in dev.videoFormats() if 0 < fmt.maxFrameRate() <= 60.01}
        self.formats = sorted(unique.values(),
                              key=lambda f: format_score(f, prefer_mjpeg), reverse=True)
        saved = self.settings.value("capture/format", "")
        self.format_combo.clear()
        pick = 0
        for i, fmt in enumerate(self.formats):
            label = describe_format(fmt)
            if label == saved:
                pick = i
            self.format_combo.addItem(label, fmt)
        if not self.settings.value('capture/manual_mode', False, type=bool) and self.formats:
            pick = self._profile_index()
        self.format_combo.setCurrentIndex(pick)
        self._pick_audio_for(dev.description())
        if self.formats:
            best = self.formats[pick]
            notes = []
            if best.maxFrameRate() < 59:
                notes.append("no 60 fps mode reported")
            if not is_widescreen(best.resolution()):
                notes.append("no 16:9 mode reported, use Options > Shape to correct the proportions")
            self.status.setText("Available mode for {}: {}.{}".format(
                dev.description(), describe_format(best),
                ("  (" + "; ".join(notes) + ")") if notes else ""))

    def _choose_output(self):
        path = QFileDialog.getExistingDirectory(self, 'Save captures to', captures_dir())
        if path:
            self.settings.setValue('capture/output', path)
            self.status.setText('Capture folder: ' + path)

    def _profile_index(self):
        width, height, fps = {
            '1080p · 60 FPS': (1920, 1080, 60),
            '1440p · 60 FPS': (2560, 1440, 60),
            '4K · 60 FPS': (3840, 2160, 60),
            '720p · 60 FPS': (1280, 720, 60),
        }.get(self.profile_combo.currentText(), (1920, 1080, 60))
        def score(i):
            fmt = self.formats[i]; size = fmt.resolution()
            return (abs(size.width()-width)+abs(size.height()-height), abs(fmt.maxFrameRate()-fps), not is_widescreen(size), -int(format_score(fmt,self.settings.value("capture/prefer_mjpeg",False,type=bool))[-1]))
        return min(range(len(self.formats)), key=score)

    def _profile_chosen(self):
        self.settings.setValue('capture/manual_mode', False)
        self.settings.setValue('capture/profile', self.profile_combo.currentText())
        if self.formats and not self.settings.value('capture/manual_mode', False, type=bool):
            self.format_combo.setCurrentIndex(self._profile_index())
            self._format_chosen()
            self.status.setText('Closest driver mode: ' + self.format_combo.currentText())

    def _device_chosen(self):
        dev = self.device_combo.currentData()
        if dev is not None:
            self.settings.setValue("capture/device", dev.id())
            self.settings.setValue("capture/format", "")
        was_running = self.camera is not None
        self.stop()
        self._load_formats()
        if was_running:
            self.start()

    def _manual_format_chosen(self):
        self.settings.setValue('capture/manual_mode', True)
        self._format_chosen()

    def _format_chosen(self):
        fmt = self.format_combo.currentData()
        if fmt is not None:
            self.settings.setValue("capture/format", describe_format(fmt))
        if self.camera is not None:
            self.start()

    def _audio_changed(self):
        self.settings.setValue("capture/audio", self.audio_check.isChecked())
        self.settings.setValue("capture/audio_device", self.audio_combo.currentText())
        if self.camera is not None:
            self._apply_audio()

    def _volume_changed(self, v):
        self.audio_out.setVolume(v / 100)
        self.settings.setValue("capture/volume", v)

    def _toggle_options(self,on):
        if on:
            self.options.show(); self.options.raise_(); self.options.activateWindow()
        else:
            self.options.close()

    def reset_picture(self):
        self.fit_combo.setCurrentIndex(FIT); self.aspect_combo.setCurrentIndex(0); self.zoom_slider.setValue(100)

    def copy_diagnostics(self):
        from PySide6.QtWidgets import QApplication
        dev=self.device_combo.currentData()
        lines=['Ascend capture diagnostics','Device: '+(dev.description() if dev else 'None'),'Selected: '+self.format_combo.currentText(),'Qt backend: '+os.environ.get('QT_MEDIA_BACKEND','Auto'),'Audio: '+self.audio_combo.currentText(),'Driver modes:']
        lines.extend(describe_format(f) for f in self.formats)
        QApplication.clipboard().setText('\n'.join(lines))
        self.status.setText('Device diagnostics copied to clipboard.')

    def _apply_view(self):
        fit = self.fit_combo.currentIndex()
        aspect = self.aspect_combo.currentIndex()
        zoom = self.zoom_slider.value()
        self.stage.configure(mode=fit, aspect=ASPECTS[aspect][1], zoom=zoom / 100)
        self.zoom_label.setText("{}%".format(zoom))
        self.settings.setValue("capture/fit2", fit)
        self.settings.setValue("capture/aspect", aspect)
        self.settings.setValue("capture/zoom", zoom)

    # ---------- start / stop ----------
    def _toggle(self):
        if self.camera is None:
            self.start()
        else:
            self.stop()

    def start(self):
        self.stop()
        dev = self.device_combo.currentData()
        if dev is None:
            self.status.setText("No capture card selected.")
            return
        if not self.formats:
            self.status.setText("This driver exposes no capture mode at or below 60 fps. Choose another device or backend.")
            return
        self.camera = QCamera(dev, self)
        fmt = self.format_combo.currentData()
        if fmt is not None:
            self.camera.setCameraFormat(fmt)
            self.stage.configure(source=(fmt.resolution().width(), fmt.resolution().height()))
        self.camera.errorOccurred.connect(self._camera_error)
        self.session.setCamera(self.camera)
        self._apply_audio()
        self.last_tick = time.monotonic()
        self.capture_started = self.last_tick
        self.camera.start()
        self.frame_clock.invalidate()
        self.start_btn.setText("Stop")
        self.status.setText("Starting capture: {}  {}".format(
            dev.description(), describe_format(fmt) if fmt else ""))

    def _apply_audio(self):
        self.session.setAudioInput(None)
        self.session.setAudioOutput(None)
        if self.audio_in is not None:
            self.audio_in.deleteLater()
        self.audio_in = None
        adev = self.audio_combo.currentData()
        if self.audio_check.isChecked() and adev is not None:
            self.audio_in = QAudioInput(adev, self)
            self.session.setAudioInput(self.audio_in)
            self.session.setAudioOutput(self.audio_out)

    def stop(self):
        if self.recorder.recorderState() != QMediaRecorder.StoppedState:
            self.recorder.stop()
        if self.camera is not None:
            self.camera.stop()
            self.session.setCamera(None)
            self.session.setAudioInput(None)
            self.session.setAudioOutput(None)
            self.camera.deleteLater()
            self.camera = None
            if self.audio_in is not None:
                self.audio_in.deleteLater()
            self.audio_in = None
        self.last_size = None
        self.frames = 0
        self.frame_clock.invalidate()
        self.empty.show()
        self.empty.raise_()
        self.start_btn.setText("Start")
        self.stats.setText("")

    def _camera_error(self, _error, message):
        self.status.setText("Capture error: {}. Close OBS or any other app using the "
                            "card, or pick a lower mode.".format(message))

    # ---------- lightweight capture status ----------
    def _on_frame(self, frame):
        if not frame.isValid():
            return
        if self.last_size is None:
            self.status.setText("Receiving video from " + self.device_combo.currentText())
        if not self.empty.isHidden(): self.empty.hide()
        self.frames += 1
        self.frame_clock.restart()
        size = frame.size()
        key = (size.width(), size.height())
        if key != self.last_size and size.height() > 0:
            self.last_size = key
            self.stage.configure(source=key)  # follow the real picture size

    def _check_stall(self):
        if self.camera is not None and not self.frame_clock.isValid() and time.monotonic() - self.capture_started > 5:
            self.status.setText("Waiting for video. Check HDMI, HDCP and other apps using the card.")
        if self.camera is None or not self.frame_clock.isValid():
            return

    def health_snapshot(self):
        device=self.device_combo.currentData(); audio=self.audio_combo.currentData(); fmt=self.format_combo.currentData()
        matching=audio and any(h in audio.description().lower() for h in CAPTURE_HINTS)
        signal='Preview stopped — press Start to check the video signal'
        if self.camera:
            signal='Waiting for HDMI video — check console output / HDCP'
            if self.last_size and self.frame_clock.isValid() and self.frame_clock.elapsed()<2000:
                signal='Video signal detected · {} × {}'.format(*self.last_size)
        return {'device':('Detected · '+device.description()) if device else 'No capture device detected',
                'audio':('Audio input available · '+audio.description()) if matching else 'No matching card audio input detected — select it in Capture Options',
                'mode':('Driver mode · '+describe_format(fmt)) if fmt else 'No supported capture mode detected', 'signal':signal}

    def _update_stats(self):
        health=self.health_snapshot()
        if health != getattr(self,'_last_health',None):
            self._last_health=health; self.health_changed.emit(health)

        now = time.monotonic()
        elapsed = now - self.last_tick
        if self.camera is not None and elapsed > 0 and self.last_size:
            text = "{} × {}   ·   {:.0f} FPS".format(
                self.last_size[0], self.last_size[1], self.frames / elapsed)
            if self.recorder.recorderState() == QMediaRecorder.RecordingState:
                secs = int(now - self.record_started)
                text += "   REC {:02d}:{:02d}".format(secs // 60, secs % 60)
            self.stats.setText(text)
        self.frames = 0
        self.last_tick = now

    # ---------- screenshot / record ----------
    def screenshot(self):
        frame = self.video.videoSink().videoFrame()
        if not frame.isValid():
            self.status.setText("Nothing to screenshot yet. Press Start first.")
            return
        path = os.path.join(captures_dir(), str(self.settings.value("console/type", "PS5")) + time.strftime("_%Y-%m-%d_%H-%M-%S") + "_" + str(time.time_ns())[-6:] + ".png")
        if frame.toImage().save(path):
            self.status.setText("Screenshot saved: " + path)
        else:
            self.status.setText("Screenshot save failed. Check folder permissions and disk space.")

    def toggle_record(self):
        if self.recorder.recorderState() == QMediaRecorder.RecordingState:
            self.recorder.stop()
            return
        if self.camera is None:
            self.status.setText("Press Start before recording.")
            return
        fmt = QMediaFormat(QMediaFormat.MPEG4)
        fmt.setVideoCodec(QMediaFormat.VideoCodec.H264)
        fmt.setAudioCodec(QMediaFormat.AudioCodec.AAC)
        self.recorder.setMediaFormat(fmt)
        self.recorder.setQuality(QMediaRecorder.VeryHighQuality)
        cam_fmt = self.camera.cameraFormat()
        if not cam_fmt.isNull():
            self.recorder.setVideoFrameRate(min(60.0,cam_fmt.maxFrameRate()))
            self.recorder.setVideoResolution(cam_fmt.resolution())
        path = os.path.join(captures_dir(), str(self.settings.value("console/type", "PS5")) + time.strftime("_%Y-%m-%d_%H-%M-%S") + "_" + str(time.time_ns())[-6:] + ".mp4")
        self.recorder.setOutputLocation(QUrl.fromLocalFile(path))
        self.recorder.record()

    def _recorder_state(self, state):
        stopped = state == QMediaRecorder.StoppedState
        for control in (self.device_combo, self.format_combo, self.profile_combo, self.start_btn, self.audio_check, self.audio_combo):
            control.setEnabled(stopped)
        if state == QMediaRecorder.RecordingState:
            self.record_started = time.monotonic()
            self.rec_btn.setText("Stop recording")
            self.rec_btn.setObjectName("Danger")
            self.status.setText("Recording...")
        else:
            self.rec_btn.setText("Record")
            self.rec_btn.setObjectName("")
            loc = self.recorder.actualLocation().toLocalFile()
            if loc:
                self.status.setText("Recording saved: " + loc)
        self.rec_btn.style().unpolish(self.rec_btn)
        self.rec_btn.style().polish(self.rec_btn)

    # ---------- cinema mode (called by the main window) ----------
    def set_cinema(self, on):
        self.controls.setVisible(True)
        self.info_bar.setVisible(True)
        self.video.setCursor(Qt.ArrowCursor)

    def shutdown(self):
        self.options.close()
        self.stop()
