"""
Gaming session logger for Dev Command Center.
Detects running games, records hardware stats per session, saves to SQLite.
"""
import json
import logging
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QPushButton, QSystemTrayIcon, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

logger = logging.getLogger(__name__)

MIN_SESSION_SEC = 60   # shorter sessions are discarded
SCAN_EVERY_SEC = 5     # how often to look for running games
SAVE_EVERY_SEC = 60    # checkpoint active sessions (crash safety)

# Any .exe inside these folders counts as a game (the folder after the marker is its name)
GAME_DIR_MARKERS = [
    "\\steamapps\\common\\",
    "\\epic games\\",
    "\\gog galaxy\\games\\",
    "\\riot games\\",
    "\\xboxgames\\",
    "\\ea games\\",
    "\\ubisoft game launcher\\games\\",
]
IGNORE_FOLDERS = {"launcher", "riot client", "steamworks shared", "directx", "directxredist"}
IGNORE_EXES = {
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "epicwebhelper.exe",
    "galaxyclient.exe", "riotclientservices.exe", "riotclientux.exe", "eadesktop.exe",
    "upc.exe", "unitycrashhandler64.exe", "unitycrashhandler32.exe",
    "crashreportclient.exe", "easyanticheat.exe", "easyanticheat_eos.exe", "beservice.exe",
}


def game_from_path(exe):
    """Return the game's folder name if this exe lives in a known game library."""
    if not exe:
        return None
    normalized = exe.replace("/", "\\")
    lowered = normalized.lower()
    for marker in GAME_DIR_MARKERS:
        i = lowered.find(marker)
        if i != -1:
            rest = normalized[i + len(marker):]
            folder = rest.split("\\")[0]
            if folder and "\\" in rest and folder.lower() not in IGNORE_FOLDERS:
                return folder
    return None


def iso(ts):
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def fmt_duration(seconds):
    hours, minutes = divmod(int(seconds or 0) // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


class GamingLogger:
    def __init__(self, config_dir, tray=None, parent=None):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.tray = tray
        self.parent = parent
        self.window = None

        self.db = sqlite3.connect(self.config_dir / "gaming.db")
        self.db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY, game TEXT, start TEXT, end TEXT, seconds INTEGER,
            avg_cpu REAL, avg_gpu REAL, avg_temp REAL, max_temp REAL, max_vram REAL)""")
        # Clean up too-short leftovers from a crash
        self.db.execute("DELETE FROM sessions WHERE seconds < ?", (MIN_SESSION_SEC,))
        self.db.commit()

        self.custom_file = self.config_dir / "custom_games.json"
        self.custom = self.load_custom()

        self.active = {}          # game name -> session dict
        self.last_scan = 0
        self.scanning = False
        self.scan_result = None

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.stop_all)

    # ---------- custom games ----------
    def load_custom(self):
        try:
            return json.loads(self.custom_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def add_custom(self, exe, name):
        self.custom[exe.lower()] = name
        self.custom_file.write_text(json.dumps(self.custom, indent=2))

    # ---------- detection (runs on a background thread) ----------
    def scan(self):
        games = set()
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                info = proc.info
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            name = (info["name"] or "").lower()
            if name in self.custom:
                games.add(self.custom[name])
                continue
            if name in IGNORE_EXES:
                continue
            game = game_from_path(info["exe"])
            if game:
                games.add(game)
        return games

    def _scan_worker(self):
        try:
            self.scan_result = self.scan()
        except psutil.Error:
            logger.exception("Couldn't scan running processes for games")
            self.scan_result = None
        except Exception:
            logger.exception("Unexpected error while scanning for games")
            self.scan_result = None
        finally:
            self.scanning = False

    # ---------- called every second by the dashboard ----------
    def on_stats(self, stats):
        now = time.time()
        if now - self.last_scan >= SCAN_EVERY_SEC and not self.scanning:
            self.last_scan = now
            self.scanning = True
            threading.Thread(target=self._scan_worker, daemon=True).start()

        if self.scan_result is not None:
            running, self.scan_result = self.scan_result, None
            for game in running - self.active.keys():
                self.start(game, now)
            for game in list(self.active.keys() - running):
                self.finish(game, now)

        for s in self.active.values():
            s["samples"] += 1
            s["cpu"] += stats.get("CPU %", 0)
            if "GPU %" in stats:
                s["gpu"] += stats["GPU %"]
                s["gpu_n"] += 1
            temp = stats.get("GPU °C")
            if temp is not None:
                s["temp"] += temp
                s["temp_n"] += 1
                s["max_temp"] = temp if s["max_temp"] is None else max(s["max_temp"], temp)
            s["max_vram"] = max(s["max_vram"], stats.get("VRAM %", 0))
            if now - s["saved"] >= SAVE_EVERY_SEC:
                self.save(s, now)

    # ---------- sessions ----------
    def start(self, game, now):
        cur = self.db.execute(
            "INSERT INTO sessions (game, start, end, seconds) VALUES (?, ?, ?, 0)",
            (game, iso(now), iso(now)))
        self.db.commit()
        self.active[game] = {
            "id": cur.lastrowid, "start_ts": now, "saved": now, "samples": 0,
            "cpu": 0.0, "gpu": 0.0, "gpu_n": 0, "temp": 0.0, "temp_n": 0,
            "max_temp": None, "max_vram": 0.0,
        }

    def save(self, s, now):
        n = s["samples"] or 1
        avg_gpu = s["gpu"] / s["gpu_n"] if s["gpu_n"] else None
        avg_temp = s["temp"] / s["temp_n"] if s["temp_n"] else None
        self.db.execute(
            """UPDATE sessions SET end=?, seconds=?, avg_cpu=?, avg_gpu=?, avg_temp=?,
               max_temp=?, max_vram=? WHERE id=?""",
            (iso(now), int(now - s["start_ts"]), s["cpu"] / n, avg_gpu, avg_temp,
             s["max_temp"], s["max_vram"], s["id"]))
        self.db.commit()
        s["saved"] = now

    def finish(self, game, now, notify=True):
        s = self.active.pop(game)
        self.save(s, now)
        length = now - s["start_ts"]
        if length < MIN_SESSION_SEC:
            self.db.execute("DELETE FROM sessions WHERE id=?", (s["id"],))
            self.db.commit()
            return
        if notify and self.tray:
            extra = f", max {s['max_temp']:.0f}°C" if s["max_temp"] is not None else ""
            self.tray.showMessage("Session logged", f"{game}: {fmt_duration(length)}{extra}",
                                  QSystemTrayIcon.MessageIcon.Information)

    def stop_all(self):
        for game in list(self.active):
            self.finish(game, time.time(), notify=False)

    # ---------- queries ----------
    def recent_sessions(self, limit=50):
        return self.db.execute(
            """SELECT game, start, seconds, avg_cpu, avg_gpu, avg_temp, max_temp
               FROM sessions ORDER BY start DESC LIMIT ?""", (limit,)).fetchall()

    def top_games(self, limit=3):
        return self.db.execute(
            """SELECT game, COUNT(*), SUM(seconds) FROM sessions
               GROUP BY game ORDER BY SUM(seconds) DESC LIMIT ?""", (limit,)).fetchall()

    def show_window(self):
        if self.window is None:
            self.window = GamingWindow(self, self.parent)
        self.window.refresh()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()


def pct(v):
    return "–" if v is None else f"{v:.0f}%"


def deg(v):
    return "–" if v is None else f"{v:.0f}°C"


class GamingWindow(QDialog):
    COLUMNS = ["Game", "Date", "Length", "Avg CPU", "Avg GPU", "Avg temp", "Max temp"]

    def __init__(self, logger, parent=None):
        super().__init__(parent)
        self.logger = logger
        self.setWindowTitle("Gaming sessions")
        self.resize(760, 500)
        layout = QVBoxLayout(self)

        self.now_label = QLabel()
        self.now_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.top_label = QLabel()
        self.top_label.setWordWrap(True)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        buttons = QHBoxLayout()
        add_button = QPushButton("Add a game manually")
        add_button.clicked.connect(self.add_game)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(add_button)
        buttons.addStretch()
        buttons.addWidget(refresh_button)

        layout.addWidget(self.now_label)
        layout.addWidget(self.top_label)
        layout.addWidget(self.table)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.refresh() if self.isVisible() else None)
        self.timer.start(5000)

    def refresh(self):
        now = time.time()
        if self.logger.active:
            playing = [f"{g} ({fmt_duration(now - s['start_ts'])})"
                       for g, s in self.logger.active.items()]
            self.now_label.setText("🎮 Now playing: " + ", ".join(playing))
        else:
            self.now_label.setText("No game running")

        top = self.logger.top_games()
        if top:
            self.top_label.setText("Most played: " + " · ".join(
                f"{g} {fmt_duration(sec)} ({n} sessions)" for g, n, sec in top))
        else:
            self.top_label.setText("No sessions logged yet. Launch a game and it'll show up here.")

        rows = self.logger.recent_sessions()
        self.table.setRowCount(len(rows))
        for r, (game, start, seconds, cpu, gpu, temp, max_temp) in enumerate(rows):
            values = [game, start[:16].replace("T", " "), fmt_duration(seconds),
                      pct(cpu), pct(gpu), deg(temp), deg(max_temp)]
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))

    def add_game(self):
        exe, ok = QInputDialog.getText(
            self, "Add a game", "The game's .exe name (Task Manager → Details tab):")
        if not ok or not exe.strip():
            return
        exe = exe.strip().lower()
        if not exe.endswith(".exe"):
            exe += ".exe"
        name, ok = QInputDialog.getText(self, "Add a game", "Name to show:", text=exe[:-4])
        if ok and name.strip():
            self.logger.add_custom(exe, name.strip())


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Gaming sessions")
    config_dir = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    logger = GamingLogger(config_dir / "DevCommandCenter")
    logger.show_window()

    stats_timer = QTimer(logger.window)
    stats_timer.timeout.connect(lambda: logger.on_stats({
        "CPU %": psutil.cpu_percent(),
        "RAM %": psutil.virtual_memory().percent,
    }))
    stats_timer.start(1000)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())