# JSON Fold

A fast, offline JSON viewer and editor for Windows, macOS and Linux. JSON Fold presents the same document in two useful forms: a lazy-loaded structure tree for navigation and folding, and a syntax-highlighted source editor for exact changes.

![JSON Fold icon](assets/icon.png)

## Why this shape

JSON is a tree, not a page of colored text. Objects contain named members, arrays contain ordered items, and both may recursively contain more containers. JSON Fold therefore makes the structure view the primary reading surface. Child nodes are materialized only when expanded, so opening a large document does not immediately create a UI row for every value.

The inspector explains the selected node, shows its JSONPath and exposes document-wide counts and maximum depth. It also calls out practical details such as missing keys versus `null`, JavaScript number precision and the fact that object-key order should not carry meaning.

## Features

- Native cross-platform desktop UI built with Python/Tk; no Electron or web server.
- Fully offline: no telemetry, network calls, uploads or remote schemas.
- Lazy expandable/collapsible tree with key, value and type columns.
- Editable source with undo/redo, syntax highlighting, line numbers and optional word wrap.
- Inline editing for scalar values from the structure view.
- Search across keys and scalar values, next/previous navigation and source highlights.
- Persistent text marking for ad-hoc review.
- Strict JSON parsing: rejects comments, trailing commas, `NaN` and infinities.
- Duplicate-key warning; parsing follows common last-value-wins behavior.
- Pretty, minified and JSON Lines export; JSON Lines requires a root array.
- Import/export of settings.
- Dark mode by default, complete light mode and three syntax palettes: Forge, colorblind and mono.
- Per-user atomic settings storage:
  - Windows: `%APPDATA%\JSON Fold\settings.json`
  - macOS: `~/Library/Application Support/JSON Fold/settings.json`
  - Linux: `$XDG_CONFIG_HOME/json-fold/settings.json` or `~/.config/json-fold/settings.json`

Syntax highlighting is intentionally paused above 2 MB while editing remains available. This prevents highlighting from monopolizing the UI on very large files. Tree expansion has a 20,000-node safety limit for “Expand all”; manual lazy navigation remains available.

## Run from source

Requirements: Python 3.10+ with Tk support. Runtime dependencies: none outside the standard library.

```bash
python -m jsonfold
python -m jsonfold path/to/file.json
```

## Keyboard map

| Action | Shortcut |
|---|---|
| Open / Save | `Ctrl+O` / `Ctrl+S` |
| Find | `Ctrl+F` |
| Structure / Source | `Ctrl+1` / `Ctrl+2` |
| Apply source edits | `Ctrl+Enter` |
| Format | `Ctrl+Shift+F` |
| Toggle theme | `Ctrl+T` |
| Toggle word wrap | `Alt+Z` |
| Edit selected scalar | `F2` |
| Mark / clear source highlight | `Ctrl+H` / `Ctrl+0` |

On macOS, Tk maps standard Command-key editing shortcuts through the platform. The explicit application shortcuts currently use Control consistently across platforms.

## Test

```bash
python -m unittest discover -s tests -v
```

The suite covers strict parsing, duplicate keys, statistics, path-safe search, scalar edits, all export formats, per-OS settings paths, atomic settings and a live Tk smoke test across tree/search/editor/theme state.

## Build a native executable

Install build-only dependencies, generate assets and run the platform-local build:

```bash
python -m pip install pyinstaller pillow
python scripts/generate_icon.py
python scripts/build.py
```

The result appears in `dist/`. Native executables must be built on their target OS; GitHub Actions does this for all three platforms.

### Native chrome note

On Windows 10/11, JSON Fold explicitly recolors the native caption, title text and border when the app theme changes. On macOS and Linux, the client area and all custom popup menus are fully themed, while the native title bar follows the active window manager/desktop appearance. This preserves native resizing, system menus and accessibility instead of replacing them with fragile custom chrome.

## Security and privacy

JSON Fold never evaluates document content, resolves URLs, loads external schemas or interprets keys as commands. Files remain local. Settings contain UI preferences and recent file paths only. Writes for normal Save operations use a same-directory temporary file followed by an atomic replace.

Do not treat the viewer as a sanitizer: a JSON document can still contain secrets, malicious strings for downstream systems or extremely large/deep structures. Duplicate keys are reported because different consumers may interpret them differently.

## Release readiness

The repository includes an MIT license, platform build workflow, test workflow, issue template, changelog and a three-color project-specific icon. Code signing and notarization are intentionally not configured because they require repository-owner certificates and secrets.
