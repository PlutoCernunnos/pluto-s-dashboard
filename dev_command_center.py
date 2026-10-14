"""
Dev Command Center
Live system stats + GitHub coding streak + stale repo nudger.
Just run it: missing dependencies are installed on first launch.
"""
import importlib
import importlib.util
import json
import os
import site
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ======================================================================
# First launch: install missing dependencies (standard library only)
# ======================================================================
REQUIRED = {  # import name -> pip package name
    "PySide6": "PySide6",
    "pyqtgraph": "pyqtgraph",
    "psutil": "psutil",
    "requests": "requests",
    "pynvml": "nvidia-ml-py",
}


def missing_packages():
    return [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]


def pip_install(packages):
    return subprocess.run([sys.executable, "-m", "pip", "install", *packages],
                          capture_output=True, text=True)


def refresh_import_paths():
    importlib.invalidate_caches()
    if site.ENABLE_USER_SITE:
        user_site = site.getusersitepackages()
        if os.path.isdir(user_site) and user_site not in sys.path:
            site.addsitedir(user_site)


def bootstrap():
    missing = missing_packages()
    if not missing:
        return
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError:  # no tkinter available: use the console instead
        print("First-time setup: installing", ", ".join(missing))
        result = pip_install(missing)
        if result.returncode != 0:
            print(result.stdout, result.stderr)
            sys.exit(1)
        refresh_import_paths()
        return

    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(
            "Dev Command Center",
            "Welcome! First-time setup needs to install:\n\n• "
            + "\n• ".join(missing) + "\n\nInstall now?"):
        sys.exit(0)

    root.deiconify()
    root.title("Setting up Dev Command Center")
    root.resizable(False, False)
    tk.Label(root, text="Installing dependencies...\nThis can take a minute or two.",
             padx=30, pady=15).pack()
    progress = ttk.Progressbar(root, mode="indeterminate", length=280)
    progress.pack(padx=30, pady=(0, 20))
    progress.start(10)

    outcome = {}
    threading.Thread(target=lambda: outcome.update(result=pip_install(missing)),
                     daemon=True).start()

    def wait_for_install():
        if "result" in outcome:
            root.destroy()
        else:
            root.after(200, wait_for_install)

    root.protocol("WM_DELETE_WINDOW", lambda: None)  # don't close mid-install
    root.after(200, wait_for_install)
    root.mainloop()

    result = outcome["result"]
    if result.returncode != 0:
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror("Install failed", "Couldn't install dependencies:\n\n"
                             + (result.stderr or result.stdout)[-1500:])
        sys.exit(1)
    refresh_import_paths()


bootstrap()

try:
    import psutil
    import requests
    from PySide6.QtCore import QObject, Qt, QTimer, Signal
    from PySide6.QtGui import QColor, QKeySequence, QPainter, QPalette, QShortcut
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout,
        QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMenu, QProgressBar,
        QPushButton, QSpinBox, QStyle, QSystemTrayIcon, QVBoxLayout, QWidget,
    )
    import pyqtgraph as pg  # import after PySide6 so it uses the same Qt binding
except ImportError:
    # Rare: new packages aren't visible until Python restarts, so relaunch once
    if os.environ.get("DCC_RELAUNCHED"):
        raise
    os.environ["DCC_RELAUNCHED"] = "1"
    sys.exit(subprocess.call([sys.executable, *sys.argv]))

from app_icon import app_icon, create_start_menu_shortcut, save_ico, set_windows_app_id
from features import FeatureHub

# ======================================================================
# Settings (saved to a JSON file, edited through the Settings window)
# ======================================================================
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "DevCommandCenter"
CONFIG_FILE = CONFIG_DIR / "settings.json"

DEFAULTS = {
    "username": "",
    "token": "",
    "stale_days": 60,
    "temp_alert": 85,
    "refresh_min": 30,
    "history_sec": 60,
    "close_to_tray": True,
}


def load_settings():
    try:
        return {**DEFAULTS, **json.loads(CONFIG_FILE.read_text())}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(settings, indent=2))
    try:
        os.chmod(CONFIG_FILE, 0o600)  # only your user account can read it (Mac/Linux)
    except OSError:
        pass

# ======================================================================
# Theme
# ======================================================================
pg.setConfigOptions(background="#161b22", foreground="#8b949e", antialias=True)

STYLE = """
QGroupBox { border: 1px solid #30363d; border-radius: 8px; margin-top: 14px;
            padding: 10px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #58a6ff; }
QProgressBar { background: #21262d; border: none; border-radius: 4px;
               min-height: 16px; text-align: center; }
QListWidget { border: 1px solid #30363d; border-radius: 6px; }
"""


def apply_dark_theme(app):
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#0d1117",
        QPalette.ColorRole.WindowText: "#e6edf3",
        QPalette.ColorRole.Base: "#161b22",
        QPalette.ColorRole.AlternateBase: "#21262d",
        QPalette.ColorRole.Text: "#e6edf3",
        QPalette.ColorRole.Button: "#21262d",
        QPalette.ColorRole.ButtonText: "#e6edf3",
        QPalette.ColorRole.Highlight: "#1f6feb",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#161b22",
        QPalette.ColorRole.ToolTipText: "#e6edf3",
        QPalette.ColorRole.PlaceholderText: "#6e7681",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)

# ======================================================================
# Hardware
# ======================================================================
try:
    import pynvml as nv
    nv.nvmlInit()
    GPU = nv.nvmlDeviceGetHandleByIndex(0)
    GPU_NAME = nv.nvmlDeviceGetName(GPU)
    if isinstance(GPU_NAME, bytes):
        GPU_NAME = GPU_NAME.decode()
except Exception:
    GPU, GPU_NAME = None, "No NVIDIA GPU detected"


def read_stats():
    stats = {"CPU %": psutil.cpu_percent(), "RAM %": psutil.virtual_memory().percent}
    if GPU:
        mem = nv.nvmlDeviceGetMemoryInfo(GPU)
        stats["GPU %"] = nv.nvmlDeviceGetUtilizationRates(GPU).gpu
        stats["VRAM %"] = 100 * mem.used / mem.total
        stats["GPU °C"] = nv.nvmlDeviceGetTemperature(GPU, nv.NVML_TEMPERATURE_GPU)
    return stats


def heat_color(value):
    if value < 60:
        return "#3fb950"
    if value < 85:
        return "#d29922"
    return "#f85149"

# ======================================================================
# GitHub
# ======================================================================
def gh_headers(token):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_connection(username, token):
    try:
        r = requests.get(f"https://api.github.com/users/{username}",
                         headers=gh_headers(token), timeout=10)
        if r.status_code == 404:
            return False, f"No GitHub user named '{username}'."
        if r.status_code == 401:
            return False, "That token was rejected. Check it and try again."
        r.raise_for_status()
        return True, f"Connected! Found {r.json().get('name') or username}."
    except requests.RequestException as e:
        return False, f"Couldn't reach GitHub: {e}"


def fetch_stale_repos(username, token, stale_days):
    if token:  # includes your private repos
        url, base = "https://api.github.com/user/repos", {"affiliation": "owner"}
    else:      # public repos only
        url, base = f"https://api.github.com/users/{username}/repos", {"type": "owner"}
    now = datetime.now(timezone.utc)
    stale, page = [], 1
    while True:
        r = requests.get(url, headers=gh_headers(token), timeout=15,
                         params={**base, "per_page": 100, "page": page})
        r.raise_for_status()
        batch = r.json()
        for repo in batch:
            if repo["archived"] or not repo["pushed_at"]:
                continue
            pushed = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
            days = (now - pushed).days
            if days >= stale_days:
                stale.append((repo["name"], days))
        if len(batch) < 100:
            break
        page += 1
    return sorted(stale, key=lambda x: -x[1])


CONTRIB_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""


def fetch_contributions(username, token):
    if not token:
        return None
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": CONTRIB_QUERY, "variables": {"login": username}},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    cal = r.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [(date.fromisoformat(d["date"]), d["contributionCount"])
            for week in cal["weeks"] for d in week["contributionDays"]]
    return {"total": cal["totalContributions"], "days": days}
def calc_streaks(days):
    counts = dict(days)
    d = date.today()
    if counts.get(d, 0) == 0:  # today isn't over yet, so start from yesterday
        d -= timedelta(days=1)
    current = 0
    while counts.get(d, 0) > 0:
        current += 1
        d -= timedelta(days=1)
    longest = run = 0
    for _, count in days:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)
    return current, longest


class GitHubWorker(QObject):
    """Fetches GitHub data on a background thread so the window never freezes."""
    done = Signal(object)

    def __init__(self):
        super().__init__()
        self.busy = False
        self.pending = None

    def start(self, settings):
        if not settings["username"]:
            return
        if self.busy:  # a fetch is running; redo it with the new settings after
            self.pending = dict(settings)
            return
        self.busy = True
        threading.Thread(target=self._run, args=(dict(settings),), daemon=True).start()

    def _run(self, s):
        while s:
            result = {}
            try:
                result["stale"] = fetch_stale_repos(s["username"], s["token"], s["stale_days"])
            except Exception as e:
                result["stale_error"] = str(e)
            try:
                result["contrib"] = fetch_contributions(s["username"], s["token"])
            except Exception as e:
                result["contrib_error"] = str(e)
            self.done.emit(result)
            s, self.pending = self.pending, None
        self.busy = False

# ======================================================================
# Widgets
# ======================================================================
class Heatmap(QWidget):
    CELL, GAP = 11, 3
    COLORS = ["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"]

    def __init__(self):
        super().__init__()
        self.days = []
        step = self.CELL + self.GAP
        self.setMinimumSize(54 * step, 7 * step)

    def set_days(self, days):
        self.days = days
        self.update()

    def paintEvent(self, event):
        if not self.days:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        top = max(count for _, count in self.days) or 1
        first = self.days[0][0]
        first_sunday = first - timedelta(days=(first.weekday() + 1) % 7)
        step = self.CELL + self.GAP
        for day, count in self.days:
            col = (day - first_sunday).days // 7
            row = (day.weekday() + 1) % 7  # Sunday on top, like GitHub
            level = 0 if count == 0 else min(4, 1 + int(3 * count / top))
            painter.setBrush(QColor(self.COLORS[level]))
            painter.drawRoundedRect(col * step, row * step, self.CELL, self.CELL, 2, 2)
        painter.end()


class SettingsDialog(QDialog):
    def __init__(self, settings, first_run=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Dev Command Center" if first_run else "Settings")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        if first_run:
            intro = QLabel(
                "<h2>Welcome! 👋</h2>Let's get you set up. Your GitHub username powers the "
                "stale repo list. A token is optional but unlocks your streak, heatmap, and "
                "private repos. You can change all of this later in Settings.")
            intro.setWordWrap(True)
            layout.addWidget(intro)

        form = QFormLayout()
        self.username = QLineEdit(settings["username"])
        self.username.setPlaceholderText("e.g. octocat")
        self.token = QLineEdit(settings["token"])
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Optional: ghp_... or github_pat_...")
        self.stale_days = self.spin(settings["stale_days"], 1, 3650, " days")
        self.temp_alert = self.spin(settings["temp_alert"], 40, 110, " °C")
        self.refresh_min = self.spin(settings["refresh_min"], 5, 1440, " min")
        self.history_sec = self.spin(settings["history_sec"], 10, 600, " sec")
        self.close_to_tray = QCheckBox("Keep running in the tray when I close the window")
        self.close_to_tray.setChecked(settings["close_to_tray"])

        form.addRow("GitHub username", self.username)
        form.addRow("GitHub token", self.token)
        form.addRow("Repo is stale after", self.stale_days)
        form.addRow("GPU heat alert at", self.temp_alert)
        form.addRow("Check GitHub every", self.refresh_min)
        form.addRow("Live graph length", self.history_sec)
        form.addRow("", self.close_to_tray)
        layout.addLayout(form)

        test_row = QHBoxLayout()
        test_button = QPushButton("Test GitHub connection")
        test_button.clicked.connect(self.run_test)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        test_row.addWidget(test_button)
        test_row.addWidget(self.test_result, 1)
        layout.addLayout(test_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        if first_run:
            buttons.button(QDialogButtonBox.StandardButton.Save).setText("Get started")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def spin(value, low, high, suffix):
        box = QSpinBox()
        box.setRange(low, high)
        box.setValue(value)
        box.setSuffix(suffix)
        return box

    def run_test(self):
        username = self.username.text().strip()
        if not username:
            self.show_test(False, "Enter a username first.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        ok, message = test_connection(username, self.token.text().strip())
        QApplication.restoreOverrideCursor()
        self.show_test(ok, message)

    def show_test(self, ok, message):
        self.test_result.setStyleSheet(f"color: {'#3fb950' if ok else '#f85149'};")
        self.test_result.setText(message)

    def values(self):
        return {
            "username": self.username.text().strip(),
            "token": self.token.text().strip(),
            "stale_days": self.stale_days.value(),
            "temp_alert": self.temp_alert.value(),
            "refresh_min": self.refresh_min.value(),
            "history_sec": self.history_sec.value(),
            "close_to_tray": self.close_to_tray.isChecked(),
        }


class Dashboard(QWidget):
    def __init__(self, settings, tray):
        super().__init__()
        self.settings = settings
        self.tray = tray
        self.last_temp_alert = 0
        self.nudged = False
        self.setWindowTitle("Dev Command Center")
        self.resize(820, 800)
        root = QVBoxLayout(self)

        # Header with settings button
        header = QHBoxLayout()
        header.addWidget(QLabel(
            "<span style='font-size:18px; font-weight:bold'>Dev Command Center</span>"))
        header.addStretch()
        self.hub = FeatureHub(self)
        labs_button = QPushButton("🧪  Labs")
        labs_button.clicked.connect(self.hub.show_labs)
        header.addWidget(labs_button)
        settings_button = QPushButton("⚙  Settings")
        settings_button.clicked.connect(self.open_settings)
        header.addWidget(settings_button)
        root.addLayout(header)
        shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        shortcut.activated.connect(self.open_settings)

        # System panel
        sys_box = QGroupBox(f"System  ·  {GPU_NAME}")
        grid = QGridLayout(sys_box)
        self.bars = {}
        for i, name in enumerate(read_stats()):
            bar = QProgressBar()
            bar.setRange(0, 100)
            grid.addWidget(QLabel(name), i, 0)
            grid.addWidget(bar, i, 1)
            self.bars[name] = bar
        self.graph_key = "GPU °C" if GPU else "CPU %"
        self.history = deque()
        self.plot = pg.PlotWidget()
        self.plot.setYRange(0, 100)
        self.plot.setMouseEnabled(False, False)
        self.plot.setMenuEnabled(False)
        self.plot.setMinimumHeight(160)
        self.curve = self.plot.plot([], pen=pg.mkPen("#58a6ff", width=2))
        grid.addWidget(self.plot, len(self.bars), 0, 1, 2)
        root.addWidget(sys_box)

        # Streak panel
        streak_box = QGroupBox("Coding streak")
        streak_layout = QVBoxLayout(streak_box)
        self.streak_label = QLabel()
        self.streak_label.setWordWrap(True)
        self.streak_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.heatmap = Heatmap()
        streak_layout.addWidget(self.streak_label)
        streak_layout.addWidget(self.heatmap)
        root.addWidget(streak_box)

        # Stale repos panel
        self.stale_box = QGroupBox()
        stale_layout = QVBoxLayout(self.stale_box)
        self.repo_list = QListWidget()
        stale_layout.addWidget(self.repo_list)
        root.addWidget(self.stale_box)

        # Timers and background worker
        self.stat_timer = QTimer(self)
        self.stat_timer.timeout.connect(self.update_stats)
        self.stat_timer.start(1000)

        self.worker = GitHubWorker()
        self.worker.done.connect(self.show_github)
        self.gh_timer = QTimer(self)
        self.gh_timer.timeout.connect(lambda: self.worker.start(self.settings))

        self.apply_settings()

    def apply_settings(self):
        s = self.settings
        self.history = deque(self.history, maxlen=s["history_sec"])
        while len(self.history) < s["history_sec"]:  # pad so the graph spans full width
            self.history.appendleft(0)
        self.plot.setTitle(f"{self.graph_key}, last {s['history_sec']}s")
        self.gh_timer.start(s["refresh_min"] * 60 * 1000)

        self.stale_box.setTitle(f"Stale repos ({s['stale_days']}+ days untouched)")
        self.repo_list.clear()
        if not s["username"]:
            self.repo_list.addItem("Add your GitHub username in Settings to see this.")
            self.streak_label.setText("Add your GitHub username in Settings to see your streak.")
            self.heatmap.set_days([])
            return
        self.repo_list.addItem("Loading...")
        if s["token"]:
            self.streak_label.setText("Loading...")
        else:
            self.streak_label.setText("Add a GitHub token in Settings to see your streak and heatmap.")
            self.heatmap.set_days([])
        self.worker.start(s)

    def open_settings(self):
        dialog = SettingsDialog(self.settings, parent=self)
        if dialog.exec():
            self.settings = dialog.values()
            save_settings(self.settings)
            self.apply_settings()

    def update_stats(self):
        stats = read_stats()
        for name, value in stats.items():
            bar = self.bars[name]
            bar.setValue(int(min(value, 100)))
            bar.setFormat(f"{value:.0f}")
            color = heat_color(value)
            if bar.property("chunk_color") != color:  # only restyle on change
                bar.setProperty("chunk_color", color)
                bar.setStyleSheet(
                    f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}")
        self.history.append(stats[self.graph_key])
        self.curve.setData(list(self.history))
        self.hub.on_stats(stats)

        temp = stats.get("GPU °C", 0)
        if temp >= self.settings["temp_alert"] and time.time() - self.last_temp_alert > 300:
            self.last_temp_alert = time.time()
            self.tray.showMessage("GPU running hot", f"{GPU_NAME} is at {temp}°C",
                                  QSystemTrayIcon.MessageIcon.Warning)

    def show_github(self, result):
        self.hub.on_github(result)
        self.repo_list.clear()
        if "stale_error" in result:
            self.repo_list.addItem(f"Couldn't load repos: {result['stale_error']}")
        else:
            stale = result["stale"]
            if not stale:
                self.repo_list.addItem("No stale repos. Nice work!")
            for name, days in stale:
                self.repo_list.addItem(f"{name}  ·  {days} days ago")
            if stale and not self.nudged:
                self.nudged = True
                oldest, days = stale[0]
                self.tray.showMessage(
                    "Repo nudge",
                    f"{len(stale)} repos need some love. {oldest} hasn't been touched in {days} days.",
                    QSystemTrayIcon.MessageIcon.Information)

        if "contrib_error" in result:
            self.streak_label.setText(f"Couldn't load contributions: {result['contrib_error']}")
        elif result.get("contrib"):
            contrib = result["contrib"]
            current, longest = calc_streaks(contrib["days"])
            flame = "🔥" if current else "💤"
            self.streak_label.setText(
                f"{flame} Current streak: {current} days   ·   Longest: {longest} days   ·   "
                f"{contrib['total']} contributions in the last year")
            self.heatmap.set_days(contrib["days"])

    def closeEvent(self, event):
        if self.settings["close_to_tray"] and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()  # keep running in the tray
        else:
            QApplication.quit()

# ======================================================================
# App
# ======================================================================
def main():
    set_windows_app_id()  # makes the taskbar show our icon instead of Python's
    app = QApplication(sys.argv)
    app.setApplicationName("Dev Command Center")
    icon = app_icon()
    app.setWindowIcon(icon)
    apply_dark_theme(app)
    app.setQuitOnLastWindowClosed(False)

    settings = load_settings()
    if not CONFIG_FILE.exists():  # first launch: show the welcome setup
        dialog = SettingsDialog(settings, first_run=True)
        if not dialog.exec():
            return
        settings = dialog.values()
        save_settings(settings)

    tray = QSystemTrayIcon(icon)
    window = Dashboard(settings, tray)

    def show_window():
        window.showNormal()
        window.activateWindow()

    def show_settings():
        show_window()
        window.open_settings()

    def add_to_start_menu():
        try:
            _, message = create_start_menu_shortcut(__file__, save_ico(CONFIG_DIR / "icon.ico"))
        except Exception as e:
            message = f"Couldn't add the shortcut: {e}"
        tray.showMessage("Dev Command Center", message)

    menu = QMenu()
    menu.addAction("Show").triggered.connect(show_window)
    menu.addAction("Settings").triggered.connect(show_settings)
    menu.addAction("Labs").triggered.connect(window.hub.show_labs)
    if sys.platform == "win32":
        menu.addAction("Add to Start menu").triggered.connect(add_to_start_menu)
    menu.addSeparator()
    menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.setToolTip("Dev Command Center")
    tray.show()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()