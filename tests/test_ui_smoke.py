from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from jsonfold.app import AboutDialog, JsonFoldApp, SettingsDialog, iter_syntax_tokens
from jsonfold.settings import SettingsStore


class UiSmokeTests(unittest.TestCase):
    def test_syntax_lexer_keeps_partial_viewport_strings_colored(self) -> None:
        self.assertEqual(list(iter_syntax_tokens('"key": "value')), [("key", 0, 5), ("string", 7, 13)])
        self.assertEqual(list(iter_syntax_tokens('"unfinished')), [("string", 0, 11)])

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
                match_path = app.search_matches[0]
                match_iid = app.path_nodes[match_path]
                self.assertIn("match", app.tree.item(match_iid, "tags"))
                self.assertIn("contains_match", app.tree.item(app.path_nodes[()], "tags"))
                self.assertTrue(app.editor.tag_ranges("search"))
                app.notebook.select(app.source_tab)
                app.next_match()
                self.assertGreaterEqual(app.source_search_index, 0)
                self.assertTrue(app.editor.tag_ranges("sel"))
                app.jump_to_position(2, 3)
                self.assertEqual(app.editor.index("insert"), "2.2")
                before_shortcut = app.editor.get("1.0", "end-1c")
                app.dirty = False
                app.editor.focus_force()
                app.editor.event_generate("<Control-t>")
                app.update()
                self.assertEqual(app.editor.get("1.0", "end-1c"), before_shortcut)
                self.assertFalse(app.dirty)
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
                about = AboutDialog(app)
                about.update_idletasks()
                self.assertIn("not been checked", about.update_status.cget("text"))
                self.assertTrue(about._valid_release_url("https://github.com/Jaap79/JSON-Fold/releases/tag/v1"))
                self.assertFalse(about._valid_release_url("https://example.com/not-a-release"))
                about.destroy()
            finally:
                app.destroy()

    def test_large_source_uses_viewport_syntax_highlighting(self) -> None:
        directory = Path(__file__).parent / "_runtime_ui_large"
        directory.mkdir(exist_ok=True)
        with (
            patch("jsonfold.app.SettingsStore", lambda: SettingsStore(directory)),
            patch("jsonfold.app.MAX_HIGHLIGHT_CHARS", 200_000),
            patch("jsonfold.app.VIEWPORT_HIGHLIGHT_CHARS", 60_000),
        ):
            app = JsonFoldApp()
            try:
                app.withdraw()
                app.after(100, app.quit)
                app.mainloop()
                large_text = '{\n  "items": [\n' + ',\n'.join('    {"name":"item","value":42,"enabled":true}' for _ in range(12_000)) + "\n  ]\n}"
                self.assertGreater(len(large_text), 500_000)
                app.editor.delete("1.0", "end")
                app.editor.insert("1.0", large_text)
                app.highlighted_range = None
                app._highlight_source()
                self.assertTrue(app.editor.tag_ranges("key"))
                self.assertTrue(app.editor.tag_ranges("string"))
                self.assertTrue(app.editor.tag_ranges("number"))
                original = app.editor.tag_cget("string", "foreground")
                app.settings["color_scheme"] = "colorblind"
                app._apply_current_theme()
                self.assertNotEqual(app.editor.tag_cget("string", "foreground"), original)
                one_line = '{"blob":"' + ("x" * 520_000) + '"}'
                app.editor.delete("1.0", "end")
                app.editor.insert("1.0", one_line)
                app.highlighted_range = None
                app._highlight_source()
                self.assertTrue(app.editor.tag_ranges("key"))
                self.assertTrue(app.editor.tag_ranges("string"))
            finally:
                app.destroy()

    @unittest.skipUnless(sys.platform == "win32", "Full 5 MB Tk regression runs on Windows")
    def test_actual_five_mb_single_line_source_is_colored_on_windows(self) -> None:
        directory = Path(__file__).parent / "_runtime_ui_5mb"
        directory.mkdir(exist_ok=True)
        with patch("jsonfold.app.SettingsStore", lambda: SettingsStore(directory)):
            app = JsonFoldApp()
            try:
                app.withdraw()
                one_line = '{"blob":"' + ("x" * 5_200_000) + '"}'
                self.assertGreater(len(one_line), 5_000_000)
                app.editor.delete("1.0", "end")
                app.editor.insert("1.0", one_line)
                app.highlighted_range = None
                app._highlight_source()
                self.assertTrue(app.editor.tag_ranges("key"))
                self.assertTrue(app.editor.tag_ranges("string"))
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
