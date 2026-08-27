"""Create deterministic source and Windows release ZIP files."""

from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent
VERSION = "0.2.0"
SOURCE_DIRS = ("jsonfold", "tests", "assets", "scripts", ".github")
SOURCE_FILES = ("pyproject.toml", "run_json_fold.py", "README.md", "CHANGELOG.md", "LICENSE", ".gitignore")


def include(path: Path) -> bool:
    return "__pycache__" not in path.parts and not any(part.startswith("_runtime") for part in path.parts) and path.suffix not in {".pyc", ".pyo"}


def write_source() -> Path:
    target = OUTPUT / f"JSON-Fold-source-v{VERSION}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        paths = [ROOT / name for name in SOURCE_FILES]
        for directory in SOURCE_DIRS:
            paths.extend(path for path in (ROOT / directory).rglob("*") if path.is_file() and include(path))
        for path in sorted(paths):
            archive.write(path, Path("JSON-Fold") / path.relative_to(ROOT))
    return target


def write_windows() -> Path:
    executable = ROOT / "dist" / "JSON-Fold.exe"
    if not executable.exists():
        raise FileNotFoundError("Build dist/JSON-Fold.exe before packaging.")
    target = OUTPUT / f"JSON-Fold-Windows-x64-v{VERSION}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.write(executable, "JSON-Fold.exe")
        archive.write(ROOT / "README.md", "README.md")
        archive.write(ROOT / "LICENSE", "LICENSE")
        archive.write(ROOT / "CHANGELOG.md", "CHANGELOG.md")
        executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest().upper()
        archive.writestr("SHA256SUMS.txt", f"{executable_hash}  JSON-Fold.exe\n")
    return target


if __name__ == "__main__":
    for result in (write_source(), write_windows()):
        print(result)
