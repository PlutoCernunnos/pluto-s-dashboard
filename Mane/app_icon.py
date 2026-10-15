"""
App icon (drawn in code, so there are no image files to keep track of)
plus Windows helpers for the taskbar and Start menu.
"""
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QIcon, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)

GREENS = ["#0e4429", "#006d32", "#26a641", "#39d353"]
PATTERN = [0, 1, 2, 3,
           1, 0, 3, 2,
           0, 2, 1, 3,
           1, 3, 2, 3]  # heatmap shades, left to right, top to bottom


def draw_icon(size=256):
    """Dark rounded tile, a 4x4 contribution heatmap, and a blue stats pulse line."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    s = size / 256  # designed at 256px, scaled to any size
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    background = QLinearGradient(0, 0, 0, size)
    background.setColorAt(0, QColor("#1c2333"))
    background.setColorAt(1, QColor("#0d1117"))
    p.setPen(QPen(QColor("#30363d"), 6 * s))
    p.setBrush(background)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 52 * s, 52 * s)

    p.setPen(Qt.PenStyle.NoPen)
    cell, gap, start = 40 * s, 10 * s, 33 * s
    for i, shade in enumerate(PATTERN):
        row, col = divmod(i, 4)
        p.setBrush(QColor(GREENS[shade]))
        p.drawRoundedRect(QRectF(start + col * (cell + gap), start + row * (cell + gap),
                                 cell, cell), 8 * s, 8 * s)

    pulse = QPainterPath(QPointF(40 * s, 150 * s))
    for x, y in [(80, 150), (105, 80), (140, 200), (168, 120), (216, 120)]:
        pulse.lineTo(x * s, y * s)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for color, width in [("#0d1117", 30), ("#58a6ff", 14)]:  # dark outline, then the line
        pen = QPen(QColor(color), width * s)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(pulse)
    p.end()
    return image


def app_icon():
    """The icon at several sizes so it looks sharp everywhere."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(QPixmap.fromImage(draw_icon(size)))
    return icon


def save_ico(path):
    """Saves the icon as a .ico file (Windows shortcuts need one)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not draw_icon(256).save(str(path), "ICO"):
        raise OSError("Couldn't save the icon file")
    return path


def set_windows_app_id(app_id="DevCommandCenter.App"):
    """Makes the Windows taskbar show this app's icon instead of Python's."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)


def create_start_menu_shortcut(script_path, icon_path):
    """Adds 'Dev Command Center' to the Windows Start menu with the custom icon."""
    if sys.platform != "win32":
        return False, "Start menu shortcuts are Windows only."
    programs = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")  # runs without a console window
    script = Path(script_path).resolve()
    env = {  # passed as environment variables so paths with ' or spaces are safe
        **os.environ,
        "DCC_LINK": str(programs / "Dev Command Center.lnk"),
        "DCC_TARGET": str(pythonw if pythonw.exists() else python),
        "DCC_ARGS": f'"{script}"',
        "DCC_DIR": str(script.parent),
        "DCC_ICON": str(Path(icon_path).resolve()),
    }
    command = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:DCC_LINK); "
        "$s.TargetPath = $env:DCC_TARGET; $s.Arguments = $env:DCC_ARGS; "
        "$s.WorkingDirectory = $env:DCC_DIR; $s.IconLocation = $env:DCC_ICON; $s.Save()"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", command], env=env,
                            capture_output=True, text=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode != 0:
        return False, f"Couldn't add the shortcut: {result.stderr.strip()}"
    return True, "Added Dev Command Center to your Start menu."