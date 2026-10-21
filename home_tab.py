"""Console profiles, onboarding and capture setup."""
import json
from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from brand import asset
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QFormLayout, QGroupBox, QCheckBox, QPushButton, QScrollArea, QComboBox, QDialog, QDialogButtonBox

from console_catalog import ConsolePicker, SOURCES

class HomeTab(QWidget):
    host_changed=Signal(str)
    profile_changed=Signal()
    def __init__(self,theme):
        super().__init__()
        self.settings=QSettings('AscendToolkit','AscendToolkit')
        layout=QVBoxLayout(self)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll)
        content=QWidget(); scroll.setWidget(content); body=QVBoxLayout(content); body.setContentsMargins(24,20,24,28); body.setSpacing(24)
        title=QLabel('YOUR CONSOLE. YOUR CHOICE.'); title.setObjectName('PageTitle'); body.addWidget(title)
        sub=QLabel('Capture your gameplay. Organise your payloads. Make it yours.'); sub.setWordWrap(True); body.addWidget(sub)
        box=QGroupBox('Console profile'); form=QFormLayout(box); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow); form.setContentsMargins(20,26,20,20); form.setVerticalSpacing(16); form.setHorizontalSpacing(24)
        self.picker=ConsolePicker(self.settings.value('console/type','PS5'))
        self.console=self.picker.console; self.firmware=self.picker.firmware; self.loader=self.picker.environment
        self.nickname=QLineEdit()
        self.host=QLineEdit(); self.host.setPlaceholderText('Optional console IP or hostname')
        form.addRow(self.picker)
        form.addRow(self.field('Name', self.nickname)); form.addRow(self.field('Console IP',self.host))
        save=QPushButton('Save console profile'); save.setObjectName('Primary'); save.clicked.connect(self.save); form.addRow(save)
        self.message=QLabel('Your profile keeps console, firmware and connection details together.')
        self.message.setWordWrap(True); form.addRow(self.message); body.addWidget(box)
        self.active=self.console.currentText(); self.load_profile(self.active)
        self.console.currentTextChanged.connect(self.switch_profile)
        guide=QGroupBox('Capture setup'); tips=QVBoxLayout(guide)
        self.console_tip=QLabel(); self.console_tip.setWordWrap(True); tips.addWidget(self.console_tip)
        self.update_tip()
        tips.setContentsMargins(20,26,20,20); tips.setSpacing(14)
        self.health_labels={}
        for key in ('device','audio','mode','signal'):
            label=QLabel(); label.setWordWrap(True); tips.addWidget(label); self.health_labels[key]=label
        self.update_capture_health({})
        note=QLabel('Status updates automatically. If no video arrives, check the HDMI connection, console HDCP settings and USB connection.')
        note.setWordWrap(True); note.setObjectName('Muted'); tips.addWidget(note)
        body.addWidget(guide)
        helpbox=QGroupBox('Explore Ascend'); hl=QVBoxLayout(helpbox); hl.setContentsMargins(20,26,20,20); hl.setSpacing(16)
        for text in (
            'Payload Holder — add your payload files, organise them by console and keep notes.',
            'Web Manager — use your existing console manager inside Ascend.',
            'Music — your own songs and ListenFree, with separate volume controls.',
            'FTP — browse your console, upload payloads and download your files.',
            'F11 enters/leaves fullscreen; Esc leaves fullscreen; F12 takes a screenshot; Ctrl+R toggles recording. Capture options stay accessible in fullscreen.'):
            label=QLabel(text); label.setWordWrap(True); hl.addWidget(label)
        body.addWidget(helpbox); body.addStretch()

    @staticmethod
    def field(text, control):
        row=QWidget(); form=QFormLayout(row); form.setContentsMargins(0,0,0,0)
        form.setHorizontalSpacing(24); label=QLabel(text); label.setFixedWidth(185)
        form.addRow(label,control); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        return row

    def update_capture_health(self, health):
        defaults={'device':'No capture device detected','audio':'No matching audio input detected',
                  'mode':'Choose a capture source to see available resolution', 'signal':'Preview stopped — press Start to check the video signal'}
        for key,label in self.health_labels.items(): label.setText(health.get(key,defaults[key]))

    def values(self):
        return {'name':self.nickname.text().strip(),'firmware':self.firmware.currentData() or '','loader':self.loader.currentText().strip(),'host':self.host.text().strip()}

    def store_profile(self):
        self.settings.setValue('profiles/'+self.active,json.dumps(self.values()))

    def load_profile(self,console):
        try: data=json.loads(self.settings.value('profiles/'+console,'{}'))
        except (ValueError,TypeError): data={}
        if not data and console=='PS5':
            data={'name':self.settings.value('console/name','My PS5'),'firmware':self.settings.value('console/firmware',''),'loader':self.settings.value('console/loader','Stock / official'),'host':self.settings.value('console/host','')}
        self.nickname.setText(data.get('name','My '+console))
        self.picker.set_profile(console,data.get('firmware',''),data.get('loader','Stock / official'))
        self.host.setText(data.get('host',''))

    def switch_profile(self,console):
        self.active=console; self.load_profile(console); self.update_tip()

    def update_tip(self):
        if self.active=='PS3':
            text='PS3: HDMI output uses HDCP. A typical HDMI capture card may show black. Use a supported component capture setup where available.'
        else:
            text=self.active+': disable HDCP in the console HDMI/system settings for gameplay capture. Start in SDR; capture is limited to 60 fps. HDMI passthrough capabilities are separate.'
        self.console_tip.setText(text)

    def save(self):
        if not self.picker.valid():
            self.message.setText('Choose a firmware and environment before saving.')
            return
        self.store_profile()
        self.settings.setValue('console/type',self.active)
        for key,value in self.values().items(): self.settings.setValue('console/'+key,value)
        self.host_changed.emit(self.host.text().strip()); self.profile_changed.emit()
        self.message.setText('Saved • '+self.active+' • '+(self.firmware.currentData() or 'firmware not set')+' • '+self.loader.currentText())

    def set_host(self,host):
        self.host.setText(host); self.save()

    def onboarding(self):
        dialog=QDialog(); dialog.setWindowIcon(QIcon(asset('ascend.ico'))); dialog.setWindowTitle('Ascends PS Capture program • Setup'); dialog.setMinimumWidth(500)
        layout=QVBoxLayout(dialog); layout.setContentsMargins(28,28,28,28); layout.setSpacing(20)
        heading=QLabel('SET UP YOUR CONSOLE'); heading.setObjectName('PageTitle'); layout.addWidget(heading)
        picker=ConsolePicker(self.active,self.firmware.currentData() or '',self.loader.currentText())
        layout.addWidget(picker)
        note=QLabel('Choose your console and firmware, then select your current environment.'); note.setWordWrap(True); layout.addWidget(note)
        error=QLabel(''); error.setWordWrap(True); layout.addWidget(error)
        picker.changed.connect(error.clear)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.Save).setText('Open Ascend')
        buttons.button(QDialogButtonBox.Save).setObjectName('Primary')
        def validate():
            if not picker.valid():
                error.setText('Choose your firmware and environment to continue.')
                return
            dialog.accept()
        buttons.accepted.connect(validate); buttons.rejected.connect(dialog.reject)
        if dialog.exec()==QDialog.Accepted:
            console,firmware,environment=picker.values()
            if console != self.active:
                self.console.setCurrentText(console)
            self.picker.set_profile(console,firmware,environment)
            self.save()
            self.settings.setValue('app/onboarded',True)
            return True
        return False

    def shutdown(self):
        pass
