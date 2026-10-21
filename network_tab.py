"""Network info: adapters with a live link monitor, Wi-Fi details, a LAN scanner
for LAN service discovery, and Windows shared folders."""
import ipaddress
import os
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import psutil
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from theme import GlowButton
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

IS_WINDOWS = sys.platform.startswith("win")
SCAN_PORTS = (21, 80, 139, 445)
# MAC prefixes used by Sony on PS3 network chips.
SONY_OUIS = {
    "00:04:1F", "00:13:15", "00:15:C1", "00:19:C5", "00:1D:0D", "00:1F:A7",
    "00:24:8D", "28:0D:FC", "A8:E3:EE", "F8:D0:AC", "FC:0F:E6", "00:D9:D1",
    "70:9E:29", "BC:60:A7", "2C:CC:44", "0C:FE:45",
}


def run_cmd(args, timeout=10):
    """Run a command and return its text output without flashing a console window."""
    flags = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW
    try:
        out = subprocess.run(args, capture_output=True, timeout=timeout,
                             creationflags=flags)
        data = out.stdout or out.stderr
        for enc in ("utf-8", "cp850", "cp1252"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "Could not run {}: {}".format(args[0], exc)


def normalise_mac(mac):
    return mac.replace("-", ":").upper()


def adapter_snapshot():
    """Return {name: dict(up, speed, ipv4, netmask, mac)} for every adapter."""
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()
    result = {}
    for name, st in stats.items():
        info = {"up": st.isup, "speed": st.speed, "ipv4": "", "netmask": "", "mac": ""}
        for a in addrs.get(name, []):
            if a.family == socket.AF_INET:
                info["ipv4"], info["netmask"] = a.address, a.netmask or ""
            elif a.family == psutil.AF_LINK:
                info["mac"] = normalise_mac(a.address)
        result[name] = info
    return result


def wifi_details():
    if IS_WINDOWS:
        text = run_cmd(["netsh", "wlan", "show", "interfaces"])
        keep = ("Name", "Description", "State", "SSID", "BSSID", "Network type",
                "Radio type", "Band", "Channel", "Receive rate", "Transmit rate",
                "Signal", "Authentication")
        lines = [ln.strip() for ln in text.splitlines()
                 if any(ln.strip().startswith(k) for k in keep)]
        return "\n".join(lines) if lines else text.strip() or "No Wi-Fi adapter found."
    text = run_cmd(["nmcli", "-f", "ACTIVE,SSID,SIGNAL,CHAN,RATE,SECURITY",
                    "dev", "wifi"])
    return text.strip() or "Wi-Fi details are available on Windows (netsh)."


def arp_table():
    """Map IP -> MAC from the OS neighbour cache."""
    text = run_cmd(["arp", "-a"])
    table = {}
    for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\D+?([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})",
                         text):
        table[m.group(1)] = normalise_mac(m.group(2))
    return table


def probe(ip, port, timeout=0.4):
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            if port == 21:
                s.settimeout(1.0)
                try:
                    return s.recv(256).decode("latin-1", "replace").strip()
                except OSError:
                    return "FTP"
            return True
    except OSError:
        return None


class ScanThread(QThread):
    found = Signal(dict)
    progress = Signal(int, int)
    finished_scan = Signal(int)

    def __init__(self, network):
        super().__init__()
        self.network = network

    def scan_host(self, ip):
        open_ports, banner = [], ""
        for port in SCAN_PORTS:
            if self.isInterruptionRequested(): return ip, [], ""
            res = probe(ip, port)
            if res:
                open_ports.append(port)
                if port == 21 and isinstance(res, str):
                    banner = res
        return ip, open_ports, banner

    def run(self):
        hosts = [str(h) for h in self.network.hosts()]
        count = 0
        results = []
        with ThreadPoolExecutor(max_workers=128) as pool:
            for i, (ip, ports, banner) in enumerate(pool.map(self.scan_host, hosts)):
                if self.isInterruptionRequested(): return
                self.progress.emit(i + 1, len(hosts))
                if ports:
                    results.append((ip, ports, banner))
        arp = arp_table()  # filled in by the scan traffic itself
        for ip, ports, banner in results:
            if self.isInterruptionRequested(): return
            name = ""
            mac = arp.get(ip, "")
            ps3 = 21 in ports and (
                any(k in banner.lower() for k in ("webman", "multiman", "ps3", "rebug",
                                                   "irisman", "cobra"))
                or mac[:8] in SONY_OUIS)
            self.found.emit({"ip": ip, "name": name, "mac": mac, "ports": ports,
                             "banner": banner, "ps3": ps3})
            count += 1
        # devices that answered ARP but have none of our ports open
        for ip, mac in arp.items():
            try:
                if ipaddress.ip_address(ip) in self.network and \
                        ip not in {r[0] for r in results}:
                    self.found.emit({"ip": ip, "name": "", "mac": mac, "ports": [],
                                     "banner": "", "ps3": False})
                    count += 1
            except ValueError:
                pass
        self.finished_scan.emit(count)


class AdapterPoller(QThread):
    """Reads adapter state off the UI thread so it can never stall the video."""

    snapshot = Signal(dict)

    def __init__(self, interval=1.5):
        super().__init__()
        self.interval = interval
        self.running = True

    def run(self):
        while self.running:
            try:
                self.snapshot.emit(adapter_snapshot())
            except Exception:
                pass
            for _ in range(int(self.interval * 10)):
                if not self.running:
                    return
                time.sleep(0.1)


class CmdThread(QThread):
    done = Signal(str, str)

    def __init__(self, title, func):
        super().__init__()
        self.title, self.func = title, func

    def run(self):
        self.done.emit(self.title, self.func())


class NetworkTab(QWidget):
    console_found = Signal(str)

    def __init__(self):
        super().__init__()
        self.prev = {}
        self.scan_thread = None
        self.cmd_threads = []

        # --- adapters + link monitor ---
        self.adapters = QTableWidget(0, 5)
        self.adapters.setHorizontalHeaderLabels(["Adapter", "Link", "Speed", "IPv4", "MAC"])
        self.adapters.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.adapters.verticalHeader().hide()
        self.adapters.setEditTriggers(QTableWidget.NoEditTriggers)
        self.adapters.setSelectionBehavior(QTableWidget.SelectRows)
        self.link_log = QPlainTextEdit()
        self.link_log.setReadOnly(True)
        self.link_log.setPlaceholderText(
            "Link monitor: every time an adapter (like Ethernet 2) drops or comes back, "
            "or its speed changes, it is logged here with the time.")
        adapters_box = QGroupBox("Network adapters (live)")
        ab = QVBoxLayout(adapters_box)
        ab.addWidget(self.adapters, 3)
        ab.addWidget(self.link_log, 1)

        # --- wifi ---
        self.wifi_text = QPlainTextEdit()
        self.wifi_text.setReadOnly(True)
        wifi_refresh = QPushButton("Refresh Wi-Fi")
        wifi_box = QGroupBox("Wi-Fi")
        wb = QVBoxLayout(wifi_box)
        wb.addWidget(self.wifi_text)
        wb.addWidget(wifi_refresh)

        top = QSplitter(Qt.Horizontal)
        top.addWidget(adapters_box)
        top.addWidget(wifi_box)
        top.setSizes([700, 400])

        # --- scanner ---
        self.net_combo = QComboBox()
        self.scan_btn = GlowButton("Scan network")
        self.scan_status = QLabel("")
        self.devices = QTableWidget(0, 5)
        self.devices.setHorizontalHeaderLabels(["IP", "Name", "MAC", "Open", "Notes"])
        self.devices.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.devices.verticalHeader().hide()
        self.devices.setEditTriggers(QTableWidget.NoEditTriggers)
        self.devices.setSelectionBehavior(QTableWidget.SelectRows)
        self.devices.setSelectionMode(QTableWidget.SingleSelection)
        self.use_ps3_btn = GlowButton("Use selected IP")
        self.shares_btn = QPushButton("Show shared folders")
        self.open_share_btn = QPushButton("Open in Explorer")
        self.my_shares_btn = QPushButton("This PC's shares")
        self.shares_text = QPlainTextEdit()
        self.shares_text.setReadOnly(True)
        self.shares_text.setMaximumHeight(140)

        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Network:"))
        scan_row.addWidget(self.net_combo, 1)
        scan_row.addWidget(self.scan_btn)
        scan_row.addWidget(self.scan_status, 1)
        dev_row = QHBoxLayout()
        for b in (self.use_ps3_btn, self.shares_btn, self.open_share_btn,
                  self.my_shares_btn):
            dev_row.addWidget(b)
        dev_row.addStretch()
        scan_box = QGroupBox("Devices on your network")
        sb = QVBoxLayout(scan_box)
        sb.addLayout(scan_row)
        sb.addWidget(self.devices, 1)
        sb.addLayout(dev_row)
        sb.addWidget(self.shares_text)

        split = QSplitter(Qt.Vertical)
        split.addWidget(top)
        split.addWidget(scan_box)
        split.setSizes([330, 470])
        layout = QVBoxLayout(self)
        layout.addWidget(split)

        wifi_refresh.clicked.connect(self.refresh_wifi)
        self.scan_btn.clicked.connect(self.start_scan)
        self.use_ps3_btn.clicked.connect(self._use_ps3)
        self.shares_btn.clicked.connect(self._show_shares)
        self.open_share_btn.clicked.connect(self._open_share)
        self.my_shares_btn.clicked.connect(self._my_shares)
        self.devices.itemDoubleClicked.connect(lambda _i: self._use_ps3())

        self.poller = AdapterPoller()
        self.poller.snapshot.connect(self.refresh_adapters)
        self.poller.start()
        self.refresh_wifi()

    # ---------- adapters ----------
    def refresh_adapters(self, snap):
        stamp = time.strftime("%H:%M:%S")
        for name, info in snap.items():
            old = self.prev.get(name)
            if old is None:
                continue
            if old["up"] != info["up"]:
                self._log("{}  {}  {}".format(stamp, name, "UP" if info["up"] else "DOWN"))
            elif info["up"] and old["speed"] != info["speed"]:
                self._log("{}  {}  speed {} -> {} Mbps".format(
                    stamp, name, old["speed"], info["speed"]))
            elif old["ipv4"] != info["ipv4"]:
                self._log("{}  {}  IP {} -> {}".format(
                    stamp, name, old["ipv4"] or "none", info["ipv4"] or "none"))
        self.prev = snap

        names = sorted(snap, key=lambda n: (not snap[n]["up"], n.lower()))
        self.adapters.setRowCount(len(names))
        for row, name in enumerate(names):
            info = snap[name]
            speed = "{} Mbps".format(info["speed"]) if info["speed"] else ""
            values = [name, "Up" if info["up"] else "Down", speed, info["ipv4"], info["mac"]]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                if col == 1:
                    item.setForeground(QColor("#34c759") if info["up"] else QColor("#ff453a"))
                self.adapters.setItem(row, col, item)

        # keep the scan network list in sync with adapters that have an address
        networks = []
        for name in names:
            info = snap[name]
            if info["up"] and info["ipv4"] and info["netmask"] and \
                    not info["ipv4"].startswith(("127.", "169.254.")):
                net = ipaddress.ip_network("{}/{}".format(info["ipv4"], info["netmask"]),
                                           strict=False)
                if net.prefixlen < 24:  # keep scans quick on big networks
                    net = ipaddress.ip_network("{}/24".format(info["ipv4"]), strict=False)
                networks.append("{}  ({})".format(net, name))
        current = [self.net_combo.itemText(i) for i in range(self.net_combo.count())]
        if networks != current:
            selected = self.net_combo.currentText()
            self.net_combo.clear()
            self.net_combo.addItems(networks)
            if selected in networks:
                self.net_combo.setCurrentText(selected)

    def _log(self, line):
        self.link_log.appendPlainText(line)

    # ---------- background commands ----------
    def _run_cmd(self, title, func, target):
        thread = CmdThread(title, func)
        thread.done.connect(lambda t, text: target.setPlainText(
            text if not t else "{}\n\n{}".format(t, text)))
        thread.finished.connect(lambda: self.cmd_threads.remove(thread))
        self.cmd_threads.append(thread)
        thread.start()

    def refresh_wifi(self):
        self.wifi_text.setPlainText("Reading Wi-Fi details...")
        self._run_cmd("", wifi_details, self.wifi_text)

    # ---------- scanner ----------
    def start_scan(self):
        if self.scan_thread and self.scan_thread.isRunning():
            return
        text = self.net_combo.currentText()
        if not text:
            self.scan_status.setText("No connected network to scan.")
            return
        network = ipaddress.ip_network(text.split()[0])
        if network.num_addresses > 256:
            self.scan_status.setText("Choose a /24 or smaller network (up to 256 addresses).")
            return
        self.devices.setRowCount(0)
        self.scan_btn.setEnabled(False)
        self.scan_thread = ScanThread(network)
        self.scan_thread.found.connect(self._add_device)
        self.scan_thread.progress.connect(
            lambda d, t: self.scan_status.setText("Scanning {}/{}...".format(d, t)))
        self.scan_thread.finished_scan.connect(self._scan_done)
        self.scan_thread.start()

    def _add_device(self, dev):
        row = self.devices.rowCount()
        self.devices.insertRow(row)
        ports = ", ".join({21: "FTP", 80: "Web", 139: "NetBIOS", 445: "Shares"}[p]
                          for p in dev["ports"])
        notes = "FTP server (identity unverified)" if dev["ps3"] else (dev["banner"][:80] or "")
        for col, val in enumerate([dev["ip"], dev["name"], dev["mac"], ports, notes]):
            item = QTableWidgetItem(val)
            if dev["ps3"]:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.devices.setItem(row, col, item)
        if dev["ps3"]:
            self.devices.selectRow(row)

    def _scan_done(self, count):
        self.scan_btn.setEnabled(True)
        ps3s = [self.devices.item(r, 0).text() for r in range(self.devices.rowCount())
                if self.devices.item(r, 4).text().startswith("FTP server")]
        msg = "Found {} devices.".format(count)
        if ps3s:
            msg += " FTP server at {}.".format(", ".join(ps3s))
        else:
            msg += (" Device identity cannot be determined from open ports. The selected device must be "
                    "on your own network.")
        self.scan_status.setText(msg)

    def _selected_ip(self):
        row = self.devices.currentRow()
        if row < 0:
            self.shares_text.setPlainText("Select a device in the list first.")
            return None
        return self.devices.item(row, 0).text()

    def _use_ps3(self):
        ip = self._selected_ip()
        if ip:
            self.console_found.emit(ip)

    def _show_shares(self):
        ip = self._selected_ip()
        if not ip:
            return
        self.shares_text.setPlainText("Asking {} for its shared folders...".format(ip))
        if IS_WINDOWS:
            func = lambda: run_cmd(["net", "view", "\\\\" + ip, "/all"], timeout=20)
        else:
            func = lambda: run_cmd(["smbclient", "-N", "-L", ip], timeout=20)
        self._run_cmd("Shared folders on " + ip, func, self.shares_text)

    def _open_share(self):
        ip = self._selected_ip()
        if ip and IS_WINDOWS:
            os.startfile("\\\\" + ip)

    def _my_shares(self):
        func = (lambda: run_cmd(["net", "share"])) if IS_WINDOWS else \
            (lambda: "Listing this PC's shares works on Windows.")
        self._run_cmd("Folders this PC is sharing", func, self.shares_text)

    def shutdown(self):
        self.poller.running = False
        self.poller.wait(2000)
        if self.scan_thread:
            self.scan_thread.requestInterruption()
            self.scan_thread.wait()
        for t in list(self.cmd_threads):
            t.wait()
