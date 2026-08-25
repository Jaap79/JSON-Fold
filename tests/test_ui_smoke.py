from pathlib import Path
import unittest
from unittest.mock import patch

from jsonfold.app import JsonFoldApp, SettingsDialog
from jsonfold.settings import SettingsStore


class UiSmokeTests(unittest.TestCase):
    def test_window_tree_search_editor_and_themes(self) -> None:
        directory = Path(__file__).parent / "_runtime_ui"
        directory.mkdir(exist_ok=True)
        with patch("jsonfold.app.SettingsStore", lambda: SettingsStore(directory)):
            app = JsonFoldApp()
            try:
                app.withdraw()
                app.update_idletasks()
                self.assertTrue(app.tree.get_children())
                app.search_var.set("array")
                app.run_search()
                self.assertGreaterEqual(len(app.search_matches), 1)
                original = app.settings["theme"]
                app.toggle_theme()
                self.assertNotEqual(app.settings["theme"], original)
                app.toggle_word_wrap()
                self.assertIn(app.editor.cget("wrap"), ("none", "word"))
                app.notebook.select(app.source_tab)
                app.editor.insert("end-1c", " ")
                app.editor.edit_modified(True)
                app._on_editor_modified()
                self.assertTrue(app.dirty)
                self.assertTrue(app.apply_source())
                dialog = SettingsDialog(app)
                dialog.update_idletasks()
                buttons = []
                stack = [dialog]
                while stack:
                    widget = stack.pop()
                    for child in widget.winfo_children():
                        stack.append(child)
                        if child.winfo_class() == "Button":
                            buttons.append(child)
                self.assertEqual({button.cget("text") for button in buttons}, {"Apply", "Cancel"})
                for button in buttons:
                    self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), dialog.winfo_rooty() + dialog.winfo_height())
                dialog.destroy()
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
