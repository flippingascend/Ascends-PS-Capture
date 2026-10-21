"""Shared offline console catalogue and dependent setup selectors.

Only explicit firmware matches enable a named option. Sources and caveats travel
with the catalogue; selection describes a profile and never installs an exploit.
"""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QComboBox, QLabel, QFormLayout

FIRMWARES = {
 'PS3': '''1.00 1.02 1.10 1.11 1.30 1.31 1.32 1.50 1.51 1.54 1.60 1.70 1.80 1.81 1.82 1.90 1.92 1.93 1.94 2.00 2.01 2.10 2.17 2.20 2.30 2.35 2.36 2.40 2.41 2.42 2.43 2.50 2.52 2.53 2.60 2.70 2.76 2.80 3.00 3.01 3.10 3.15 3.21 3.30 3.40 3.41 3.42 3.50 3.55 3.56 3.60 3.61 3.65 3.66 3.70 3.72 3.73 3.74 4.00 4.10 4.11 4.20 4.21 4.25 4.30 4.31 4.40 4.41 4.45 4.46 4.50 4.53 4.55 4.60 4.65 4.66 4.70 4.75 4.76 4.78 4.80 4.81 4.82 4.83 4.84 4.85 4.86 4.87 4.88 4.89 4.90 4.91 4.92 4.93'''.split(),
 'PS4': '''1.01 1.05 1.06 1.07 1.10 1.50 1.51 1.52 1.60 1.61 1.62 1.70 1.71 1.72 1.74 1.75 1.76 2.00 2.01 2.02 2.03 2.04 2.50 2.51 2.55 2.57 3.00 3.10 3.11 3.15 3.50 3.55 4.00 4.01 4.05 4.06 4.07 4.50 4.55 4.70 4.71 4.72 4.73 4.74 5.00 5.01 5.03 5.05 5.50 5.53 5.55 5.56 6.00 6.02 6.20 6.50 6.51 6.70 6.71 6.72 7.00 7.01 7.02 7.50 7.51 7.55 8.00 8.01 8.03 8.50 8.52 9.00 9.03 9.04 9.50 9.51 9.60 10.00 10.01 10.50 10.70 10.71 11.00 11.02 11.50 11.52 12.00 12.02 12.50 12.52 13.00 13.02 13.04 13.50 13.52'''.split(),
 'PS5': '''1.00 1.01 1.02 1.05 1.10 1.11 1.12 1.13 1.14 2.00 2.20 2.25 2.26 2.30 2.50 2.70 3.00 3.10 3.20 3.21 4.00 4.02 4.03 4.50 4.51 5.00 5.02 5.10 5.50 6.00 6.02 6.50 7.00 7.01 7.20 7.40 7.60 7.61 8.00 8.20 8.40 8.60 9.00 9.05 9.20 9.40 9.60 10.00 10.01 10.20 10.40 10.60 11.00 11.20 11.40 11.60 12.00 12.02 12.20 12.40 12.60 12.70 13.00 13.20 13.40 13.42 13.60 14.00 14.10'''.split(),
}
RELAPSE = set('7.00 7.01 7.20 7.40 7.60 7.61 8.00 8.20 8.40 8.60 9.00 9.20 9.40 9.60 10.00 10.01 10.20 10.40 10.60 11.00 11.20 11.60 12.00 12.02 12.20 12.40 12.60 12.70 13.00 13.20 13.40 13.42 13.60'.split())
SOURCES = {
 'Relapse': 'https://github.com/ntfargo/Relapse-Exploit/blob/main/src/firmware.js',
 'PS3HEN': 'https://github.com/PS3Xploit/PS3HEN',
 'GoldHEN': 'https://github.com/GoldHEN/GoldHEN/releases',
 'PPPwn': 'https://github.com/TheOfficialFloW/PPPwn',
 'pOOBs4': 'https://github.com/ChendoChap/pOOBs4',
 'IPv6': 'https://github.com/Cryptogenic/PS5-IPV6-Kernel-Exploit',
 'OnionHEN': 'https://github.com/aydencharles/OnionHEN',
 'UMTX': 'https://github.com/PS5Dev/PS5-UMTX-Jailbreak',
 'PS5 firmware': 'https://github.com/MewX/ps5-official-firmware-list',
}
STOCK = 'Stock / official'
UNKNOWN = 'Other / unverified'

def environments(console, fw):
    """Return (label, limitation) pairs; unknown firmware never inherits a range."""
    options = [(STOCK, 'Official system software; capture and music remain available.')]
    if fw not in FIRMWARES.get(console, ()):
        return options + [(UNKNOWN, 'This firmware is not in the compatibility catalogue.')]
    if console == 'PS5':
        if fw in RELAPSE:
            options.append(('Relapse', 'Relapse lists this exact firmware. Homebrew enablers and payloads have separate build requirements.'))
        if fw in {'1.00','1.01','1.02','1.05','1.10','1.11','1.12','1.13','1.14','2.00','2.20','2.25','2.26','2.30','2.50','2.70','3.00','3.20','4.00','4.02','4.03','4.50','4.51'}:
            options.append(('UMTX', 'Listed by the UMTX project; reliability and payload support vary by firmware.'))
        if fw == '9.20':
            options.append(('Relapse + OnionHEN', 'Relapse supports 9.20. Requires a firmware-matched OnionHEN build; the enabler is separate from the jailbreak entry point.'))
        if fw in {'3.00','3.10','3.20','3.21','4.00','4.02','4.03','4.50','4.51'}:
            options.append(('IPv6 / WebKit', 'The IPv6 project lists this exact firmware; payload requirements are separate.'))
    elif console == 'PS4':
        if fw in set('7.00 7.01 7.02 7.50 7.51 7.55 8.00 8.01 8.03 8.50 8.52 9.00 9.03 9.04 9.50 9.51 9.60 10.00 10.01 10.50 10.70 10.71 11.00'.split()):
            options.append(('PPPwn', 'PPPwn supports this version; a compatible stage2 / homebrew enabler is required for homebrew.'))
        if fw == '9.00':
            options.append(('pOOBs4', 'The USB / exFAT exploit targets PS4 9.00.'))
        # Published GoldHEN release targets, rather than every vulnerable version.
        if fw in {'5.05','6.71','6.72','9.00','9.60','10.00','10.01','10.50','10.70','10.71','11.00'}:
            options.append(('GoldHEN', 'Use a GoldHEN build and exploit entry point matching this exact firmware.'))
    elif console == 'PS3':
        if fw in {'4.80','4.81','4.82'}:
            options.append(('PS3HEN', 'PS3HEN lists this OFW version; select the matching installer.'))
        if fw in {'4.83','4.84','4.85','4.86','4.87','4.88','4.89','4.90','4.91','4.92','4.93'}:
            options.append(('PS3HEN / HFW', 'Requires matching Hybrid Firmware (HFW), not ordinary OFW.'))
        if fw in {'3.55','4.21','4.30','4.46','4.65','4.70','4.75','4.76','4.78','4.80','4.81','4.82','4.84','4.85','4.86','4.87','4.88','4.89','4.90','4.91','4.92','4.93'}:
            options.append(('CFW (compatible models only)', 'Model-dependent: firmware alone does not establish CFW support. Select only if your console already runs compatible CFW.'))
    return options + [(UNKNOWN, 'No compatibility claim. Keep this for an existing setup not yet covered by the catalogue.')]

class ConsolePicker(QWidget):
    changed = Signal()
    def __init__(self, console='PS5', firmware='', environment=STOCK, parent=None):
        super().__init__(parent)
        form=QFormLayout(self); form.setContentsMargins(0,0,0,0); form.setVerticalSpacing(16); form.setHorizontalSpacing(24)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.console=QComboBox(); self.console.addItems(['PS3','PS4','PS5'])
        self.firmware=QComboBox(); self.firmware.setMaxVisibleItems(12)
        self.firmware.setStyleSheet('QComboBox { combobox-popup: 0; }')
        self.environment=QComboBox(); self.environment.setMaxVisibleItems(10)
        for title,control in [('Console',self.console),('Firmware',self.firmware),('Environment / jailbreak',self.environment)]: label=QLabel(title); label.setFixedWidth(185); control.setMinimumHeight(38); form.addRow(label,control)
        self.note=QLabel(); self.note.setWordWrap(True); self.note.setObjectName('Muted'); form.addRow(self.note)
        sources=QLabel('<a style="color:#8ccaff" href="https://github.com/ntfargo/Relapse-Exploit/blob/main/src/firmware.js">Relapse</a> · <a style="color:#8ccaff" href="https://github.com/GoldHEN/GoldHEN/releases">GoldHEN</a> · <a style="color:#8ccaff" href="https://github.com/PS3Xploit/PS3HEN">PS3HEN</a>')
        sources.setOpenExternalLinks(True); sources.setStyleSheet('QLabel { color: #c3d0df; } QLabel a { color: #8ccaff; }'); form.addRow(sources)
        self.console.currentTextChanged.connect(self._console_changed)
        self.firmware.currentIndexChanged.connect(self._firmware_changed)
        self.environment.currentIndexChanged.connect(self._environment_changed)
        self.set_profile(console, firmware, environment)

    def set_profile(self,console,firmware,environment):
        self.console.blockSignals(True); self.console.setCurrentText(console); self.console.blockSignals(False)
        self._populate_firmware(firmware)
        self._populate_environment(environment)

    def _populate_firmware(self, selected=''):
        self.firmware.blockSignals(True); self.firmware.clear()
        self.firmware.addItem('Select firmware…','')
        versions=list(FIRMWARES[self.console.currentText()])
        if selected and selected not in versions: versions.append(selected)
        for fw in sorted(versions,key=lambda v:tuple(int(x) for x in v.split('.')) if all(x.isdigit() for x in v.split('.')) else (999,),reverse=True):
            self.firmware.addItem(fw if fw in FIRMWARES[self.console.currentText()] else fw+' (saved, unverified)',fw)
        self.firmware.setCurrentIndex(max(0,self.firmware.findData(selected)))
        self.firmware.blockSignals(False)

    def _populate_environment(self, selected=''):
        aliases={'JB-Relapse':'Relapse','HEN':'PS3HEN / HFW','CFW':'CFW (compatible models only)','OnionHEN':'Relapse + OnionHEN'}
        selected=aliases.get(selected,selected)
        self.environment.blockSignals(True); self.environment.clear()
        self.environment.addItem('Select environment…','')
        for label,note in environments(self.console.currentText(), self.firmware.currentData() or ''):
            self.environment.addItem(label,note)
        i=self.environment.findText(selected)
        if i<0 and selected: i=self.environment.findText(UNKNOWN)
        self.environment.setCurrentIndex(max(0,i)); self.environment.blockSignals(False)
        self._environment_changed()

    def _console_changed(self):
        self._populate_firmware(); self._populate_environment(); self.changed.emit()

    def _firmware_changed(self):
        previous=self.environment.currentText()
        # An incompatible selection is cleared, never silently changed to stock.
        labels=[label for label,_ in environments(self.console.currentText(),self.firmware.currentData() or '')]
        self._populate_environment(previous if previous in labels else '')
        self.changed.emit()

    def _environment_changed(self):
        self.note.setText(self.environment.currentData() or 'Choose your firmware, then the environment you already use.')
        self.changed.emit()

    def values(self):
        return self.console.currentText(),self.firmware.currentData() or '',self.environment.currentText() if self.environment.currentIndex()>0 else ''

    def valid(self):
        _,fw,env=self.values()
        return bool(fw and env)
