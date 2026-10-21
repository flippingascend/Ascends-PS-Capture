"""Local payload catalogue. Files are referenced, never executed."""
import hashlib
import json
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QApplication, QGridLayout

class HashWorker(QThread):
    result = Signal(str, str)
    def __init__(self, path):
        super().__init__(); self.path=path
    def run(self):
        try:
            digest=hashlib.sha256()
            with open(self.path,'rb') as handle:
                for chunk in iter(lambda: handle.read(1024*1024),b''):
                    if self.isInterruptionRequested(): return
                    digest.update(chunk)
            self.result.emit(self.path,digest.hexdigest())
        except OSError as exc: self.result.emit(self.path,'Error: '+str(exc))

class PayloadTab(QWidget):
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.settings=QSettings('AscendToolkit','AscendToolkit'); self.worker=None
        try:
            self.entries=json.loads(self.settings.value('payloads/catalogue','[]'))
            if not isinstance(self.entries,list): self.entries=[]
            self.entries=[e for e in self.entries if isinstance(e,dict) and isinstance(e.get('path'),str)]
        except (ValueError,TypeError): self.entries=[]
        layout=QVBoxLayout(self)
        title=QLabel('Payload Holder'); title.setObjectName('PageTitle'); layout.addWidget(title)
        desc=QLabel('Add or drop your payload files, then organise them by console and firmware. Original files stay where they are.')
        desc.setWordWrap(True); layout.addWidget(desc)
        row=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText('Search payloads, firmware or notes…')
        self.console=QComboBox(); self.console.addItems(['All consoles','PS3','PS4','PS5'])
        row.addWidget(self.search,1); row.addWidget(self.console)
        for text, callback in (('Add files',self.add),('Remove entry',self.remove)):
            b=QPushButton(text); b.clicked.connect(callback); row.addWidget(b)
        layout.addLayout(row)
        self.table=QTableWidget(0,5); self.table.verticalHeader().hide(); self.table.setHorizontalHeaderLabels(['File','Console','Firmware / loader','Notes','File status'])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        for col in (1,2,4): self.table.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setWordWrap(False); layout.addWidget(self.table,1)
        actions=QGridLayout()
        self.hash_btn=QPushButton('Calculate SHA-256'); self.hash_btn.clicked.connect(self.hash_selected); actions.addWidget(self.hash_btn,0,0)
        for i,(text,callback) in enumerate((('Copy file path',self.copy_path),('Open containing folder',self.open_folder),('Export catalogue',self.export))):
            b=QPushButton(text); b.clicked.connect(callback); actions.addWidget(b,(i+1)//2,(i+1)%2)
        layout.addLayout(actions)
        self.status=QLabel('Double-click a detail to edit it. Removing an entry does not delete the original file.')
        self.status.setWordWrap(True); self.status.setTextInteractionFlags(Qt.TextSelectableByMouse); layout.addWidget(self.status)
        self.search.textChanged.connect(self.render); self.console.currentTextChanged.connect(self.render)
        self.table.itemChanged.connect(self.edited); self.render()

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()): event.acceptProposedAction()

    def dropEvent(self,event):
        paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile() and Path(u.toLocalFile()).is_file()]
        if paths:
            self.add_paths(paths); self.status.setText(f'Added {len(paths)} file(s). Files stay in their original folders.'); event.acceptProposedAction()

    def save(self):
        self.settings.setValue('payloads/catalogue',json.dumps(self.entries))

    def render(self):
        self.table.blockSignals(True); self.table.setRowCount(0)
        query=self.search.text().casefold(); console=self.console.currentText()
        for index,e in enumerate(self.entries):
            if query and query not in json.dumps(e).casefold(): continue
            if console!='All consoles' and e.get('console')!=console: continue
            row=self.table.rowCount(); self.table.insertRow(row)
            values=[Path(e['path']).name,e.get('console','PS5'),e.get('firmware',''),e.get('notes',''),'Available' if Path(e['path']).is_file() else 'Missing']
            for col,value in enumerate(values):
                item=QTableWidgetItem(value); item.setData(Qt.UserRole,index); item.setToolTip(e['path'])
                if col in (0,4): item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row,col,item)
        self.table.blockSignals(False)

    def edited(self,item):
        key={1:'console',2:'firmware',3:'notes'}.get(item.column())
        if key:
            self.entries[item.data(Qt.UserRole)][key]=item.text().strip(); self.save()

    def selected(self):
        item=self.table.item(self.table.currentRow(),0)
        return self.entries[item.data(Qt.UserRole)] if item else None

    def add_paths(self,paths):
        existing={e['path'] for e in self.entries}
        for path in paths:
            if path not in existing:
                self.entries.append({'path':path,'console':self.settings.value('console/type','PS5'),'firmware':self.settings.value('console/firmware',''),'notes':''})
                existing.add(path)
        self.save(); self.render()

    def add(self):
        paths,_=QFileDialog.getOpenFileNames(self,'Add payload or homebrew files','','Payloads / homebrew (*.bin *.elf *.self *.sprx *.pkg *.zip *.7z *.txt);;All files (*)')
        self.add_paths(paths)

    def remove(self):
        entry=self.selected()
        if entry: self.entries.remove(entry); self.save(); self.render()

    def copy_path(self):
        entry=self.selected()
        if entry: QApplication.clipboard().setText(entry['path'])

    def open_folder(self):
        entry=self.selected()
        if entry: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(entry['path']).parent)))

    def hash_selected(self):
        entry=self.selected()
        if not entry or (self.worker and self.worker.isRunning()): return
        self.hash_btn.setEnabled(False); self.status.setText('Calculating SHA-256…')
        self.worker=HashWorker(entry['path']); self.worker.result.connect(self.hashed)
        self.worker.finished.connect(lambda: self.hash_btn.setEnabled(True)); self.worker.start()

    def hashed(self,path,digest):
        self.status.setText(Path(path).name+' • '+digest)
        for entry in self.entries:
            if entry['path']==path and not digest.startswith('Error:'): entry['sha256']=digest
        self.save()

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export catalogue','ascend-payload-catalogue.json','JSON (*.json)')
        if path:
            try: Path(path).write_text(json.dumps(self.entries,indent=2),encoding='utf-8'); self.status.setText('Catalogue exported.')
            except OSError as exc: self.status.setText('Export failed: '+str(exc))

    def shutdown(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption(); self.worker.wait()
