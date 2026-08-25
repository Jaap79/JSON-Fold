"""Tk desktop application for JSON Fold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from . import __version__
from .model import (
    JSON,
    ParseResult,
    child_items,
    collect_stats,
    dump_json_lines,
    dump_minified,
    dump_pretty,
    get_by_path,
    is_container,
    json_type,
    load_json,
    parse_json,
    parse_scalar,
    path_child,
    search_node_paths,
    set_by_path,
    value_preview,
)
from .settings import SettingsStore
from .theme import apply_theme, tokens


APP_NAME = "JSON Fold"
MAX_HIGHLIGHT_CHARS = 2_000_000
TOKEN_RE = re.compile(
    r'(?P<string>"(?:\\.|[^"\\])*")(?P<key>\s*:)?|'
    r'(?P<number>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)|'
    r'(?P<boolean>\b(?:true|false)\b)|(?P<null>\bnull\b)'
)

WELCOME = {
    "welcome": "Open a JSON file or paste JSON from the clipboard.",
    "structure": {
        "objects": "Named key/value groups",
        "arrays": ["Ordered", "zero-indexed", "foldable"],
        "values": {"string": "text", "number": 42, "boolean": True, "null": None},
    },
    "shortcuts": {"open": "Ctrl+O", "find": "Ctrl+F", "apply edits": "Ctrl+Enter"},
}


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class PopupMenu:
    """Themeable popup menu without native white gutters/seams."""

    active: "PopupMenu | None" = None

    def __init__(self, owner: "JsonFoldApp", anchor: tk.Widget, items: list[tuple[str, str, Callable[[], None] | None]]) -> None:
        if PopupMenu.active:
            PopupMenu.active.close()
        self.owner = owner
        self.window = tk.Toplevel(owner)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.transient(owner)
        self.window.configure(bg=owner.colors["border"], padx=1, pady=1)
        body = tk.Frame(self.window, bg=owner.colors["surface"], padx=4, pady=4)
        body.pack(fill="both", expand=True)
        self.rows: list[tuple[tk.Frame, Callable[[], None] | None]] = []
        self.active_index = 0
        for label, shortcut, command in items:
            if label == "-":
                tk.Frame(body, bg=owner.colors["border"], height=1).pack(fill="x", padx=6, pady=4)
                continue
            row = tk.Frame(body, bg=owner.colors["surface"], width=280, height=31, takefocus=True, cursor="hand2")
            row.pack(fill="x")
            row.pack_propagate(False)
            left = tk.Label(row, text=label, anchor="w", bg=owner.colors["surface"], fg=owner.colors["text"], font=("Segoe UI", 9), cursor="hand2")
            left.pack(side="left", fill="both", expand=True, padx=(10, 12))
            right = tk.Label(row, text=shortcut, anchor="e", bg=owner.colors["surface"], fg=owner.colors["text_muted"], font=("Cascadia Mono", 8), cursor="hand2")
            right.pack(side="right", padx=(4, 10))
            index = len(self.rows)
            self.rows.append((row, command))
            for widget in (row, left, right):
                widget.bind("<Button-1>", lambda _e, cmd=command: self.invoke(cmd))
                widget.bind("<Enter>", lambda _e, idx=index: self.select(idx))
            row.bind("<FocusIn>", lambda _e, idx=index: self.select(idx))
        self.window.update_idletasks()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height()
        self.window.geometry(f"+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.window.bind("<Escape>", lambda _e: self.close())
        self.window.bind("<Down>", lambda _e: self.move(1))
        self.window.bind("<Up>", lambda _e: self.move(-1))
        self.window.bind("<Return>", lambda _e: self.invoke_active())
        self.window.bind("<space>", lambda _e: self.invoke_active())
        self.window.bind("<FocusOut>", lambda _e: self.window.after(80, self._close_if_outside))
        PopupMenu.active = self
        if self.rows:
            self.select(0, focus=True)

    def select(self, index: int, *, focus: bool = False) -> None:
        if not self.rows:
            return
        self.active_index = index % len(self.rows)
        for row_index, (row, _) in enumerate(self.rows):
            background = self.owner.colors["surface_alt"] if row_index == self.active_index else self.owner.colors["surface"]
            row.configure(bg=background)
            for child in row.winfo_children():
                child.configure(bg=background)
        if focus:
            self.rows[self.active_index][0].focus_set()

    def move(self, direction: int) -> str:
        self.select(self.active_index + direction, focus=True)
        return "break"

    def invoke_active(self) -> str:
        if self.rows:
            self.invoke(self.rows[self.active_index][1])
        return "break"

    def _close_if_outside(self) -> None:
        try:
            focused = self.window.focus_get()
            if focused is None or focused.winfo_toplevel() != self.window:
                self.close()
        except tk.TclError:
            pass

    def invoke(self, command: Callable[[], None] | None) -> None:
        self.close()
        if command:
            self.owner.after_idle(command)

    def close(self) -> None:
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        if PopupMenu.active is self:
            PopupMenu.active = None


class LineNumberCanvas(tk.Canvas):
    def __init__(self, master: tk.Widget, text: tk.Text, **kwargs: Any) -> None:
        super().__init__(master, highlightthickness=0, width=50, **kwargs)
        self.text = text

    def redraw(self, colors: dict[str, str]) -> None:
        self.delete("all")
        index = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(index)
            if info is None:
                break
            y = info[1]
            line = str(index).split(".")[0]
            self.create_text(42, y, anchor="ne", text=line, fill=colors["text_muted"], font=("Cascadia Mono", 9))
            index = self.text.index(f"{index}+1line")


class JsonFoldApp(tk.Tk):
    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.style = ttk.Style(self)
        self.colors = apply_theme(self, self.style, self.settings["theme"], self.settings["color_scheme"])
        self.title(APP_NAME)
        self._set_window_icon()
        self.minsize(820, 560)
        width = int(self.settings["window"].get("width", 1200))
        height = int(self.settings["window"].get("height", 760))
        self.geometry(f"{max(width, 820)}x{max(height, 560)}")

        self.current_path: Path | None = None
        self.document: JSON = WELCOME
        self.parse_result = ParseResult(WELCOME, collect_stats(WELCOME))
        self.source_snapshot = dump_pretty(WELCOME)
        self.dirty = False
        self.node_paths: dict[str, tuple[str | int, ...]] = {}
        self.path_nodes: dict[tuple[str | int, ...], str] = {}
        self.node_jsonpaths: dict[str, str] = {}
        self.search_matches: list[tuple[str | int, ...]] = []
        self.search_index = -1
        self.highlight_job: str | None = None
        self._build_ui()
        self.editor.configure(wrap="word" if self.settings["word_wrap"] else "none")
        if not self.settings["show_line_numbers"]:
            self.line_numbers.pack_forget()
        self._bind_shortcuts()
        self._load_document(WELCOME, self.source_snapshot, None, ParseResult(WELCOME, collect_stats(WELCOME)))
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.after(80, self._apply_current_theme)
        if initial_path:
            self.after(120, lambda: self.open_path(initial_path))

    # --- UI construction -------------------------------------------------
    def _build_ui(self) -> None:
        self.menu_bar = tk.Frame(self, bg=self.colors["surface"], height=36, highlightbackground=self.colors["border"], highlightthickness=0)
        self.menu_bar.pack(fill="x")
        brand = tk.Frame(self.menu_bar, bg=self.colors["surface"])
        brand.pack(side="left", padx=(8, 10))
        self.logo = tk.Canvas(brand, width=22, height=22, bg=self.colors["surface"], highlightthickness=0)
        self.logo.pack(side="left", pady=6)
        self._draw_logo()
        tk.Label(brand, text="JSON FOLD", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI Semibold", 9)).pack(side="left", padx=(7, 4))
        self.menu_buttons: list[tk.Button] = []
        menus = [("File", self._file_menu), ("Edit", self._edit_menu), ("View", self._view_menu), ("Tools", self._tools_menu), ("Help", self._help_menu)]
        for label, command in menus:
            button = tk.Button(self.menu_bar, text=label, underline=0, command=lambda cmd=command: cmd(), relief="flat", borderwidth=0, padx=10, pady=7, bg=self.colors["surface"], fg=self.colors["text"], activebackground=self.colors["surface_alt"], activeforeground=self.colors["text"], font=("Segoe UI", 9))
            button.pack(side="left")
            self.menu_buttons.append(button)
        self.theme_button = tk.Button(self.menu_bar, text="☾  Dark", command=self.toggle_theme, relief="flat", borderwidth=0, padx=10, pady=7, bg=self.colors["surface"], fg=self.colors["text_muted"], activebackground=self.colors["surface_alt"], activeforeground=self.colors["text"], font=("Segoe UI", 9))
        self.theme_button.pack(side="right", padx=6)

        self.toolbar = tk.Frame(self, bg=self.colors["surface"], highlightbackground=self.colors["border"], highlightthickness=1)
        self.toolbar.pack(fill="x")
        self._plain_button(self.toolbar, "Open", self.open_file).pack(side="left", padx=(8, 2), pady=7)
        self._plain_button(self.toolbar, "Save", self.save_file).pack(side="left", padx=2, pady=7)
        tk.Frame(self.toolbar, bg=self.colors["border"], width=1).pack(side="left", fill="y", padx=8, pady=8)
        self._plain_button(self.toolbar, "Expand all", self.expand_all).pack(side="left", padx=2, pady=7)
        self._plain_button(self.toolbar, "Collapse", self.collapse_all).pack(side="left", padx=2, pady=7)
        self.apply_button = self._plain_button(self.toolbar, "Apply edits", self.apply_source, accent=True)
        self.apply_button.pack(side="right", padx=8, pady=7)

        search_area = tk.Frame(self.toolbar, bg=self.colors["surface"])
        search_area.pack(side="right", padx=(8, 4), pady=7)
        self.search_label = tk.Label(search_area, text="Find", bg=self.colors["surface"], fg=self.colors["text_muted"], font=("Segoe UI", 8))
        self.search_label.pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_area, textvariable=self.search_var, width=26)
        self.search_entry.pack(side="left")
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        self.search_entry.bind("<Return>", lambda _e: self.next_match())
        self.search_count = tk.Label(search_area, text="", width=8, anchor="e", bg=self.colors["surface"], fg=self.colors["text_muted"], font=("Segoe UI", 8))
        self.search_count.pack(side="left", padx=(5, 2))
        self._plain_button(search_area, "↑", self.previous_match, narrow=True).pack(side="left", padx=1)
        self._plain_button(search_area, "↓", self.next_match, narrow=True).pack(side="left", padx=1)

        self.main = ttk.Panedwindow(self, orient="horizontal")
        self.main.pack(fill="both", expand=True, padx=8, pady=8)
        self.content = tk.Frame(self.main, bg=self.colors["surface"], highlightbackground=self.colors["border"], highlightthickness=1)
        self.inspector = tk.Frame(self.main, bg=self.colors["surface"], width=290, highlightbackground=self.colors["border"], highlightthickness=1)
        self.main.add(self.content, weight=5)
        self.main.add(self.inspector, weight=1)

        self.notebook = ttk.Notebook(self.content)
        self.notebook.pack(fill="both", expand=True)
        self.structure_tab = tk.Frame(self.notebook, bg=self.colors["surface"])
        self.source_tab = tk.Frame(self.notebook, bg=self.colors["surface"])
        self.notebook.add(self.structure_tab, text="  Structure  ")
        self.notebook.add(self.source_tab, text="  Source  ")
        self.notebook.bind("<<NotebookTabChanged>>", lambda _e: self._sync_active_tab())
        self._build_tree()
        self._build_editor()
        self._build_inspector()

        self.status = tk.Frame(self, bg=self.colors["surface"], height=28, highlightbackground=self.colors["border"], highlightthickness=1)
        self.status.pack(fill="x")
        self.status_text = tk.Label(self.status, text="Ready", anchor="w", bg=self.colors["surface"], fg=self.colors["text_muted"], font=("Segoe UI", 8))
        self.status_text.pack(side="left", fill="x", expand=True, padx=10, pady=5)
        self.position_text = tk.Label(self.status, text="", anchor="e", bg=self.colors["surface"], fg=self.colors["text_muted"], font=("Cascadia Mono", 8))
        self.position_text.pack(side="right", padx=10)

    def _plain_button(self, parent: tk.Widget, text: str, command: Callable[[], None], *, accent: bool = False, narrow: bool = False) -> tk.Button:
        bg = self.colors["accent"] if accent else self.colors["control"]
        fg = self.colors["on_accent"] if accent else self.colors["text"]
        active = self.colors["accent_hover"] if accent else self.colors["surface_alt"]
        button = tk.Button(parent, text=text, command=command, relief="flat", borderwidth=0, padx=6 if narrow else 10, pady=5, bg=bg, fg=fg, activebackground=active, activeforeground=fg, font=("Segoe UI Semibold" if accent else "Segoe UI", 9), cursor="hand2")
        button.jsonfold_role = "accent" if accent else "control"  # type: ignore[attr-defined]
        return button

    def _draw_logo(self) -> None:
        self.logo.delete("all")
        self.logo.create_rectangle(1, 1, 21, 21, fill=self.colors["surface_alt"], outline=self.colors["border"])
        self.logo.create_line(8, 5, 5, 5, 5, 17, 8, 17, fill=self.colors["text"], width=2)
        self.logo.create_line(14, 5, 17, 5, 17, 17, 14, 17, fill=self.colors["text"], width=2)
        self.logo.create_rectangle(10, 9, 13, 12, fill=self.colors["accent"], outline="")

    def _set_window_icon(self) -> None:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        icon_path = base / "assets" / "icon.png"
        try:
            self._window_icon = tk.PhotoImage(file=icon_path)
            self.iconphoto(True, self._window_icon)
        except tk.TclError:
            self._window_icon = None

    def _build_tree(self) -> None:
        columns = ("value", "type")
        self.tree = ttk.Treeview(self.structure_tab, columns=columns, show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="KEY / INDEX", anchor="w")
        self.tree.heading("value", text="VALUE", anchor="w")
        self.tree.heading("type", text="TYPE", anchor="w")
        self.tree.column("#0", width=290, minwidth=130, stretch=True)
        self.tree.column("value", width=420, minwidth=160, stretch=True)
        self.tree.column("type", width=100, minwidth=80, stretch=False)
        yscroll = ttk.Scrollbar(self.structure_tab, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(self.structure_tab, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.structure_tab.rowconfigure(0, weight=1)
        self.structure_tab.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_open)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected_value())
        self.tree.bind("<Return>", lambda _e: self._toggle_selected())
        self.tree.tag_configure("match", background=self.colors["surface_alt"], foreground=self.colors["accent"])

    def _build_editor(self) -> None:
        editor_frame = tk.Frame(self.source_tab, bg=self.colors["surface"])
        editor_frame.pack(fill="both", expand=True)
        self.editor = tk.Text(editor_frame, undo=True, maxundo=-1, wrap="none", borderwidth=0, highlightthickness=0, padx=10, pady=8, bg=self.colors["surface"], fg=self.colors["text"], insertbackground=self.colors["text"], selectbackground=self.colors["surface_alt"], selectforeground=self.colors["text"], font=("Cascadia Mono", 10), tabs=(28,))
        self.line_numbers = LineNumberCanvas(editor_frame, self.editor, bg=self.colors["surface_alt"])
        yscroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self._editor_yview)
        xscroll = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.editor.xview)
        self.editor.configure(yscrollcommand=lambda first, last: self._on_editor_scroll(first, last, yscroll))
        self.line_numbers.pack(side="left", fill="y")
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.editor.pack(side="left", fill="both", expand=True)
        self.editor.bind("<<Modified>>", self._on_editor_modified)
        self.editor.bind("<KeyRelease>", lambda _e: self._update_cursor())
        self.editor.bind("<ButtonRelease-1>", lambda _e: self._update_cursor())
        for tag in ("key", "string", "number", "boolean", "null", "search", "marked", "error"):
            self.editor.tag_configure(tag)

    def _build_inspector(self) -> None:
        header = tk.Frame(self.inspector, bg=self.colors["surface"])
        header.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(header, text="INSPECTOR", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI Semibold", 9)).pack(side="left")
        self.type_badge = tk.Label(header, text="OBJECT", bg=self.colors["surface_alt"], fg=self.colors["accent"], padx=6, pady=2, font=("Cascadia Mono", 8))
        self.type_badge.pack(side="right")
        self.path_label = tk.Label(self.inspector, text="$", anchor="w", justify="left", wraplength=250, bg=self.colors["surface"], fg=self.colors["text"], font=("Cascadia Mono", 9))
        self.path_label.pack(fill="x", padx=12, pady=(0, 10))
        self.meta_label = tk.Label(self.inspector, text="", anchor="nw", justify="left", bg=self.colors["surface"], fg=self.colors["text_muted"], font=("Segoe UI", 9))
        self.meta_label.pack(fill="x", padx=12)
        separator = tk.Frame(self.inspector, height=1, bg=self.colors["border"])
        separator.pack(fill="x", padx=12, pady=12)
        tk.Label(self.inspector, text="DOCUMENT MAP", anchor="w", bg=self.colors["surface"], fg=self.colors["text"], font=("Segoe UI Semibold", 9)).pack(fill="x", padx=12)
        self.stats_label = tk.Label(self.inspector, text="", anchor="nw", justify="left", bg=self.colors["surface"], fg=self.colors["text_muted"], font=("Cascadia Mono", 9))
        self.stats_label.pack(fill="x", padx=12, pady=(8, 0))
        self.learn_frame = tk.Frame(self.inspector, bg=self.colors["surface_alt"], highlightbackground=self.colors["border"], highlightthickness=1)
        self.learn_frame.pack(fill="x", padx=12, pady=14)
        self.learn_title = tk.Label(self.learn_frame, text="HOW JSON IS BUILT", anchor="w", bg=self.colors["surface_alt"], fg=self.colors["accent"], font=("Segoe UI Semibold", 8))
        self.learn_title.pack(fill="x", padx=9, pady=(8, 4))
        self.learn_text = tk.Label(self.learn_frame, text="Objects contain named keys. Arrays contain ordered items. Values are typed but JSON has no comments.", anchor="nw", justify="left", wraplength=235, bg=self.colors["surface_alt"], fg=self.colors["text"], font=("Segoe UI", 9))
        self.learn_text.pack(fill="x", padx=9, pady=(0, 9))
        self.validation_label = tk.Label(self.inspector, text="✓ Valid JSON", anchor="w", bg=self.colors["surface"], fg=self.colors["good"], font=("Segoe UI Semibold", 9))
        self.validation_label.pack(side="bottom", fill="x", padx=12, pady=12)

    # --- Menus -----------------------------------------------------------
    def _show_menu(self, button_index: int, items: list[tuple[str, str, Callable[[], None] | None]]) -> None:
        PopupMenu(self, self.menu_buttons[button_index], items)

    def _file_menu(self) -> None:
        self._show_menu(0, [("New", "Ctrl+N", self.new_document), ("Open…", "Ctrl+O", self.open_file), ("Paste JSON", "Ctrl+Shift+V", self.paste_json), ("-", "", None), ("Save", "Ctrl+S", self.save_file), ("Save as…", "Ctrl+Shift+S", self.save_as), ("-", "", None), ("Export pretty…", "", lambda: self.export_document("pretty")), ("Export minified…", "", lambda: self.export_document("minified")), ("Export JSON Lines…", "", lambda: self.export_document("jsonl")), ("-", "", None), ("Exit", "Alt+F4", self.close_app)])

    def _edit_menu(self) -> None:
        self._show_menu(1, [("Undo", "Ctrl+Z", lambda: self.editor.event_generate("<<Undo>>")), ("Redo", "Ctrl+Y", lambda: self.editor.event_generate("<<Redo>>")), ("-", "", None), ("Find", "Ctrl+F", self.focus_search), ("Mark selection", "Ctrl+H", self.mark_selection), ("Clear marks", "Ctrl+0", self.clear_marks), ("-", "", None), ("Edit selected value…", "F2", self.edit_selected_value), ("Apply source edits", "Ctrl+Enter", self.apply_source)])

    def _view_menu(self) -> None:
        wrap_label = "Disable word wrap" if self.settings["word_wrap"] else "Enable word wrap"
        self._show_menu(2, [("Structure", "Ctrl+1", lambda: self.notebook.select(self.structure_tab)), ("Source", "Ctrl+2", lambda: self.notebook.select(self.source_tab)), ("-", "", None), ("Expand all", "Ctrl++", self.expand_all), ("Collapse all", "Ctrl+-", self.collapse_all), (wrap_label, "Alt+Z", self.toggle_word_wrap), ("-", "", None), ("Toggle theme", "Ctrl+T", self.toggle_theme)])

    def _tools_menu(self) -> None:
        self._show_menu(3, [("Format document", "Ctrl+Shift+F", self.format_document), ("Copy JSONPath", "Ctrl+Shift+C", self.copy_json_path), ("Copy selected value", "Ctrl+Shift+X", self.copy_selected_value), ("-", "", None), ("Settings…", "Ctrl+,", self.show_settings), ("Export settings…", "", self.export_settings), ("Import settings…", "", self.import_settings)])

    def _help_menu(self) -> None:
        self._show_menu(4, [("JSON quick guide", "F1", self.show_json_guide), ("Keyboard shortcuts", "", self.show_shortcuts), ("-", "", None), (f"About {APP_NAME}", "", self.show_about)])

    # --- Documents -------------------------------------------------------
    def _load_document(self, value: JSON, text: str, path: Path | None, result: ParseResult) -> None:
        self.document = value
        self.parse_result = result
        self.current_path = path
        self.source_snapshot = text
        self.dirty = False
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self._rebuild_tree()
        self._update_stats()
        self._schedule_highlight()
        self._update_title()
        self._set_validation(True)
        label = path.name if path else "Untitled"
        duplicate_note = f" · {len(result.duplicates)} duplicate key(s), last value kept" if result.duplicates else ""
        self._status(f"{label} · {format_bytes(len(text.encode('utf-8')))} · {result.stats.nodes} nodes{duplicate_note}")
        if path:
            self.settings_store.add_recent(path)
            self.settings_store.save()

    def new_document(self) -> None:
        if not self._confirm_discard():
            return
        value: JSON = {}
        self._load_document(value, "{}\n", None, ParseResult(value, collect_stats(value)))
        self.notebook.select(self.source_tab)
        self.editor.focus_set()

    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        value = filedialog.askopenfilename(parent=self, title="Open JSON", filetypes=[("JSON files", "*.json *.geojson"), ("All files", "*.*")])
        if value:
            self.open_path(Path(value))

    def open_path(self, path: Path) -> None:
        started = time.perf_counter()
        try:
            text, result = load_json(path)
        except UnicodeDecodeError:
            self._show_error("Encoding error", "The file is not valid UTF-8. JSON Fold intentionally uses UTF-8/UTF-8-BOM.")
            return
        except json.JSONDecodeError as error:
            self._show_parse_error(error)
            return
        except ValueError as error:
            self._show_error("Invalid JSON", str(error))
            return
        except OSError as error:
            self._show_error("Could not open file", str(error))
            return
        self._load_document(result.value, text, path, result)
        elapsed = (time.perf_counter() - started) * 1000
        self._status(f"Loaded {path.name} in {elapsed:.0f} ms · {result.stats.nodes} nodes · lazy tree")

    def paste_json(self) -> None:
        if not self._confirm_discard():
            return
        try:
            text = self.clipboard_get()
            result = parse_json(text)
        except tk.TclError:
            self._show_error("Clipboard empty", "No text is available on the clipboard.")
            return
        except json.JSONDecodeError as error:
            self._show_parse_error(error)
            return
        except ValueError as error:
            self._show_error("Invalid JSON", str(error))
            return
        self._load_document(result.value, text, None, result)

    def save_file(self) -> None:
        if self.notebook.select() == str(self.source_tab) and self.dirty and not self.apply_source():
            return
        if self.current_path is None:
            self.save_as()
            return
        text = self.editor.get("1.0", "end-1c")
        self._write_document(self.current_path, text.rstrip("\n") + "\n")

    def save_as(self) -> None:
        if self.notebook.select() == str(self.source_tab) and self.dirty and not self.apply_source():
            return
        value = filedialog.asksaveasfilename(parent=self, title="Save JSON", defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if value:
            path = Path(value)
            text = self.editor.get("1.0", "end-1c").rstrip("\n") + "\n"
            if self._write_document(path, text):
                self.current_path = path
                self.settings_store.add_recent(path)
                self.settings_store.save()
                self._update_title()

    def _write_document(self, path: Path, text: str) -> bool:
        try:
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(text, encoding="utf-8", newline="\n")
            temporary.replace(path)
        except OSError as error:
            self._show_error("Could not save file", str(error))
            return False
        self.source_snapshot = text
        self.dirty = False
        self._update_title()
        self._status(f"Saved {path.name} · UTF-8 · {format_bytes(len(text.encode('utf-8')))}")
        return True

    def export_document(self, mode: str) -> None:
        extension = ".jsonl" if mode == "jsonl" else ".json"
        value = filedialog.asksaveasfilename(parent=self, title=f"Export {mode}", defaultextension=extension, filetypes=[("JSON Lines", "*.jsonl")] if mode == "jsonl" else [("JSON files", "*.json")])
        if not value:
            return
        try:
            if mode == "pretty":
                text = dump_pretty(self.document, indent=int(self.settings["indent"]), sort_keys=bool(self.settings["sort_keys"]))
            elif mode == "minified":
                text = dump_minified(self.document)
            else:
                text = dump_json_lines(self.document)
            Path(value).write_text(text, encoding="utf-8", newline="\n")
            self._status(f"Exported {mode}: {Path(value).name}")
        except (OSError, ValueError) as error:
            self._show_error("Export failed", str(error))

    def apply_source(self) -> bool:
        text = self.editor.get("1.0", "end-1c")
        try:
            result = parse_json(text)
        except json.JSONDecodeError as error:
            self._set_validation(False, f"Line {error.lineno}, col {error.colno}")
            self.editor.tag_remove("error", "1.0", "end")
            index = f"{error.lineno}.{max(error.colno - 1, 0)}"
            self.editor.tag_add("error", index, f"{index}+1c")
            self.editor.tag_configure("error", background=self.colors["danger"], foreground=self.colors["on_accent"])
            self.editor.see(index)
            self._show_parse_error(error, text)
            return False
        except ValueError as error:
            self._set_validation(False, "non-standard value")
            self._show_error("Invalid JSON", str(error))
            return False
        self.document = result.value
        self.parse_result = result
        self.source_snapshot = text
        self.dirty = True
        self.editor.edit_modified(False)
        self._rebuild_tree()
        self._update_stats()
        self._set_validation(True)
        duplicate_note = f" · warning: {len(result.duplicates)} duplicate key(s)" if result.duplicates else ""
        self._status(f"Edits applied · {result.stats.nodes} nodes{duplicate_note}")
        self._update_title()
        return True

    def format_document(self) -> None:
        if self.dirty and not self.apply_source():
            return
        text = dump_pretty(self.document, indent=int(self.settings["indent"]), sort_keys=bool(self.settings["sort_keys"]))
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_modified(False)
        self.dirty = True
        self._schedule_highlight()
        self._update_title()
        self._status(f"Formatted with {self.settings['indent']} spaces")

    # --- Tree ------------------------------------------------------------
    def _rebuild_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.node_paths.clear()
        self.path_nodes.clear()
        self.node_jsonpaths.clear()
        root_id = self._insert_node("", "$", self.document, (), "$")
        self.tree.item(root_id, open=True)
        self._populate_node(root_id)

    def _insert_node(self, parent: str, key: str, value: JSON, path: tuple[str | int, ...], jsonpath: str) -> str:
        node_type = json_type(value)
        iid = self.tree.insert(parent, "end", text=key, values=(value_preview(value), node_type), tags=(node_type,))
        self.node_paths[iid] = path
        self.path_nodes[path] = iid
        self.node_jsonpaths[iid] = jsonpath
        if is_container(value) and len(value) > 0:
            self.tree.insert(iid, "end", text="Loading…", tags=("placeholder",))
        return iid

    def _populate_node(self, iid: str) -> None:
        if iid not in self.node_paths:
            return
        children = self.tree.get_children(iid)
        if children and children[0] in self.node_paths:
            return
        for child in children:
            self.tree.delete(child)
        path = self.node_paths[iid]
        value = get_by_path(self.document, path)
        parent_jsonpath = self.node_jsonpaths[iid]
        for key, child_value in child_items(value):
            token: str | int = int(key) if isinstance(value, list) else key
            self._insert_node(iid, key, child_value, path + (token,), path_child(parent_jsonpath, key, value))

    def _on_tree_open(self, _event: tk.Event[Any] | None = None) -> None:
        iid = self.tree.focus()
        if iid:
            self._populate_node(iid)

    def _on_tree_select(self, _event: tk.Event[Any] | None = None) -> None:
        selection = self.tree.selection()
        if not selection or selection[0] not in self.node_paths:
            return
        iid = selection[0]
        path = self.node_paths[iid]
        value = get_by_path(self.document, path)
        self._show_inspection(self.node_jsonpaths[iid], value)

    def _toggle_selected(self) -> None:
        iid = self.tree.focus()
        if iid and is_container(get_by_path(self.document, self.node_paths[iid])):
            self._populate_node(iid)
            self.tree.item(iid, open=not bool(self.tree.item(iid, "open")))

    def expand_all(self) -> None:
        limit = 20_000
        count = 0
        stack = list(self.tree.get_children())
        while stack and count < limit:
            iid = stack.pop()
            self._populate_node(iid)
            self.tree.item(iid, open=True)
            stack.extend(self.tree.get_children(iid))
            count += 1
        self._status(f"Expanded {count} nodes" + (" · stopped at safety limit" if stack else ""))

    def collapse_all(self) -> None:
        for iid in self.node_paths:
            self.tree.item(iid, open=False)
        roots = self.tree.get_children()
        if roots:
            self.tree.item(roots[0], open=True)
        self._status("Collapsed structure")

    def _ensure_node(self, path: tuple[str | int, ...]) -> str | None:
        if path in self.path_nodes:
            return self.path_nodes[path]
        parent_path: tuple[str | int, ...] = ()
        parent_iid = self.path_nodes.get(parent_path)
        if not parent_iid:
            return None
        for part in path:
            self._populate_node(parent_iid)
            self.tree.item(parent_iid, open=True)
            parent_path += (part,)
            parent_iid = self.path_nodes.get(parent_path)
            if not parent_iid:
                return None
        return parent_iid

    def edit_selected_value(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        path = self.node_paths.get(iid)
        if path is None:
            return
        current = get_by_path(self.document, path)
        if is_container(current):
            self._status("Objects and arrays are edited in the Source tab")
            self.notebook.select(self.source_tab)
            return
        dialog = ValueDialog(self, self.node_jsonpaths[iid], current)
        self.wait_window(dialog)
        if dialog.result_set:
            self.document = set_by_path(self.document, path, dialog.result)
            self.parse_result = ParseResult(self.document, collect_stats(self.document))
            text = dump_pretty(self.document, indent=int(self.settings["indent"]), sort_keys=bool(self.settings["sort_keys"]))
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", text)
            self.editor.edit_modified(False)
            self.dirty = True
            self._rebuild_tree()
            new_iid = self._ensure_node(path)
            if new_iid:
                self.tree.selection_set(new_iid)
                self.tree.see(new_iid)
            self._update_stats()
            self._schedule_highlight()
            self._update_title()

    # --- Search and highlighting ----------------------------------------
    def _on_search_changed(self, _event: tk.Event[Any] | None = None) -> None:
        self.after(120, self.run_search)

    def run_search(self) -> None:
        query = self.search_var.get()
        self.editor.tag_remove("search", "1.0", "end")
        self.editor.tag_configure("search", background=self.colors["accent"], foreground=self.colors["on_accent"])
        for iid in self.node_paths:
            tags = tuple(tag for tag in self.tree.item(iid, "tags") if tag != "match")
            self.tree.item(iid, tags=tags)
        if not query:
            self.search_matches = []
            self.search_index = -1
            self.search_count.configure(text="")
            return
        self.search_matches = search_node_paths(self.document, query)
        self.search_index = -1
        start = "1.0"
        source = self.editor.get("1.0", "end-1c")
        if len(source) <= MAX_HIGHLIGHT_CHARS:
            while True:
                found = self.editor.search(query, start, stopindex="end", nocase=True)
                if not found:
                    break
                end = f"{found}+{len(query)}c"
                self.editor.tag_add("search", found, end)
                start = end
        self.search_count.configure(text=f"{len(self.search_matches)} found")
        if self.search_matches:
            self.next_match()

    def next_match(self) -> None:
        if not self.search_matches:
            return
        self.search_index = (self.search_index + 1) % len(self.search_matches)
        self._select_match()

    def previous_match(self) -> None:
        if not self.search_matches:
            return
        self.search_index = (self.search_index - 1) % len(self.search_matches)
        self._select_match()

    def _select_match(self) -> None:
        path = self.search_matches[self.search_index]
        iid = self._ensure_node(path)
        if iid:
            tags = tuple(self.tree.item(iid, "tags")) + ("match",)
            self.tree.item(iid, tags=tags)
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        self.search_count.configure(text=f"{self.search_index + 1}/{len(self.search_matches)}")

    def _schedule_highlight(self) -> None:
        if self.highlight_job:
            self.after_cancel(self.highlight_job)
        self.highlight_job = self.after(180, self._highlight_source)

    def _highlight_source(self) -> None:
        self.highlight_job = None
        text = self.editor.get("1.0", "end-1c")
        for tag in ("key", "string", "number", "boolean", "null"):
            self.editor.tag_remove(tag, "1.0", "end")
        if len(text) > MAX_HIGHLIGHT_CHARS:
            self._status(f"Syntax highlighting paused above {format_bytes(MAX_HIGHLIGHT_CHARS)}; editing remains available")
            return
        for match in TOKEN_RE.finditer(text):
            tag = match.lastgroup
            if tag == "string" and match.group("key"):
                tag = "key"
            if not tag:
                continue
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end('string') if match.lastgroup == 'string' else match.end()}c"
            self.editor.tag_add(tag, start, end)
        for tag in ("key", "string", "number", "boolean", "null"):
            self.editor.tag_configure(tag, foreground=self.colors[tag])

    def mark_selection(self) -> None:
        try:
            first, last = self.editor.index("sel.first"), self.editor.index("sel.last")
        except tk.TclError:
            self._status("Select source text to mark it")
            return
        self.editor.tag_add("marked", first, last)
        self.editor.tag_configure("marked", background=self.colors["warning"], foreground=self.colors["on_accent"])

    def clear_marks(self) -> None:
        self.editor.tag_remove("marked", "1.0", "end")
        self._status("Highlight marks cleared")

    # --- Editor ----------------------------------------------------------
    def _on_editor_modified(self, _event: tk.Event[Any] | None = None) -> None:
        if self.editor.edit_modified():
            self.dirty = True
            self.editor.edit_modified(False)
            self._update_title()
            self._schedule_highlight()
        self.line_numbers.redraw(self.colors)

    def _editor_yview(self, *args: Any) -> None:
        self.editor.yview(*args)
        self.line_numbers.redraw(self.colors)

    def _on_editor_scroll(self, first: str, last: str, scrollbar: ttk.Scrollbar) -> None:
        scrollbar.set(first, last)
        self.line_numbers.redraw(self.colors)

    def _update_cursor(self) -> None:
        line, column = self.editor.index("insert").split(".")
        self.position_text.configure(text=f"Ln {line}, Col {int(column) + 1}")
        self.line_numbers.redraw(self.colors)

    def toggle_word_wrap(self) -> None:
        self.settings["word_wrap"] = not self.settings["word_wrap"]
        self.editor.configure(wrap="word" if self.settings["word_wrap"] else "none")
        self.settings_store.save()
        self._status(f"Word wrap {'enabled' if self.settings['word_wrap'] else 'disabled'}")

    def _sync_active_tab(self) -> None:
        if self.notebook.select() == str(self.source_tab):
            self._update_cursor()
        else:
            self.position_text.configure(text="")

    # --- Inspector -------------------------------------------------------
    def _show_inspection(self, path: str, value: JSON) -> None:
        kind = json_type(value)
        self.path_label.configure(text=path)
        self.type_badge.configure(text=kind.upper())
        if isinstance(value, dict):
            meta = f"{len(value)} keys\nUnordered named members"
            learn = "An object uses { } and maps unique string keys to values. Key order should not carry meaning."
        elif isinstance(value, list):
            meta = f"{len(value)} items\nIndexes 0–{max(len(value)-1, 0)}"
            learn = "An array uses [ ] and keeps order. Items may have different JSON types, although consistent shapes are easier to process."
        elif isinstance(value, str):
            meta = f"{len(value)} characters\nUTF-8 when saved"
            learn = "A string is double-quoted. Quotes, backslashes and control characters must be escaped."
        elif isinstance(value, bool):
            meta = f"Value: {'true' if value else 'false'}\nLowercase in JSON"
            learn = "JSON booleans are the lowercase literals true and false; they are not strings."
        elif value is None:
            meta = "Value: null\nExplicit absence"
            learn = "null is a value. It differs from a missing key and from the strings \"null\" or \"\"."
        else:
            meta = f"Value: {value}\nNo integer/float distinction"
            learn = "JSON has one number type. Very large integers can lose precision in some consumers, notably JavaScript."
        self.meta_label.configure(text=meta)
        self.learn_text.configure(text=learn)

    def _update_stats(self) -> None:
        s = self.parse_result.stats
        self.stats_label.configure(text=f"nodes      {s.nodes:,}\nobjects    {s.objects:,}\narrays     {s.arrays:,}\nkeys       {s.keys:,}\nstrings    {s.strings:,}\nnumbers    {s.numbers:,}\nbooleans   {s.booleans:,}\nnulls      {s.nulls:,}\nmax depth  {s.max_depth:,}")
        self._show_inspection("$", self.document)

    # --- Settings and theme ---------------------------------------------
    def toggle_theme(self) -> None:
        self.settings["theme"] = "light" if self.settings["theme"] == "dark" else "dark"
        self.settings_store.save()
        self._apply_current_theme()

    def _apply_current_theme(self) -> None:
        self.colors = apply_theme(self, self.style, self.settings["theme"], self.settings["color_scheme"])
        for widget in (self.menu_bar, self.toolbar, self.status, self.content, self.inspector, self.structure_tab, self.source_tab):
            widget.configure(bg=self.colors["surface"])
        for widget in (self.toolbar, self.status, self.content, self.inspector):
            widget.configure(highlightbackground=self.colors["border"])
        for widget in self.menu_buttons:
            widget.configure(bg=self.colors["surface"], fg=self.colors["text"], activebackground=self.colors["surface_alt"], activeforeground=self.colors["text"])
        self.theme_button.configure(text="☾  Dark" if self.settings["theme"] == "dark" else "☀  Light", bg=self.colors["surface"], fg=self.colors["text_muted"], activebackground=self.colors["surface_alt"], activeforeground=self.colors["text"])
        for widget in (self.status_text, self.position_text, self.search_count):
            widget.configure(bg=self.colors["surface"], fg=self.colors["text_muted"])
        self.search_label.configure(bg=self.colors["surface"], fg=self.colors["text_muted"])
        self.editor.configure(bg=self.colors["surface"], fg=self.colors["text"], insertbackground=self.colors["text"], selectbackground=self.colors["surface_alt"], selectforeground=self.colors["text"])
        self.line_numbers.configure(bg=self.colors["surface_alt"])
        for widget in (self.path_label, self.meta_label, self.stats_label, self.validation_label):
            widget.configure(bg=self.colors["surface"])
        self.path_label.configure(fg=self.colors["text"])
        self.meta_label.configure(fg=self.colors["text_muted"])
        self.stats_label.configure(fg=self.colors["text_muted"])
        self.type_badge.configure(bg=self.colors["surface_alt"], fg=self.colors["accent"])
        self.learn_frame.configure(bg=self.colors["surface_alt"], highlightbackground=self.colors["border"])
        self.learn_title.configure(bg=self.colors["surface_alt"], fg=self.colors["accent"])
        self.learn_text.configure(bg=self.colors["surface_alt"], fg=self.colors["text"])
        self._draw_logo()
        self._retint_custom_widgets(self)
        self._highlight_source()
        self.line_numbers.redraw(self.colors)

    def _retint_custom_widgets(self, parent: tk.Misc) -> None:
        for widget in parent.winfo_children():
            if isinstance(widget, tk.Button) and hasattr(widget, "jsonfold_role"):
                role = widget.jsonfold_role  # type: ignore[attr-defined]
                if role == "accent":
                    widget.configure(bg=self.colors["accent"], fg=self.colors["on_accent"], activebackground=self.colors["accent_hover"], activeforeground=self.colors["on_accent"])
                else:
                    widget.configure(bg=self.colors["control"], fg=self.colors["text"], activebackground=self.colors["surface_alt"], activeforeground=self.colors["text"])
            elif isinstance(widget, tk.Frame):
                current = str(widget.cget("bg")).lower()
                known_surface = {"#1b1e24", "#ffffff"}
                known_alt = {"#252a32", "#e9edf2"}
                known_border = {"#353c47", "#c9d0d8"}
                if current in known_surface:
                    widget.configure(bg=self.colors["surface"])
                elif current in known_alt:
                    widget.configure(bg=self.colors["surface_alt"])
                elif current in known_border:
                    widget.configure(bg=self.colors["border"])
                try:
                    if str(widget.cget("highlightbackground")).lower() in known_border:
                        widget.configure(highlightbackground=self.colors["border"])
                except tk.TclError:
                    pass
            elif isinstance(widget, tk.Label):
                current = str(widget.cget("bg")).lower()
                foreground = str(widget.cget("fg")).lower()
                if current in {"#1b1e24", "#ffffff"}:
                    widget.configure(bg=self.colors["surface"])
                elif current in {"#252a32", "#e9edf2"}:
                    widget.configure(bg=self.colors["surface_alt"])
                if foreground in {"#f1f4f6", "#17202a"}:
                    widget.configure(fg=self.colors["text"])
                elif foreground in {"#9ea7b3", "#5b6572"}:
                    widget.configure(fg=self.colors["text_muted"])
                elif foreground == "#ff982e":
                    widget.configure(fg=self.colors["accent"])
            self._retint_custom_widgets(widget)

    def show_settings(self) -> None:
        dialog = SettingsDialog(self)
        self.wait_window(dialog)
        if dialog.applied:
            self.editor.configure(wrap="word" if self.settings["word_wrap"] else "none")
            self.line_numbers.pack_forget()
            if self.settings["show_line_numbers"]:
                self.line_numbers.pack(side="left", fill="y", before=self.editor)
            self._apply_current_theme()
            self.settings_store.save()

    def export_settings(self) -> None:
        value = filedialog.asksaveasfilename(parent=self, title="Export settings", defaultextension=".json", initialfile="json-fold-settings.json", filetypes=[("JSON files", "*.json")])
        if value:
            try:
                self.settings_store.export_to(Path(value))
                self._status(f"Settings exported: {Path(value).name}")
            except OSError as error:
                self._show_error("Export failed", str(error))

    def import_settings(self) -> None:
        value = filedialog.askopenfilename(parent=self, title="Import settings", filetypes=[("JSON files", "*.json")])
        if value:
            try:
                self.settings = self.settings_store.import_from(Path(value))
                self._apply_current_theme()
                self.editor.configure(wrap="word" if self.settings["word_wrap"] else "none")
                self._status("Settings imported")
            except (OSError, ValueError, json.JSONDecodeError) as error:
                self._show_error("Import failed", str(error))

    # --- Clipboard and dialogs ------------------------------------------
    def copy_json_path(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        value = self.node_jsonpaths.get(selection[0], "$")
        self.clipboard_clear()
        self.clipboard_append(value)
        self._status(f"Copied JSONPath: {value}")

    def copy_selected_value(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        value = get_by_path(self.document, self.node_paths[selection[0]])
        text = json.dumps(value, ensure_ascii=False, indent=2)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._status("Selected value copied as JSON")

    def show_json_guide(self) -> None:
        text = "JSON has six value types:\n\n• object  { \"key\": value }\n• array   [ value, value ]\n• string  \"text\"\n• number  42 or 3.14\n• boolean true / false\n• null    null\n\nObjects use unique string keys. Arrays preserve order. Standard JSON has no comments or trailing commas."
        InfoDialog(self, "JSON quick guide", text)

    def show_shortcuts(self) -> None:
        text = "Ctrl+O  Open\nCtrl+S  Save\nCtrl+F  Find\nCtrl+1 / Ctrl+2  Structure / Source\nCtrl+Enter  Apply source edits\nCtrl+Shift+F  Format\nCtrl+T  Toggle theme\nAlt+Z  Word wrap\nF2  Edit selected scalar\nEscape  Close popup/dialog"
        InfoDialog(self, "Keyboard shortcuts", text)

    def show_about(self) -> None:
        InfoDialog(self, f"About {APP_NAME}", f"JSON Fold {__version__}\n\nA fast, offline JSON viewer and editor.\nBuilt with the Python standard library.\nNo telemetry. No network access.\n\nSettings:\n{self.settings_store.path}")

    def _show_error(self, title: str, text: str) -> None:
        messagebox.showerror(title, text, parent=self)

    def _show_parse_error(self, error: json.JSONDecodeError, text: str | None = None) -> None:
        source = text if text is not None else error.doc
        lines = source.splitlines()
        excerpt = lines[error.lineno - 1] if 0 < error.lineno <= len(lines) else ""
        pointer = " " * max(error.colno - 1, 0) + "^"
        self._show_error("Invalid JSON", f"{error.msg}\nLine {error.lineno}, column {error.colno}\n\n{excerpt[:140]}\n{pointer[:140]}")

    # --- State and lifecycle --------------------------------------------
    def _bind_shortcuts(self) -> None:
        bindings: dict[str, Callable[[], Any]] = {
            "<Control-n>": self.new_document, "<Control-o>": self.open_file, "<Control-s>": self.save_file,
            "<Control-Shift-S>": self.save_as, "<Control-f>": self.focus_search, "<Control-t>": self.toggle_theme,
            "<Control-Key-1>": lambda: self.notebook.select(self.structure_tab), "<Control-Key-2>": lambda: self.notebook.select(self.source_tab),
            "<Control-Return>": self.apply_source, "<Control-Shift-F>": self.format_document, "<Alt-z>": self.toggle_word_wrap,
            "<F2>": self.edit_selected_value, "<F1>": self.show_json_guide, "<Control-comma>": self.show_settings,
            "<Control-h>": self.mark_selection, "<Control-Key-0>": self.clear_marks,
        }
        for sequence, command in bindings.items():
            self.bind_all(sequence, lambda _e, cmd=command: (cmd(), "break")[1])
        for sequence, command in (("<Alt-f>", self._file_menu), ("<Alt-e>", self._edit_menu), ("<Alt-v>", self._view_menu), ("<Alt-t>", self._tools_menu), ("<Alt-h>", self._help_menu)):
            self.bind_all(sequence, lambda _e, cmd=command: (cmd(), "break")[1])

    def focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")

    def _update_title(self) -> None:
        name = self.current_path.name if self.current_path else "Untitled"
        self.title(f"{'● ' if self.dirty else ''}{name} — {APP_NAME}")

    def _status(self, text: str) -> None:
        self.status_text.configure(text=text)

    def _set_validation(self, valid: bool, details: str = "") -> None:
        if valid:
            self.validation_label.configure(text="✓ Valid JSON", fg=self.colors["good"])
        else:
            self.validation_label.configure(text=f"✕ Invalid JSON · {details}", fg=self.colors["danger"])

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", "Save changes before continuing?", parent=self)
        if answer is None:
            return False
        if answer:
            self.save_file()
            return not self.dirty
        return True

    def close_app(self) -> None:
        if not self._confirm_discard():
            return
        self.settings["window"]["width"] = self.winfo_width()
        self.settings["window"]["height"] = self.winfo_height()
        self.settings_store.save()
        self.destroy()


class BaseDialog(tk.Toplevel):
    def __init__(self, owner: JsonFoldApp, title: str, width: int = 460, height: int = 260) -> None:
        super().__init__(owner)
        self.owner = owner
        self.title(title)
        self.transient(owner)
        self.grab_set()
        self.resizable(False, False)
        self.configure(bg=owner.colors["surface"])
        self.geometry(f"{width}x{height}+{owner.winfo_rootx()+80}+{owner.winfo_rooty()+80}")
        self.bind("<Escape>", lambda _e: self.destroy())
        apply_theme(self, owner.style, owner.settings["theme"], owner.settings["color_scheme"])


class ValueDialog(BaseDialog):
    def __init__(self, owner: JsonFoldApp, path: str, value: JSON) -> None:
        super().__init__(owner, "Edit JSON value", 500, 220)
        self.result: JSON = value
        self.result_set = False
        tk.Label(self, text="EDIT SCALAR", bg=owner.colors["surface"], fg=owner.colors["text"], font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(self, text=path, bg=owner.colors["surface"], fg=owner.colors["text_muted"], font=("Cascadia Mono", 9)).pack(anchor="w", padx=16)
        self.entry = ttk.Entry(self)
        self.entry.pack(fill="x", padx=16, pady=14)
        self.entry.insert(0, json.dumps(value, ensure_ascii=False))
        self.error = tk.Label(self, text="Enter a valid JSON scalar: string, number, true, false or null.", bg=owner.colors["surface"], fg=owner.colors["text_muted"], font=("Segoe UI", 8))
        self.error.pack(anchor="w", padx=16)
        buttons = tk.Frame(self, bg=owner.colors["surface"])
        buttons.pack(side="bottom", fill="x", padx=16, pady=16)
        owner._plain_button(buttons, "Cancel", self.destroy).pack(side="right", padx=(4, 0))
        owner._plain_button(buttons, "Apply", self.apply, accent=True).pack(side="right")
        self.entry.bind("<Return>", lambda _e: self.apply())
        self.entry.focus_set()
        self.entry.selection_range(0, "end")

    def apply(self) -> None:
        try:
            self.result = parse_scalar(self.entry.get())
        except (json.JSONDecodeError, ValueError) as error:
            self.error.configure(text=str(error), fg=self.owner.colors["danger"])
            return
        self.result_set = True
        self.destroy()


class SettingsDialog(BaseDialog):
    def __init__(self, owner: JsonFoldApp) -> None:
        super().__init__(owner, "Settings", 520, 430)
        self.applied = False
        tk.Label(self, text="SETTINGS", bg=owner.colors["surface"], fg=owner.colors["text"], font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=18, pady=(18, 12))
        form = tk.Frame(self, bg=owner.colors["surface"])
        form.pack(fill="x", padx=18)
        self.theme = tk.StringVar(value=owner.settings["theme"])
        self.indent = tk.StringVar(value=str(owner.settings["indent"]))
        self.scheme = tk.StringVar(value=owner.settings["color_scheme"])
        self.wrap = tk.BooleanVar(value=owner.settings["word_wrap"])
        self.lines = tk.BooleanVar(value=owner.settings["show_line_numbers"])
        self.sort = tk.BooleanVar(value=owner.settings["sort_keys"])
        rows = [("Theme", ttk.Combobox(form, textvariable=self.theme, values=("dark", "light"), state="readonly", width=20)), ("Syntax palette", ttk.Combobox(form, textvariable=self.scheme, values=("forge", "colorblind", "mono"), state="readonly", width=20)), ("Indent", ttk.Combobox(form, textvariable=self.indent, values=("2", "4"), state="readonly", width=20))]
        for row, (label, control) in enumerate(rows):
            tk.Label(form, text=label, bg=owner.colors["surface"], fg=owner.colors["text"], font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=8)
            control.grid(row=row, column=1, sticky="ew", padx=(30, 0), pady=8)
        checks = [("Word wrap in Source", self.wrap), ("Show line numbers", self.lines), ("Sort object keys when formatting/exporting", self.sort)]
        for offset, (label, variable) in enumerate(checks, start=3):
            check = ttk.Checkbutton(form, text=label, variable=variable)
            check.grid(row=offset, column=0, columnspan=2, sticky="w", pady=5)
        form.columnconfigure(1, weight=1)
        location = tk.Label(form, text=f"Stored per user in:\n{owner.settings_store.path}", justify="left", anchor="w", wraplength=450, bg=owner.colors["surface_alt"], fg=owner.colors["text_muted"], padx=10, pady=9, font=("Cascadia Mono", 8))
        location.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        buttons = tk.Frame(self, bg=owner.colors["surface"])
        buttons.pack(side="bottom", fill="x", padx=18, pady=18)
        owner._plain_button(buttons, "Cancel", self.destroy).pack(side="right", padx=(4, 0))
        owner._plain_button(buttons, "Apply", self.apply, accent=True).pack(side="right")

    def apply(self) -> None:
        self.owner.settings["theme"] = self.theme.get()
        self.owner.settings["indent"] = int(self.indent.get())
        self.owner.settings["color_scheme"] = self.scheme.get()
        self.owner.settings["word_wrap"] = self.wrap.get()
        self.owner.settings["show_line_numbers"] = self.lines.get()
        self.owner.settings["sort_keys"] = self.sort.get()
        self.applied = True
        self.destroy()


class InfoDialog(BaseDialog):
    def __init__(self, owner: JsonFoldApp, title: str, text: str) -> None:
        height = min(480, max(240, 150 + text.count("\n") * 20))
        super().__init__(owner, title, 520, height)
        tk.Label(self, text=title.upper(), bg=owner.colors["surface"], fg=owner.colors["accent"], font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=18, pady=(18, 10))
        owner._plain_button(self, "Close", self.destroy, accent=True).pack(side="bottom", anchor="e", padx=18, pady=16)
        tk.Label(self, text=text, justify="left", anchor="nw", wraplength=470, bg=owner.colors["surface"], fg=owner.colors["text"], font=("Segoe UI", 9)).pack(fill="both", expand=True, padx=18)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open and inspect JSON files in JSON Fold.")
    parser.add_argument("file", nargs="?", type=Path, help="JSON file to open")
    parser.add_argument("--version", action="version", version=f"JSON Fold {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.file and not args.file.exists():
        print(f"JSON Fold: file not found: {args.file}", file=sys.stderr)
        return 2
    app = JsonFoldApp(args.file)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
