"""Semantic theme tokens and Tk styling."""

from __future__ import annotations

import ctypes
import platform
import tkinter as tk
from tkinter import ttk
from typing import Any


SHARED = {
    "accent": "#FF982E",
    "accent_hover": "#FFAE58",
    "good": "#32C48D",
    "warning": "#FFB547",
    "danger": "#FF5D6C",
    "neutral": "#6F7B8A",
    "on_accent": "#15181D",
}

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "window": "#14171C",
        "surface": "#1B1E24",
        "surface_alt": "#252A32",
        "control": "#20242B",
        "text": "#F1F4F6",
        "text_muted": "#9EA7B3",
        "border": "#353C47",
        "string": "#9BD89B",
        "number": "#79B8FF",
        "boolean": "#D2A8FF",
        "null": "#FF8E9B",
        "key": "#F1C77A",
    },
    "light": {
        "window": "#F3F5F8",
        "surface": "#FFFFFF",
        "surface_alt": "#E9EDF2",
        "control": "#F8FAFC",
        "text": "#17202A",
        "text_muted": "#5B6572",
        "border": "#C9D0D8",
        "string": "#247A45",
        "number": "#145FB3",
        "boolean": "#7342A8",
        "null": "#B4233C",
        "key": "#8A5300",
    },
}

SYNTAX_SCHEMES: dict[str, dict[str, dict[str, str]]] = {
    "forge": {"dark": {}, "light": {}},
    "colorblind": {
        "dark": {"string": "#56B4E9", "number": "#E69F00", "boolean": "#CC79A7", "null": "#F07A5A", "key": "#F0E442"},
        "light": {"string": "#166B8F", "number": "#8A5600", "boolean": "#8A3F73", "null": "#A83E27", "key": "#665F00"},
    },
    "mono": {
        "dark": {"string": "#D7DCE1", "number": "#F1F4F6", "boolean": "#B8C0CA", "null": "#9EA7B3", "key": "#FF982E"},
        "light": {"string": "#36414D", "number": "#17202A", "boolean": "#4A5663", "null": "#6F7B8A", "key": "#A65300"},
    },
}


def tokens(mode: str, scheme: str = "forge") -> dict[str, str]:
    actual_mode = "light" if mode == "light" else "dark"
    syntax = SYNTAX_SCHEMES.get(scheme, SYNTAX_SCHEMES["forge"])[actual_mode]
    return {**THEMES[actual_mode], **syntax, **SHARED}


def apply_theme(root: tk.Tk, style: ttk.Style, mode: str, scheme: str = "forge") -> dict[str, str]:
    c = tokens(mode, scheme)
    root.configure(bg=c["window"])
    style.theme_use("clam")
    style.configure(".", background=c["window"], foreground=c["text"], fieldbackground=c["control"], bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"], font=("Segoe UI", 9))
    style.configure("TFrame", background=c["window"])
    style.configure("Surface.TFrame", background=c["surface"])
    style.configure("TLabel", background=c["window"], foreground=c["text"])
    style.configure("Surface.TLabel", background=c["surface"], foreground=c["text"])
    style.configure("Muted.TLabel", background=c["surface"], foreground=c["text_muted"])
    style.configure("Heading.TLabel", background=c["surface"], foreground=c["text"], font=("Segoe UI Semibold", 10))
    style.configure("Accent.TLabel", background=c["surface"], foreground=c["accent"], font=("Segoe UI Semibold", 9))
    style.configure("TButton", background=c["control"], foreground=c["text"], borderwidth=1, padding=(10, 6), relief="flat")
    style.map("TButton", background=[("active", c["surface_alt"]), ("pressed", c["surface_alt"])], foreground=[("disabled", c["text_muted"])], bordercolor=[("focus", c["accent"])])
    style.configure("Accent.TButton", background=c["accent"], foreground=c["on_accent"], font=("Segoe UI Semibold", 9))
    style.map("Accent.TButton", background=[("active", c["accent_hover"]), ("pressed", c["accent_hover"])])
    style.configure("Tool.TButton", padding=(8, 5))
    style.configure("TEntry", fieldbackground=c["control"], foreground=c["text"], insertcolor=c["text"], bordercolor=c["border"], padding=(7, 5))
    style.map("TEntry", bordercolor=[("focus", c["accent"])])
    style.configure("TCombobox", fieldbackground=c["control"], background=c["control"], foreground=c["text"], arrowcolor=c["text_muted"], padding=(6, 4))
    style.map("TCombobox", fieldbackground=[("readonly", c["control"])], selectbackground=[("readonly", c["surface_alt"])], selectforeground=[("readonly", c["text"])])
    style.configure("Treeview", background=c["surface"], fieldbackground=c["surface"], foreground=c["text"], borderwidth=0, rowheight=26)
    style.map("Treeview", background=[("selected", c["surface_alt"])], foreground=[("selected", c["text"])])
    style.configure("Treeview.Heading", background=c["surface"], foreground=c["text_muted"], relief="flat", borderwidth=0, padding=(8, 7), font=("Segoe UI Semibold", 9))
    style.map("Treeview.Heading", background=[("active", c["surface_alt"])])
    style.configure("TNotebook", background=c["window"], borderwidth=0, tabmargins=0)
    style.configure("TNotebook.Tab", background=c["surface"], foreground=c["text_muted"], padding=(14, 8), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", c["surface_alt"]), ("active", c["surface_alt"])], foreground=[("selected", c["text"])])
    style.configure("TCheckbutton", background=c["surface"], foreground=c["text"], indicatorcolor=c["control"], padding=4)
    style.map("TCheckbutton", background=[("active", c["surface_alt"])], indicatorcolor=[("selected", c["accent"]), ("!selected", c["control"])])
    style.configure("TPanedwindow", background=c["border"], sashwidth=1)
    style.configure("Vertical.TScrollbar", background=c["control"], troughcolor=c["surface"], arrowcolor=c["text_muted"], borderwidth=0)
    style.configure("Horizontal.TScrollbar", background=c["control"], troughcolor=c["surface"], arrowcolor=c["text_muted"], borderwidth=0)
    _theme_titlebar(root, mode, c)
    return c


def _theme_titlebar(root: tk.Tk, mode: str, c: dict[str, str]) -> None:
    if platform.system() != "Windows":
        return
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        dark = ctypes.c_int(1 if mode == "dark" else 0)
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark))
            if result == 0:
                break
        for attribute, color in ((35, c["surface"]), (36, c["text"]), (34, c["border"])):
            rgb = int(color[1:3], 16) | (int(color[3:5], 16) << 8) | (int(color[5:7], 16) << 16)
            value = ctypes.c_int(rgb)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError, tk.TclError):
        pass
