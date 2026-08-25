import json
from pathlib import Path
import unittest

from jsonfold.settings import DEFAULT_SETTINGS, SettingsStore, config_dir, deep_merge, normalize_settings


class SettingsTests(unittest.TestCase):
    def test_platform_locations(self) -> None:
        self.assertEqual(config_dir({"APPDATA": "C:/Profile/AppData/Roaming", "USERPROFILE": "C:/Profile"}, "Windows"), Path("C:/Profile/AppData/Roaming/JSON Fold"))
        self.assertEqual(config_dir({"HOME": "/Users/test"}, "Darwin"), Path("/Users/test/Library/Application Support/JSON Fold"))
        self.assertEqual(config_dir({"HOME": "/home/test", "XDG_CONFIG_HOME": "/tmp/config"}, "Linux"), Path("/tmp/config/json-fold"))

    def test_unknown_keys_are_not_imported(self) -> None:
        merged = deep_merge(DEFAULT_SETTINGS, {"theme": "light", "unsafe": "ignored", "window": {"width": 900, "surprise": True}})
        self.assertEqual(merged["theme"], "light")
        self.assertNotIn("unsafe", merged)
        self.assertNotIn("surprise", merged["window"])

    def test_invalid_values_are_normalized(self) -> None:
        normalized = normalize_settings({"theme": "ultraviolet", "indent": "many", "word_wrap": "yes", "color_scheme": "remote", "recent_files": [1, "ok.json"] * 10, "window": {"width": 1, "height": 99_999}})
        self.assertEqual(normalized["theme"], "dark")
        self.assertEqual(normalized["indent"], 2)
        self.assertIs(normalized["word_wrap"], False)
        self.assertEqual(normalized["color_scheme"], "forge")
        self.assertEqual(normalized["recent_files"], ["ok.json"] * 4)
        self.assertEqual(normalized["window"]["width"], 820)
        self.assertEqual(normalized["window"]["height"], 4320)

    def test_atomic_roundtrip_and_recent_files(self) -> None:
        directory = Path(__file__).parent / "_runtime_roundtrip"
        directory.mkdir(exist_ok=True)
        store = SettingsStore(directory)
        store.data["theme"] = "light"
        store.add_recent(directory / "sample.json")
        store.save()
        loaded = SettingsStore(directory).load()
        self.assertEqual(loaded["theme"], "light")
        self.assertEqual(len(loaded["recent_files"]), 1)
        self.assertFalse((directory / "settings.tmp").exists())

    def test_invalid_settings_fall_back(self) -> None:
        directory = Path(__file__).parent / "_runtime_invalid"
        directory.mkdir(exist_ok=True)
        path = directory / "settings.json"
        path.write_text("not json", encoding="utf-8")
        loaded = SettingsStore(directory).load()
        self.assertEqual(loaded["theme"], "dark")


if __name__ == "__main__":
    unittest.main()
