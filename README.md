# Dev Command Center

A Python desktop app that combines live PC hardware stats with GitHub coding activity in one dark-themed dashboard. Project folder: "pluto's dashboard".

## Current status (October 13, 2026)

- Everything is in a single file, `dev_command_center.py` (~680 lines).
- Confirmed working: automatic dependency install on first launch, the first-run welcome/setup screen, and saving settings.
- **Open bug:** `AttributeError: 'Dashboard' object has no attribute 'show_github'`. The code was pasted in three parts and part 3 lost its indentation, so `show_github` and `closeEvent` ended up outside the `Dashboard` class. Fix: indent both methods 4 spaces so they line up with `def update_stats`. The VS Code AI agent was working on this.
- The file was originally saved without a `.py` extension and needs renaming to `dev_command_center.py`.
- Not yet tested: anything past startup (dashboard panels, tray alerts, settings changes), because of the bug above.

## Environment

- Windows, Python 3.14, VS Code, PowerShell
- Run with: `python dev_command_center.py`

## Features (built)

- **System panel:** live bars for CPU %, RAM %, GPU %, VRAM %, and GPU temp, colored green/yellow/red. Includes a live scrolling graph of GPU temp (or CPU % if there's no NVIDIA GPU).
- **Coding streak panel:** current streak, longest streak, total contributions in the last year, and a GitHub-style contribution heatmap.
- **Stale repo nudger:** lists repos not pushed to in X days (archived repos skipped).
- **Tray icon:** overheat alert (max once per 5 min), a one-time stale repo nudge per session, and a menu with Show / Settings / Quit. Closing the window hides it to the tray (configurable).
- **Settings window:** opened with the ⚙ button, Ctrl+, or the tray menu. Changes apply instantly.
- **First launch:** detects missing packages, asks permission, installs them with a progress window, then shows a welcome setup screen with a "Test GitHub connection" button.

## Settings

Saved at `%APPDATA%\DevCommandCenter\settings.json` (Windows) or `~/.config/DevCommandCenter/settings.json` (Mac/Linux). Delete the file to see the welcome setup again.

| Setting | Default | Meaning |
|---|---|---|
| username | "" | GitHub username |
| token | "" | GitHub personal access token (optional) |
| stale_days | 60 | Days untouched before a repo counts as stale |
| temp_alert | 85 | GPU °C that triggers an overheat alert |
| refresh_min | 30 | How often to re-check GitHub |
| history_sec | 60 | Length of the live graph |
| close_to_tray | true | Closing the window hides it to the tray |

The token is stored as plain text in that file, so never share or upload it. A classic token with the `read:user` scope works; add `repo` to include private repos. Without a token, only public repos show and the streak/heatmap are disabled, because GitHub's contribution data requires authentication.

## Dependencies (auto-installed)

PySide6, pyqtgraph, psutil, requests, nvidia-ml-py

## Code layout (sections of the file, top to bottom)

1. **Bootstrap:** standard library only. Finds missing packages, installs them via pip with a tkinter progress window, and relaunches once if new packages aren't visible.
2. **Settings:** `DEFAULTS`, `load_settings()`, `save_settings()`.
3. **Theme:** Fusion style plus a dark QPalette and a small stylesheet, using GitHub-dark colors.
4. **Hardware:** `read_stats()` uses psutil for CPU/RAM and pynvml for the GPU (NVIDIA only). `heat_color()` thresholds are 60 and 85.
5. **GitHub:** `fetch_stale_repos()` (REST, paginated), `fetch_contributions()` (GraphQL contribution calendar, token required), `calc_streaks()`, `test_connection()`. `GitHubWorker` runs fetches on a daemon thread and emits a `done` signal. If settings change mid-fetch, it re-runs with the new ones.
6. **Widgets:** `Heatmap` (custom QPainter grid, 53 weeks × 7 days), `SettingsDialog` (also used as the first-run welcome), `Dashboard` (main window).
7. **App:** `main()` handles first-run setup, the tray icon and menu, and starts the window.

Data flow: a 1-second QTimer calls `update_stats()`, which updates the bars, graph, and temp alert. A `refresh_min` QTimer calls `GitHubWorker.start()`, which calls `show_github()` when done.

Additional files:

- `app_icon.py`: App icon drawn in code, Windows taskbar ID, and the Start menu shortcut (tray menu → Add to Start menu).
- `features.py`: `FeatureHub`, shared services (`History`, `Notifier`), and one class per planned feature with its plan. Shown in the 🧪 Labs window. All stubs for now.

## Design decisions

- **Desktop app, not a web app:** personal preference.
- **PySide6** over Pygame (no built-in widgets, everything hand-drawn), Textual (terminal only), and CustomTkinter (weaker charting). It has a built-in tray icon and works well with pyqtgraph.
- **Single file for now** so it's easy to share and paste. Split into modules once it grows.
- **Background thread for GitHub** so the window never freezes.
- **GPU support is NVIDIA-only** for now.

## Roadmap

### Next up (in order)
1. Fix the indentation bug and test every feature.
2. **SQLite history:** log system stats and daily commit counts for long-term trend charts.
3. **Achievement badges:** e.g. Night Owl (commits after 2am), Marathon (30-day streak), Necromancer (reviving a repo untouched for a year).
4. **GitHub Wrapped:** a Spotify Wrapped-style year-end summary covering top repo, busiest month, favorite language, and total lines changed.
5. **Crossover stats:** e.g. "your GPU ran hottest on your most productive coding day," or PC uptime vs. commits.

### More feature ideas from brainstorming
- Gaming session logger (detect game launch, record temps/usage per session)
- Electricity cost tracker (power draw × local electricity rate)
- Commit message roaster (rates and mocks lazy commit messages)
- README health checker (grades repos on README, license, description, topics)
- "On this day" in your code (what you worked on 1, 2, 3 years ago)
- Language evolution timeline
- Star, fork, and follower tracker with growth charts
- Daily "what changed" digest, optionally summarized by an LLM
- Benchmark leaderboard (compare runs after driver updates or overclocks)
- Notifications to Discord or Telegram
- AMD and Intel GPU support
- Show GPU power draw (watts)

### Polish and tech debt
- Split into modules: `main.py`, `bootstrap.py`, `settings.py`, `hardware.py`, `github_api.py`, `widgets/`
- Store the token in the OS keychain (`keyring` library) instead of plain-text JSON
- Package as a `.exe` with PyInstaller so it runs without Python installed
- Heatmap hover tooltips and month labels
- Custom tray icon and app icon
- "Start with Windows" option

## Gotchas learned so far

- Pasting code in chunks can strip indentation. Methods must line up with the other `def`s inside their class.
- The file must end in `.py` so VS Code treats it as Python.
- Unauthenticated GitHub API calls are limited to 60 per hour; with a token it's 5,000.
- On some Mac/Linux setups, pip refuses with "externally managed environment." Use a virtual environment.

## For an AI assistant reading this

I'm building this app and want to continue where I left off. Please read this README, ask me for the current `dev_command_center.py` if you need to see the code, and help me with the next item on the roadmap (or whatever I ask). Keep it a Python desktop app using PySide6.