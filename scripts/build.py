"""Build a native one-file executable with PyInstaller."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
separator = ";" if sys.platform == "win32" else ":"
command = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name",
    "JSON-Fold",
    "--icon",
    str(ROOT / "assets" / "icon.ico"),
    "--add-data",
    f"{ROOT / 'assets' / 'icon.png'}{separator}assets",
    str(ROOT / "run_json_fold.py"),
]


if __name__ == "__main__":
    raise SystemExit(subprocess.call(command, cwd=ROOT))
