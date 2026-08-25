"""Cross-platform, atomic user-profile settings storage."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import platform
from typing import Any


APP_DIR = "JSON Fold"

DEFAULT_SETTINGS: dict[str, Any] = {
    "version": 1,
    "theme": "dark",
    "color_scheme": "forge",
    "word_wrap": False,
    "indent": 2,
    "sort_keys": False,
    "show_line_numbers": True,
    "recent_files": [],
    "window": {"width": 1200, "height": 760, "maximized": False},
}


def config_dir(env: dict[str, str] | None = None, system: str | None = None) -> Path:
    env = env or os.environ
    system = system or platform.system()
    home = Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    if system == "Windows":
        return Path(env.get("APPDATA", home / "AppData" / "Roaming")) / APP_DIR
    if system == "Darwin":
        return home / "Library" / "Application Support" / APP_DIR
    return Path(env.get("XDG_CONFIG_HOME", home / ".config")) / "json-fold"


def deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        elif key in merged:
            merged[key] = value
    return merged


def normalize_settings(value: dict[str, Any]) -> dict[str, Any]:
    """Constrain imported/profile values to the supported schema and ranges."""
    merged = deep_merge(DEFAULT_SETTINGS, value)
    merged["theme"] = merged["theme"] if merged["theme"] in {"dark", "light"} else "dark"
    merged["color_scheme"] = merged["color_scheme"] if merged["color_scheme"] in {"forge", "colorblind", "mono"} else "forge"
    merged["indent"] = merged["indent"] if type(merged["indent"]) is int and merged["indent"] in {2, 4} else 2
    for key in ("word_wrap", "sort_keys", "show_line_numbers"):
        merged[key] = merged[key] if type(merged[key]) is bool else DEFAULT_SETTINGS[key]
    recent = merged.get("recent_files")
    merged["recent_files"] = [item for item in recent[:8] if isinstance(item, str)] if isinstance(recent, list) else []
    window = merged["window"]
    width = window.get("width")
    height = window.get("height")
    window["width"] = min(max(width, 820), 7680) if type(width) is int else 1200
    window["height"] = min(max(height, 560), 4320) if type(height) is int else 760
    window["maximized"] = window.get("maximized") if type(window.get("maximized")) is bool else False
    merged["version"] = 1
    return merged


class SettingsStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or config_dir()
        self.path = self.directory / "settings.json"
        self.data = deepcopy(DEFAULT_SETTINGS)

    def load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data = normalize_settings(raw)
        except (OSError, json.JSONDecodeError):
            self.data = deepcopy(DEFAULT_SETTINGS)
        return self.data

    def save(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def export_to(self, path: Path) -> None:
        path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def import_from(self, path: Path) -> dict[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Settings import must contain a JSON object.")
        self.data = normalize_settings(raw)
        self.save()
        return self.data

    def add_recent(self, path: Path) -> None:
        value = str(path.resolve())
        recent = [item for item in self.data.get("recent_files", []) if item != value]
        self.data["recent_files"] = [value, *recent][:8]
