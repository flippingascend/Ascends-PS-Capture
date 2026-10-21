"""Background FTP client for PS3, PS4 and PS5 console services."""
import ftplib
import os
import posixpath
import webbrowser
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal
from theme import GlowButton
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

PS3_PLACES = [
    "/",
    "/dev_hdd0",
    "/dev_hdd0/game",
    "/dev_hdd0/GAMES",
    "/dev_hdd0/PS3ISO",
    "/dev_hdd0/PSXISO",
    "/dev_hdd0/PS2ISO",
    "/dev_hdd0/packages",
    "/dev_hdd0/home",
    "/dev_hdd0/plugins",
    "/dev_hdd0/tmp",
    "/dev_usb000",
    "/dev_usb001",
    "/dev_blind",
]
CHUNK = 256 * 1024


def safe_name(name):
    return bool(name and name not in ('.','..') and not any(c in name for c in ('/', '\\', ':', '\r', '\n', '\x00')))


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return "{:.0f} {}".format(n, unit) if unit == "B" else "{:.1f} {}".format(n, unit)
        n /= 1024.0


def parse_list_line(line):
    """Parse one Unix-style LIST line: 'drwxr-xr-x 1 root root 512 Jan 01 12:00 name'."""
    parts = line.split(None, 8)
    if len(parts) < 9:
        return None
    perms, size, name = parts[0], parts[4], parts[8]
    if name in (".", ".."):
        return None
    is_dir = perms.startswith("d")
    try:
        size = int(size)
    except ValueError:
        size = 0
    date = " ".join(parts[5:8])
    return name, is_dir, size, date


class FtpWorker(QObject):
    """Owns the FTP connection. Jobs are (callable, on_done) pairs run in order."""

    job_done = Signal(object, object)   # on_done, result
    failed = Signal(str)
    progress = Signal(str, object, object)    # label, done bytes, total bytes
    log = Signal(str)

    def __init__(self):
        super().__init__()
        self.ftp = None
        self.cancel = False
        self.last_progress = 0.0

    def report_progress(self, label, done, total):
        now=time.monotonic()
        if now-self.last_progress >= 0.1 or done == total:
            self.last_progress=now; self.progress.emit(label, done, total)

    def run(self, job):
        func, on_done = job
        self.cancel = False
        try:
            result = func(self)
            self.job_done.emit(on_done, result)
        except Exception as exc:  # report every failure in the window, never crash
            if isinstance(exc, (OSError, EOFError, ftplib.error_temp)):
                self._drop()
            self.failed.emit(str(exc) or exc.__class__.__name__)

    def _drop(self):
        try:
            if self.ftp:
                self.ftp.close()
        except Exception:
            pass
        self.ftp = None

    # ---------- operations (run on the worker thread) ----------
    def open_connection(self, host, port, user, password, passive):
        self._drop()
        ftp = ftplib.FTP()
        ftp.encoding = "utf-8"
        self.ftp = ftp
        ftp.connect(host, port, timeout=10)
        ftp.login(user or "anonymous", password or "")
        ftp.set_pasv(passive)
        self.ftp = ftp
        self.log.emit(ftp.getwelcome() or "Connected")
        return ftp.pwd()

    def require(self):
        if self.ftp is None:
            raise ConnectionError("Not connected")
        return self.ftp

    def listdir(self, path):
        ftp = self.require()
        entries = []
        try:
            for name, facts in ftp.mlsd(path, facts=["type", "size", "modify"]):
                if not safe_name(name) or facts.get("type") in ("cdir", "pdir"):
                    continue
                is_dir = facts.get("type") == "dir"
                size = int(facts.get("size", 0) or 0)
                mod = facts.get("modify", "")
                date = "{}-{}-{} {}:{}".format(mod[0:4], mod[4:6], mod[6:8],
                                                mod[8:10], mod[10:12]) if len(mod) >= 12 else ""
                entries.append((name, is_dir, size, date))
        except ftplib.error_perm:
            lines = []
            ftp.cwd(path)
            ftp.retrlines("LIST", lines.append)
            for line in lines:
                parsed = parse_list_line(line)
                if parsed and safe_name(parsed[0]):
                    entries.append(parsed)
        entries.sort(key=lambda e: (not e[1], e[0].lower()))
        return path, entries

    def download_file(self, remote, local, size):
        ftp = self.require()
        done = [0]
        name = posixpath.basename(remote)
        if os.path.exists(local):
            raise FileExistsError("Download destination already exists: " + local)
        with open(local, "xb") as fh:
            def write(block):
                if self.cancel:
                    raise InterruptedError("Cancelled")
                fh.write(block)
                done[0] += len(block)
                self.report_progress("Downloading " + name, done[0], size)
            ftp.retrbinary("RETR " + remote, write, blocksize=CHUNK)

    def download_tree(self, remote, local_dir):
        ftp = self.require()
        target = os.path.join(local_dir, posixpath.basename(remote.rstrip("/")))
        os.makedirs(target, exist_ok=True)
        _, entries = self.listdir(remote)
        for name, is_dir, size, _ in entries:
            child = posixpath.join(remote, name)
            if is_dir:
                self.download_tree(child, target)
            else:
                self.download_file(child, os.path.join(target, name), size)
        return ftp

    def upload_file(self, local, remote):
        ftp = self.require()
        size = os.path.getsize(local)
        done = [0]
        name = os.path.basename(local)

        def sent(block):
            if self.cancel:
                raise InterruptedError("Cancelled")
            done[0] += len(block)
            self.report_progress("Uploading " + name, done[0], size)
        with open(local, "rb") as fh:
            ftp.storbinary("STOR " + remote, fh, blocksize=CHUNK, callback=sent)

    def upload_tree(self, local_dir, remote_parent):
        ftp = self.require()
        remote = posixpath.join(remote_parent, os.path.basename(local_dir.rstrip("\\/")))
        try:
            ftp.mkd(remote)
        except ftplib.error_perm:
            pass  # already exists
        for name in sorted(os.listdir(local_dir)):
            path = os.path.join(local_dir, name)
            if os.path.isdir(path):
                self.upload_tree(path, remote)
            else:
                self.upload_file(path, posixpath.join(remote, name))

    def delete_tree(self, remote):
        ftp = self.require()
        _, entries = self.listdir(remote)
        for name, is_dir, _, _ in entries:
            child = posixpath.join(remote, name)
            if is_dir:
                self.delete_tree(child)
            else:
                ftp.delete(child)
        ftp.rmd(remote)


class RemoteTree(QTreeWidget):
    """File list that accepts files dropped from Explorer to upload them."""

    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class FtpTab(QWidget):
    submit = Signal(object)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("AscendToolkit", "AscendToolkit")
        self.cwd = "/"
        self.busy = False

        self.thread = QThread(self)
        self.worker = FtpWorker()
        self.worker.moveToThread(self.thread)
        self.submit.connect(self.worker.run)
        self.worker.job_done.connect(self._job_done)
        self.worker.failed.connect(self._job_failed)
        self.worker.progress.connect(self._progress)
        self.worker.log.connect(lambda m: self.status.setText(m.strip()))
        self.thread.start()

        # connection row
        self.host_edit = QLineEdit(self.settings.value("ftp/host", ""))
        self.host_edit.setPlaceholderText("Console IP or hostname")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(int(self.settings.value("ftp/port", 21)))
        self.user_edit = QLineEdit(self.settings.value("ftp/user", "anonymous"))
        self.user_edit.setFixedWidth(110)
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setPlaceholderText("(blank)")
        self.pass_edit.setFixedWidth(110)
        self.passive = QCheckBox("Passive")
        self.passive.setChecked(True)
        self.connect_btn = GlowButton("Connect")
        self.webman_btn = QPushButton("Disconnect")

        conn = QHBoxLayout()
        conn.addWidget(QLabel("Host:"))
        conn.addWidget(self.host_edit, 1)
        conn.addWidget(QLabel("Port:"))
        conn.addWidget(self.port_spin)
        conn.addWidget(QLabel("User:"))
        conn.addWidget(self.user_edit)
        conn.addWidget(QLabel("Pass:"))
        conn.addWidget(self.pass_edit)
        conn.addWidget(self.passive)
        conn.addWidget(self.connect_btn)
        conn.addWidget(self.webman_btn)

        # path row
        self.up_btn = QPushButton("Up")
        self.path_edit = QLineEdit("/")
        self.places = QComboBox()
        self.places.addItem("Jump to...")
        self.places.addItems(PS3_PLACES)
        self.refresh_btn = QPushButton("Refresh")
        nav = QHBoxLayout()
        nav.addWidget(self.up_btn)
        nav.addWidget(self.path_edit, 1)
        nav.addWidget(self.places)
        nav.addWidget(self.refresh_btn)

        # file list
        self.tree = RemoteTree()
        self.tree.setHeaderLabels(["Name", "Size", "Modified"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setSortingEnabled(False)

        # actions
        self.upload_btn = QPushButton("Upload files")
        self.upload_dir_btn = QPushButton("Upload folder")
        self.download_btn = QPushButton("Download")
        self.mkdir_btn = QPushButton("New folder")
        self.rename_btn = QPushButton("Rename")
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("Danger")
        self.cancel_btn = QPushButton("Cancel transfer")
        actions = QGridLayout(); actions.setHorizontalSpacing(12); actions.setVerticalSpacing(8)
        for i,b in enumerate((self.upload_btn,self.upload_dir_btn,self.download_btn,self.mkdir_btn,self.rename_btn,self.delete_btn)):
            actions.addWidget(b,i//3,i%3)
        actions.addWidget(self.cancel_btn,2,2)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        self.status = QLabel('Connect to the FTP service running on your console. Passwords are kept in memory only.')
        self.status.setWordWrap(True)

        layout = QVBoxLayout(self)
        title=QLabel('FTP File Manager'); title.setObjectName('PageTitle'); layout.addWidget(title)
        layout.setSpacing(16); layout.setContentsMargins(12,16,12,16)
        # Split credentials into a second row so small windows stay usable.
        for control in (self.user_edit,self.pass_edit,self.passive,self.webman_btn): conn.removeWidget(control)
        # Rebuild the connection rows without orphan label widgets.
        while conn.count():
            item=conn.takeAt(0)
            if item.widget() and item.widget() not in (self.host_edit,self.port_spin,self.connect_btn): item.widget().deleteLater()
        conn.addWidget(QLabel('Host')); conn.addWidget(self.host_edit,1); conn.addWidget(QLabel('Port')); conn.addWidget(self.port_spin); conn.addWidget(self.connect_btn); conn.addWidget(self.webman_btn)
        layout.addLayout(conn)
        auth=QHBoxLayout(); auth.addWidget(QLabel('Username')); auth.addWidget(self.user_edit); auth.addWidget(QLabel('Password')); auth.addWidget(self.pass_edit); auth.addWidget(self.passive); auth.addStretch(); layout.addLayout(auth)
        layout.addLayout(nav)
        layout.addWidget(self.tree, 1)
        layout.addLayout(actions)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status)

        self.connect_btn.clicked.connect(self.do_connect)
        self.host_edit.returnPressed.connect(self.do_connect)
        self.webman_btn.clicked.connect(self.disconnect)
        self.up_btn.clicked.connect(self._go_up)
        self.path_edit.returnPressed.connect(lambda: self.open_dir(self.path_edit.text()))
        self.places.activated.connect(self._place_chosen)
        self.refresh_btn.clicked.connect(lambda: self.open_dir(self.cwd))
        self.tree.itemDoubleClicked.connect(self._item_activated)
        self.tree.files_dropped.connect(self._upload_paths)
        self.upload_btn.clicked.connect(self._upload_files)
        self.upload_dir_btn.clicked.connect(self._upload_folder)
        self.download_btn.clicked.connect(self._download)
        self.mkdir_btn.clicked.connect(self._mkdir)
        self.rename_btn.clicked.connect(self._rename)
        self.delete_btn.clicked.connect(self._delete)
        self.cancel_btn.clicked.connect(self._cancel)
        self.apply_profile()

    # ---------- job plumbing ----------
    def _run(self, func, on_done=None, label="Working..."):
        if self.busy:
            self.status.setText("Busy, wait for the current task to finish (or Cancel).")
            return
        self.busy = True
        self.status.setText(label)
        self.submit.emit((func, on_done))

    def _job_done(self, on_done, result):
        self.busy = False
        self.progress_bar.hide()
        if on_done:
            on_done(result)

    def _job_failed(self, message):
        self.busy = False
        self.progress_bar.hide()
        self.status.setText("Error: " + message)
        if self.worker.ftp is None:
            self.connect_btn.setText("Connect")

    def _progress(self, label, done, total):
        self.progress_bar.show()
        if total > 0:
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(int(done * 1000 / total))
            self.progress_bar.setFormat("{}  {} / {}".format(label, human_size(done),
                                                             human_size(total)))
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat(label)

    def _cancel(self):
        self.worker.cancel = True

    # ---------- connect / browse ----------
    def do_connect(self):
        host = self.host_edit.text().strip()
        if not host:
            self.status.setText("Type the console's IP address first.")
            return
        port = self.port_spin.value()
        user = self.user_edit.text().strip()
        password = self.pass_edit.text()
        passive = self.passive.isChecked()
        self.settings.setValue("ftp/host", host)
        self.settings.setValue("ftp/port", port)
        self.settings.setValue("ftp/user", user)

        def connected(_pwd):
            self.connect_btn.setText("Reconnect")
            self.open_dir("/")
        self._run(lambda w: w.open_connection(host, port, user, password, passive), connected,
                  "Connecting to {}:{}...".format(host, port))

    def apply_profile(self):
        console=self.settings.value('console/type','PS5')
        if not self.busy and self.worker.ftp is None:
            self.host_edit.setText(self.settings.value('console/host','') or self.settings.value('ftp/host',''))
            self.port_spin.setValue(int(self.settings.value('ftp/port',21 if console=='PS3' else 2121)))
        self.places.clear(); self.places.addItem('Jump to…')
        self.places.addItems(PS3_PLACES if console=='PS3' else ['/', '/data', '/data/homebrew', '/mnt/usb0', '/mnt/usb1', '/user'])

    def disconnect(self):
        if self.busy:
            self.status.setText('Cancel or finish the current transfer before disconnecting.')
            return
        def done(_):
            self.tree.clear(); self.connect_btn.setText('Connect'); self.status.setText('Disconnected')
        self._run(lambda w:w._drop(),done,'Disconnecting…')

    def open_dir(self, path):
        path = path.strip() or "/"
        self._run(lambda w: w.listdir(path), self._show_listing, "Listing " + path)

    def _show_listing(self, result):
        path, entries = result
        self.cwd = path
        self.path_edit.setText(path)
        self.tree.clear()
        for name, is_dir, size, date in entries:
            item = QTreeWidgetItem([name + ("/" if is_dir else ""),
                                    "" if is_dir else human_size(size), date])
            item.setData(0, Qt.UserRole, (name, is_dir, size))
            item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(item)
        self.status.setText("{}  ({} items)".format(path, len(entries)))

    def _go_up(self):
        self.open_dir(posixpath.dirname(self.cwd.rstrip("/")) or "/")

    def _place_chosen(self, index):
        if index > 0:
            self.open_dir(self.places.itemText(index))
        self.places.setCurrentIndex(0)

    def _item_activated(self, item):
        name, is_dir, _ = item.data(0, Qt.UserRole)
        if is_dir:
            self.open_dir(posixpath.join(self.cwd, name))
        else:
            self._download()

    def _selected(self):
        return [i.data(0, Qt.UserRole) for i in self.tree.selectedItems()]

    # ---------- transfers ----------
    def _refresh_after(self, _result=None):
        self.open_dir(self.cwd)

    def _upload_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Upload to console")
        if paths:
            self._upload_paths(paths)

    def _upload_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Upload folder to console")
        if path:
            self._upload_paths([path])

    def _upload_paths(self, paths):
        cwd = self.cwd

        def job(w):
            for p in paths:
                if os.path.isdir(p):
                    w.upload_tree(p, cwd)
                else:
                    w.upload_file(p, posixpath.join(cwd, os.path.basename(p)))
        self._run(job, self._refresh_after, "Uploading...")

    def _download(self):
        selected = self._selected()
        if not selected:
            self.status.setText("Select files or folders to download.")
            return
        last = self.settings.value("ftp/download_dir", os.path.expanduser("~/Downloads"))
        dest = QFileDialog.getExistingDirectory(self, "Download to", last)
        if not dest:
            return
        self.settings.setValue("ftp/download_dir", dest)
        cwd = self.cwd

        def job(w):
            for name, is_dir, size in selected:
                remote = posixpath.join(cwd, name)
                if is_dir:
                    w.download_tree(remote, dest)
                else:
                    w.download_file(remote, os.path.join(dest, name), size)
        self._run(job, lambda _r: self.status.setText("Downloaded to " + dest),
                  "Downloading...")

    def _mkdir(self):
        name, ok = QInputDialog.getText(self, "New folder", "Folder name:")
        if ok and name.strip():
            remote = posixpath.join(self.cwd, name.strip())
            self._run(lambda w: w.require().mkd(remote), self._refresh_after)

    def _rename(self):
        selected = self._selected()
        if len(selected) != 1:
            self.status.setText("Select one item to rename.")
            return
        old = selected[0][0]
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=old)
        if ok and new.strip() and new != old:
            src, dst = posixpath.join(self.cwd, old), posixpath.join(self.cwd, new.strip())
            self._run(lambda w: w.require().rename(src, dst), self._refresh_after)

    def _delete(self):
        selected = self._selected()
        if not selected:
            return
        names = ", ".join(s[0] for s in selected[:5]) + ("..." if len(selected) > 5 else "")
        answer = QMessageBox.question(
            self, "Delete from console",
            "Permanently delete {} from the console?\n\nFolders are deleted with everything "
            "inside them.".format(names))
        if answer != QMessageBox.Yes:
            return
        cwd = self.cwd

        def job(w):
            for name, is_dir, _ in selected:
                remote = posixpath.join(cwd, name)
                if is_dir:
                    w.delete_tree(remote)
                else:
                    w.require().delete(remote)
        self._run(job, self._refresh_after, "Deleting...")

    def shutdown(self):
        self.worker.cancel = True
        if self.worker.ftp:
            self.worker._drop()
        self.thread.quit()
        self.thread.wait(12000)
