"""
Feature scaffolding for Dev Command Center.

Every planned feature is a small class below. Each one has:
  name, description, status   shown on its card in the Labs window
  plan                        the step-by-step to-do list for building it
  build_widget()              what it shows in Labs (default: its plan)
  on_stats(stats)             called every second with live system stats
  on_github(result)           called after every GitHub refresh

To work on one: set status to "in progress", follow its plan, and fill in
the methods. Shared building blocks (History, Notifier) are at the top so
every feature can use them through self.hub.
"""
import html
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .gaming_logger import GamingLogger as GamingEngine

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "DevCommandCenter"

STATUS_COLORS = {"planned": "#8b949e", "in progress": "#d29922", "done": "#3fb950"}


# ======================================================================
# Shared services
# ======================================================================
class History:
    """SQLite log of system stats and daily commits. Foundation for trend
    charts, Wrapped, crossover stats, achievements, and the gaming logger.
    FeatureHub already calls these every second / every GitHub refresh.

    Plan:
      1. Open (or create) history.db in the settings folder with sqlite3.
      2. Tables: stats(time, cpu, ram, gpu, vram, gpu_temp)
                 daily_commits(day PRIMARY KEY, count)
      3. log_stats: average the per-second readings, write one row a minute.
      4. log_commits: upsert the contribution calendar.
      5. Query helpers: stats_between(start, end), commits_between(start, end).
    """

    def log_stats(self, stats):
        pass  # TODO

    def log_commits(self, days):
        pass  # TODO


class Notifier:
    """One place to send alerts: the tray today, Discord/Telegram later."""

    def __init__(self, tray):
        self.tray = tray

    def send(self, title, message):
        self.tray.showMessage(title, message)
        # TODO: also post to Discord or Telegram (see RemoteAlerts below)


# ======================================================================
# Feature base class
# ======================================================================
class Feature:
    name = "Unnamed feature"
    description = ""
    status = "planned"  # "planned", "in progress", or "done"
    plan = []

    def __init__(self, hub):
        self.hub = hub  # use hub.settings, hub.history, hub.notifier

    def build_widget(self):
        """What this feature shows in the Labs window. Default: a plan card."""
        return plan_card(self)

    def on_stats(self, stats):
        """Called every second with the latest system stats."""

    def on_github(self, result):
        """Called after every GitHub refresh (stale repos + contributions)."""


def plan_card(feature):
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet("#card { background: #161b22; border: 1px solid #30363d; "
                       "border-radius: 8px; }")
    layout = QVBoxLayout(card)
    color = STATUS_COLORS.get(feature.status, "#8b949e")
    title = QLabel(f"<b style='font-size:15px'>{html.escape(feature.name, quote=False)}</b>"
                   f"&nbsp;&nbsp;<span style='color:{color}'>● {feature.status}</span>")
    title.setTextFormat(Qt.TextFormat.RichText)
    description = QLabel(feature.description)
    description.setWordWrap(True)
    steps = QLabel("<br>".join(f"{i}. {html.escape(step, quote=False)}"
                               for i, step in enumerate(feature.plan, 1)))
    steps.setTextFormat(Qt.TextFormat.RichText)
    steps.setWordWrap(True)
    steps.setStyleSheet("color: #8b949e;")
    for widget in (title, description, steps):
        layout.addWidget(widget)
    return card


# ======================================================================
# Planned features
# ======================================================================
class TrendCharts(Feature):
    name = "History & trend charts"
    description = "Long-term charts of temps, usage, and commits."
    plan = [
        "Fill in the History service at the top of this file.",
        "Add a pyqtgraph chart with a 24h / 7d / 30d selector.",
        "Move the chart onto the main dashboard when it's ready.",
    ]


class Achievements(Feature):
    name = "Achievement badges"
    description = "Unlock game-style badges from your coding and hardware habits."
    plan = [
        "Define badges as data: name, emoji, description, and a check function.",
        "Ideas: Marathon (30-day streak), Necromancer (revive a repo untouched for a year), "
        "Hot Hardware (GPU hits the alert temp), Night Owl (commit after 2am).",
        "Night Owl needs commit times, so fetch them from the REST commits API.",
        "Check badges in on_github / on_stats, save unlocks to History, "
        "and announce them with hub.notifier.",
    ]


class Wrapped(Feature):
    name = "GitHub Wrapped"
    description = "A Spotify Wrapped-style year in review."
    plan = [
        "Gather the year's contribution calendar, repos, and languages.",
        "Compute top repo, busiest month, longest streak, and favorite language.",
        "Build a full-screen slideshow window with one stat per slide.",
        "Add 'Save as image' using QWidget.grab() so it's shareable.",
    ]


class Crossover(Feature):
    name = "Crossover stats"
    description = "Fun facts that mix hardware and coding data."
    plan = [
        "Needs History logging both stats and commits.",
        "Join by day: average GPU temp vs. commits, PC uptime vs. commits.",
        "Show the most surprising fact each day as a card.",
    ]


class GamingLogger(Feature):
    name = "Gaming session logger"
    description = "Detects running games and records a summary of each session."
    status = "done"
    plan = [
        "Detects games in Steam, Epic, GOG, Riot, Xbox, EA, and Ubisoft folders.",
        "Tracks CPU, GPU usage, GPU temp, and VRAM while a game runs.",
        "Saves sessions to gaming.db and sends a tray alert when one ends.",
        "Games outside those folders can be added manually.",
    ]

    def __init__(self, hub):
        super().__init__(hub)
        self.engine = GamingEngine(CONFIG_DIR, hub.dashboard.tray, hub.dashboard)
        hub.gaming = self.engine  # lets the dashboard and tray open the window

    def build_widget(self):
        card = plan_card(self)
        button = QPushButton("🎮 Open gaming sessions")
        button.clicked.connect(self.engine.show_window)
        card.layout().addWidget(button)
        return card

    def on_stats(self, stats):
        self.engine.on_stats(stats)


class PowerCost(Feature):
    name = "Power draw & electricity cost"
    description = "Shows GPU watts and estimates what your PC costs to run."
    plan = [
        "Add GPU watts to read_stats with nvmlDeviceGetPowerUsage (returns milliwatts).",
        "Add 'base system watts' and 'electricity rate' settings.",
        "Add up watt-seconds in on_stats and convert to kWh.",
        "Show today's and this month's estimated cost.",
    ]

    def on_stats(self, stats):
        pass  # TODO: accumulate energy used


class Benchmark(Feature):
    name = "Benchmark leaderboard"
    description = "Compare performance before and after driver updates or overclocks."
    plan = [
        "Write a short timed stress test (e.g. matrix math or a render loop).",
        "Save the score, driver version, and date to History.",
        "Show past runs in a table, best first.",
    ]


class CommitRoaster(Feature):
    name = "Commit message roaster"
    description = "Rates your recent commit messages and gently roasts lazy ones."
    plan = [
        "Fetch recent commits per repo: GET /repos/{owner}/{repo}/commits.",
        "Score messages with simple rules: length, vague words (fix, stuff, asdf), all caps.",
        "Show the worst offenders with a joke and a better suggestion.",
        "Optional: use an LLM API for smarter roasts.",
    ]


class ReadmeChecker(Feature):
    name = "README health checker"
    description = "Grades each repo on how polished it looks."
    plan = [
        "Check each repo for a README, license, description, and topics.",
        "Score out of 100 and list what's missing.",
        "Show a table with the worst repos first.",
    ]


class OnThisDay(Feature):
    name = "On this day"
    description = "What you were coding 1, 2, and 3 years ago today."
    plan = [
        "Query past years with GraphQL contributionsCollection(from:, to:).",
        "Find the repos you pushed to on today's date in those years.",
        "Show a small nostalgic card on the dashboard each day.",
    ]


class LanguageTimeline(Feature):
    name = "Language timeline"
    description = "How your mix of languages has shifted over the years."
    plan = [
        "Fetch each repo's languages: GET /repos/{owner}/{repo}/languages.",
        "Group by the year each repo was created.",
        "Draw a stacked area chart with pyqtgraph.",
    ]


class StarTracker(Feature):
    name = "Star & follower tracker"
    description = "Alerts on new stars, forks, and followers, with growth charts."
    plan = [
        "Extend fetch_stale_repos to also return stargazers_count and forks_count.",
        "Save a snapshot to History on each refresh and compare it with the last one.",
        "Send changes through hub.notifier and chart growth over time.",
    ]


class DailyDigest(Feature):
    name = "Daily digest"
    description = "A morning summary of everything that happened across your repos."
    plan = [
        "Fetch yesterday's events: GET /users/{username}/events.",
        "Group by repo: commits, issues, PRs, and releases.",
        "Send it once a day through hub.notifier, with an optional LLM summary.",
    ]


class RemoteAlerts(Feature):
    name = "Discord / Telegram alerts"
    description = "Get alerts on your phone, not just the tray."
    plan = [
        "Add webhook URL / bot token fields to the Settings window.",
        "Fill in Notifier.send(): Discord is a POST to a webhook URL, "
        "Telegram is the Bot API sendMessage call.",
        "Switch the app's existing tray alerts over to hub.notifier.send().",
    ]


class OtherGPUs(Feature):
    name = "AMD & Intel GPU support"
    description = "Stats for non-NVIDIA graphics cards."
    plan = [
        "Windows: read GPU sensors through LibreHardwareMonitor or WMI.",
        "Linux: read the amdgpu sensors under /sys/class/drm.",
        "Return the same keys read_stats uses so the dashboard just works.",
    ]


FEATURES = [TrendCharts, Achievements, Wrapped, Crossover, GamingLogger, PowerCost,
            Benchmark, CommitRoaster, ReadmeChecker, OnThisDay, LanguageTimeline,
            StarTracker, DailyDigest, RemoteAlerts, OtherGPUs]


# ======================================================================
# Hub and Labs window
# ======================================================================
class FeatureHub:
    """Owns the shared services and every feature, and passes data to them."""

    def __init__(self, dashboard):
        self.dashboard = dashboard
        self.history = History()
        self.notifier = Notifier(dashboard.tray)
        self.features = [cls(self) for cls in FEATURES]
        self.labs = None

    @property
    def settings(self):
        return self.dashboard.settings

    def _each(self, method, *args):
        for feature in self.features:  # one broken feature can't crash the others
            try:
                getattr(feature, method)(*args)
            except Exception as e:
                print(f"[{feature.name}] {method} failed: {e}")

    def on_stats(self, stats):
        self.history.log_stats(stats)
        self._each("on_stats", stats)

    def on_github(self, result):
        if result.get("contrib"):
            self.history.log_commits(result["contrib"]["days"])
        self._each("on_github", result)

    def show_labs(self):
        if self.labs is None:
            self.labs = LabsWindow(self.features)
        self.labs.show()
        self.labs.raise_()
        self.labs.activateWindow()


class LabsWindow(QWidget):
    """Shows a card for every feature in the works."""

    def __init__(self, features):
        super().__init__()
        self.setWindowTitle("Labs · Dev Command Center")
        self.resize(560, 720)
        content = QWidget()
        column = QVBoxLayout(content)
        intro = QLabel("Features in the works. Each card's plan is its to-do list, "
                       "and the code lives in features.py.")
        intro.setWordWrap(True)
        column.addWidget(intro)
        for feature in self.sorted(features):
            column.addWidget(feature.build_widget())
        column.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        QVBoxLayout(self).addWidget(scroll)

    @staticmethod
    def sorted(features):
        order = {"in progress": 0, "planned": 1, "done": 2}
        return sorted(features, key=lambda f: order.get(f.status, 1))