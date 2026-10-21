"""Embedded existing LAN manager; no proxy, server or port changes."""
from PySide6.QtCore import QSettings, QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QApplication, QFileDialog, QComboBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings

class WebManagerTab(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('AscendToolkit', 'AscendToolkit')
        self.loaded = False
        self.loading = False
        layout = QVBoxLayout(self)
        title = QLabel('Web Payload Manager'); title.setObjectName('PageTitle'); layout.addWidget(title)
        row = QHBoxLayout()
        self.address = QLineEdit(self.settings.value('webmanager/url', ''))
        self.address.setPlaceholderText('Manager address, e.g. http://console-host:8084/')
        row.addWidget(self.address, 1)
        go = QPushButton("Connect"); go.clicked.connect(self.connect_manager); row.addWidget(go)
        layout.addLayout(row)
        actions = QHBoxLayout()
        for text, callback in (('Reload', self.reload), ('Copy phone link', self.copy_link), ('Open browser', self.open_browser)):
            button = QPushButton(text); button.clicked.connect(callback); actions.addWidget(button)
        actions.addStretch(); layout.addLayout(actions)
        self.status = QLabel('Connect to your console’s web manager. Use the same address on your phone while connected to the same network.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.browser = QWebEngineView()
        self.private_profile = QWebEngineProfile(self)
        self.private_profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        self.browser.setPage(QWebEnginePage(self.private_profile,self.browser))
        self.browser.settings().setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, False)
        self.browser.page().setBackgroundColor(self.palette().window().color())
        self.browser.loadStarted.connect(self.started)
        self.browser.page().renderProcessTerminated.connect(self.renderer_failed)
        layout.addWidget(self.browser, 1)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel('Page zoom'))
        self.zoom = QComboBox(); self.zoom.addItems(['65%','75%','85%','100%','125%','150%'])
        self.zoom.setCurrentText(self.settings.value('webmanager/zoom','85%'))
        zoom_row.addWidget(self.zoom); zoom_row.addStretch()
        layout.insertLayout(2,zoom_row)
        self.zoom.currentTextChanged.connect(self.set_zoom)
        self.set_zoom(self.zoom.currentText())
        self.browser.page().profile().downloadRequested.connect(self.download)
        self.browser.loadFinished.connect(self.finished)
        self.address.returnPressed.connect(self.connect_manager)

    def target(self):
        if not self.address.text().strip():
            self.status.setText("Enter your own manager address to connect.")
            return None
        url = QUrl.fromUserInput(self.address.text().strip())
        if url.scheme() not in ('http', 'https') or not url.host():
            self.status.setText('Enter a valid http:// or https:// manager URL.')
            return None
        return url

    def showEvent(self, event):
        super().showEvent(event)
        if not self.loaded and self.address.text().strip():
            self.loaded = True
            QTimer.singleShot(0, self.connect_manager)

    def started(self):
        self.loading = True

    def renderer_failed(self, status, code):
        self.loading = False
        self.status.setText("Web Manager stopped responding. Press Reload to reconnect.")

    def connect_manager(self):
        url = self.target()
        if url:
            if self.loaded and self.browser.url() == url:
                if not self.loading:
                    self.status.setText('Connected • ' + url.toString())
                return
            self.loaded = True
            self.settings.setValue('webmanager/url', url.toString())
            self.status.setText('Connecting to ' + url.toString())
            self.browser.setUrl(url)

    def finished(self, ok):
        self.loading = False
        self.status.setText('Connected • ' + self.browser.url().toString() if ok else 'Could not load manager. Check the console/server is running and this PC can reach it. Try Open browser.')

    def reload(self):
        if self.loaded: self.browser.reload()
        else: self.connect_manager()

    def copy_link(self):
        url = self.target()
        if url:
            QApplication.clipboard().setText(url.toString())
            self.status.setText('Link copied. Open it on a phone on the same reachable network.')

    def open_browser(self):
        url = self.target()
        if url: QDesktopServices.openUrl(url)

    def set_zoom(self,text):
        self.browser.setZoomFactor(int(text.rstrip('%'))/100)
        self.settings.setValue('webmanager/zoom',text)

    def download(self,request):
        from pathlib import Path
        path,_=QFileDialog.getSaveFileName(self,'Save manager download',request.downloadFileName())
        if path:
            request.setDownloadDirectory(str(Path(path).parent))
            request.setDownloadFileName(Path(path).name)
            request.accept()
        else:
            request.cancel()

    def shutdown(self):
        self.browser.stop()
