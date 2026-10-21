"""Local music queue with independent output and persistent playlist."""
from pathlib import Path
import random
from PySide6.QtCore import QSettings, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel, QSlider, QFileDialog, QCheckBox, QComboBox, QTabWidget, QLineEdit

def clock(ms):
    seconds = max(0, ms // 1000)
    return f'{seconds//60:02d}:{seconds%60:02d}'

class LocalMusicTab(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('AscendToolkit', 'AscendToolkit')
        self.paths = list(self.settings.value('music/queue', [], type=list))
        self.index = -1
        self.player = QMediaPlayer(self); self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        layout = QVBoxLayout(self)
        title = QLabel('Ascend Music'); title.setObjectName('PageTitle'); layout.addWidget(title)
        subtitle = QLabel('Your soundtrack while you play. Music volume is separate from capture audio.')
        subtitle.setWordWrap(True); layout.addWidget(subtitle)
        row = QHBoxLayout()
        for text, callback in (('Add tracks', self.add), ('Remove selected', self.remove), ('Clear queue', self.clear)):
            button = QPushButton(text); button.clicked.connect(callback); row.addWidget(button)
        row.addStretch(); layout.addLayout(row)
        self.queue = QListWidget(); layout.addWidget(self.queue, 1)
        self.now = QLabel('Choose a track to get started.'); self.now.setWordWrap(True); layout.addWidget(self.now)
        self.seek = QSlider(Qt.Horizontal); self.seek.setRange(0, 0); layout.addWidget(self.seek)
        self.time = QLabel('00:00 / 00:00'); layout.addWidget(self.time)
        transport = QHBoxLayout()
        for text, callback in (('Previous', self.previous), ('Play / Pause', self.toggle), ('Stop', self.player.stop), ('Next', self.next)):
            button = QPushButton(text); button.clicked.connect(callback); transport.addWidget(button)
        self.shuffle = QCheckBox('Shuffle'); self.repeat = QCheckBox('Repeat queue')
        transport.addStretch()
        layout.addLayout(transport)
        volume_row = QHBoxLayout(); volume_row.addWidget(self.shuffle); volume_row.addWidget(self.repeat); volume_row.addSpacing(12); volume_row.addWidget(QLabel('Volume'))
        self.volume = QSlider(Qt.Horizontal); self.volume.setRange(0,100); self.volume.setValue(int(self.settings.value('music/volume',40)))
        self.volume.setMaximumWidth(160); volume_row.addWidget(self.volume); volume_row.addStretch(); layout.addLayout(volume_row)
        devices = QHBoxLayout(); devices.addWidget(QLabel('Playback output'))
        self.devices = QComboBox(); devices.addWidget(self.devices,1); layout.addLayout(devices)
        self.media = QMediaDevices(self); self.media.audioOutputsChanged.connect(self.refresh_outputs)
        self.devices.activated.connect(self.change_output); self.refresh_outputs()
        self.volume.valueChanged.connect(self.set_volume); self.set_volume(self.volume.value())
        self.queue.itemDoubleClicked.connect(lambda item: self.play(self.queue.row(item)))
        self.player.positionChanged.connect(self.position)
        self.player.durationChanged.connect(lambda duration: self.seek.setRange(0,duration))
        self.seek.sliderMoved.connect(self.player.setPosition)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.errorOccurred.connect(lambda error, message: self.now.setText('Playback error: '+message))
        self.render()

    def refresh_outputs(self):
        old = self.devices.currentData()
        keep = old.id() if old else self.settings.value('music/device', QMediaDevices.defaultAudioOutput().id())
        self.devices.clear()
        for d in QMediaDevices.audioOutputs(): self.devices.addItem(d.description(),d)
        for i in range(self.devices.count()):
            if keep and self.devices.itemData(i).id()==keep: self.devices.setCurrentIndex(i)
        self.change_output()

    def change_output(self):
        device = self.devices.currentData()
        if device:
            self.output.setDevice(device)
            self.settings.setValue('music/device',device.id())

    def set_volume(self, value):
        self.output.setVolume(value/100); self.settings.setValue('music/volume',value)

    def render(self):
        self.queue.clear(); self.queue.addItems([Path(p).name for p in self.paths])
        self.settings.setValue('music/queue',self.paths)
        if 0 <= self.index < len(self.paths): self.queue.setCurrentRow(self.index)

    def add(self):
        paths, _ = QFileDialog.getOpenFileNames(self,'Add music','','Audio (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus);;All files (*)')
        self.paths.extend(p for p in paths if p not in self.paths); self.render()

    def play(self, index):
        if not 0 <= index < len(self.paths): return
        if not Path(self.paths[index]).is_file():
            self.now.setText('File missing: '+self.paths[index]); return
        self.index=index; self.queue.setCurrentRow(index)
        self.player.setSource(QUrl.fromLocalFile(self.paths[index])); self.player.play()
        self.now.setText('Now playing • '+Path(self.paths[index]).name)

    def toggle(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState: self.player.pause()
        elif self.index>=0 and not self.player.source().isEmpty(): self.player.play()
        elif self.paths: self.play(max(0,self.queue.currentRow()))

    def next(self):
        if not self.paths: return
        if self.shuffle.isChecked() and len(self.paths)>1:
            self.play(random.choice([i for i in range(len(self.paths)) if i!=self.index]))
        elif self.index+1 < len(self.paths): self.play(self.index+1)
        elif self.repeat.isChecked(): self.play(0)
        else: self.player.stop()

    def previous(self):
        if self.player.position()>3000: self.player.setPosition(0)
        elif self.paths: self.play(max(0,self.index-1))

    def media_status(self, status):
        if status==QMediaPlayer.EndOfMedia: self.next()

    def position(self, ms):
        if not self.seek.isSliderDown(): self.seek.setValue(ms)
        self.time.setText(clock(ms)+' / '+clock(self.player.duration()))

    def remove(self):
        row=self.queue.currentRow()
        if row<0: return
        if row==self.index: self.player.stop(); self.player.setSource(QUrl()); self.index=-1
        elif row<self.index: self.index-=1
        self.paths.pop(row); self.render()

    def clear(self):
        self.player.stop(); self.player.setSource(QUrl()); self.paths=[]; self.index=-1; self.render()
        self.now.setText('Queue cleared.')

    def shutdown(self):
        self.player.stop()


class MusicTab(QWidget):
    """Online sources are loaded only when the customer opens them."""
    def __init__(self):
        super().__init__()
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.local = LocalMusicTab()
        self.tabs.addTab(self.local, 'Your music')
        online = QWidget(); ol = QVBoxLayout(online)
        title = QLabel('ListenFree'); title.setObjectName('PageTitle'); ol.addWidget(title)
        note = QLabel('Listen through the ListenFree website. Availability and playback are provided by that service.')
        note.setWordWrap(True); note.setObjectName('Muted'); ol.addWidget(note)
        row = QHBoxLayout()
        for label,callback in (('Reload', self.reload_online), ('Pause audio', self.stop_online)):
            button=QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        row.addStretch(); ol.addLayout(row)
        self.online_status=QLabel('Connects only when you open this tab.'); self.online_status.setWordWrap(True); ol.addWidget(self.online_status)
        self.codec_supported=None
        self.web=QWebEngineView()
        self.private_profile=QWebEngineProfile(self)
        self.private_profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        self.web.setPage(QWebEnginePage(self.private_profile,self.web))
        self.install_native_audio()
        self.web.loadStarted.connect(self.native_audio.reset)
        self.web.loadFinished.connect(self.online_finished)
        volume_row=QHBoxLayout(); volume_row.addWidget(QLabel('ListenFree volume'))
        self.online_volume=QSlider(Qt.Horizontal); self.online_volume.setRange(0,100)
        self.online_volume.setValue(self.local.volume.value()); self.online_volume.setMaximumWidth(200)
        self.online_volume.valueChanged.connect(self.native_audio.set_master)
        self.native_audio.set_master(self.online_volume.value())
        volume_row.addWidget(self.online_volume); volume_row.addStretch(); ol.addLayout(volume_row)

        ol.addWidget(self.web,1)
        self.tabs.addTab(online,'ListenFree')
        spotify=QWidget(); sl=QVBoxLayout(spotify)
        heading=QLabel('Your Spotify, in your browser'); heading.setObjectName('PageTitle'); sl.addWidget(heading)
        desc=QLabel('Open Spotify or paste a Spotify track, album or playlist link. Sign in using your own browser. Ascend does not receive your Spotify password or store account tokens.')
        desc.setWordWrap(True); sl.addWidget(desc)
        self.spotify_link=QLineEdit(); self.spotify_link.setPlaceholderText('https://open.spotify.com/… (optional)'); sl.addWidget(self.spotify_link)
        button=QPushButton('Open Spotify'); button.clicked.connect(self.open_spotify); sl.addWidget(button)
        self.spotify_status=QLabel('Local files and ListenFree remain available without a Spotify connection.')
        self.spotify_status.setWordWrap(True); self.spotify_status.setObjectName('Muted'); sl.addWidget(self.spotify_status); sl.addStretch()
        self.tabs.addTab(spotify,'Spotify')
        layout.addWidget(self.tabs)
        self.online_loaded=False
        self.tabs.currentChanged.connect(self.source_changed)

    def source_changed(self,index):
        self.native_audio.set_enabled(index==1)
        self.web.page().setAudioMuted(True)
        if index!=0: self.local.player.pause()
        if index==1 and not self.online_loaded:
            self.online_loaded=True
            self.web.setUrl(QUrl('https://listenfree.in/'))
            self.online_status.setText('Connecting to ListenFree…')

    def reload_online(self):
        self.online_loaded=True
        self.web.setUrl(QUrl('https://listenfree.in/'))

    def install_native_audio(self):
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineCore import QWebEngineScript
        from PySide6.QtCore import QFile, QIODevice
        from native_audio import NativeAudioBridge
        from brand import asset
        self.native_audio=NativeAudioBridge(self.web.page(),self)
        self.native_audio.status.connect(self.online_status.setText)
        self.channel=QWebChannel(self.web.page())
        self.channel.registerObject('ascendAudio',self.native_audio)
        self.web.page().setWebChannel(self.channel)
        channel_file=QFile(':/qtwebchannel/qwebchannel.js')
        if not channel_file.open(QIODevice.ReadOnly):
            raise RuntimeError('Qt WebChannel resource is unavailable')
        channel_js=bytes(channel_file.readAll()).decode('utf-8')
        script=QWebEngineScript()
        script.setName('Ascend native ListenFree audio')
        script.setInjectionPoint(QWebEngineScript.DocumentCreation)
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(channel_js+'\n'+Path(asset('native-audio.js')).read_text(encoding='utf-8'))
        self.web.page().scripts().insert(script)
        self.local.devices.currentIndexChanged.connect(self.sync_online_device)
        self.sync_online_device()

    def sync_online_device(self):
        device=self.local.devices.currentData()
        if device: self.native_audio.set_device(device)

    def online_finished(self,ok):
        if not ok:
            self.online_status.setText('ListenFree could not load. Try Reload. Your local music still works.')
            return
        self.web.page().runJavaScript(
            'Boolean(window.__ascendNativeAudio && window.__ascendNativeAudio.ready)',
            self.native_ready)

    def native_ready(self,ready):
        self.online_status.setText('Ready • select a song. Audio plays inside Ascend.' if ready else
                                   'Native audio connection not ready. Try Reload.')

    def stop_online(self):
        self.native_audio.set_enabled(False)
        self.online_status.setText('Audio paused. Press Play on a song to resume.')
        self.native_audio.set_enabled(self.tabs.currentIndex()==1)

    def open_spotify(self):
        text=self.spotify_link.text().strip() or 'https://open.spotify.com/'
        url=QUrl.fromUserInput(text)
        host=url.host().lower()
        if url.scheme()!='https' or not (host=='spotify.com' or host.endswith('.spotify.com')):
            self.spotify_status.setText('Use an https:// Spotify link.')
            return
        self.local.player.pause(); self.native_audio.set_enabled(False); self.web.page().setAudioMuted(True)
        QDesktopServices.openUrl(url)
        self.spotify_status.setText('Opened in your browser. No Spotify account data is saved by Ascend.')

    def shutdown(self):
        self.local.shutdown(); self.native_audio.set_enabled(False); self.native_audio.reset(); self.web.page().setAudioMuted(True); self.web.stop()
