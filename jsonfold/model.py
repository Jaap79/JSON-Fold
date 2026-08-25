"""Pure JSON parsing, inspection, navigation and export helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Iterable, Iterator


JSON = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(slots=True)
class JsonStats:
    objects: int = 0
    arrays: int = 0
    keys: int = 0
    strings: int = 0
    numbers: int = 0
    booleans: int = 0
    nulls: int = 0
    max_depth: int = 0

    @property
    def nodes(self) -> int:
        return self.objects + self.arrays + self.strings + self.numbers + self.booleans + self.nulls


@dataclass(slots=True)
class ParseResult:
    value: JSON
    stats: JsonStats
    duplicates: list[str] = field(default_factory=list)


class DuplicateTracker:
    """object_pairs_hook that records duplicate keys without changing normal semantics."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    def hook(self, pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        seen: set[str] = set()
        for key, value in pairs:
            if key in seen:
                self.keys.append(key)
            seen.add(key)
            result[key] = value
        return result


def parse_json(text: str) -> ParseResult:
    tracker = DuplicateTracker()
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-standard numeric value is not allowed: {value}")

    value = json.loads(text, object_pairs_hook=tracker.hook, parse_constant=reject_constant)
    return ParseResult(value=value, stats=collect_stats(value), duplicates=tracker.keys)


def load_json(path: Path) -> tuple[str, ParseResult]:
    text = path.read_text(encoding="utf-8-sig")
    return text, parse_json(text)


def collect_stats(value: JSON) -> JsonStats:
    stats = JsonStats()
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        stats.max_depth = max(stats.max_depth, depth)
        if isinstance(node, dict):
            stats.objects += 1
            stats.keys += len(node)
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stats.arrays += 1
            stack.extend((child, depth + 1) for child in node)
        elif isinstance(node, bool):
            stats.booleans += 1
        elif node is None:
            stats.nulls += 1
        elif isinstance(node, (int, float)):
            stats.numbers += 1
        else:
            stats.strings += 1
    return stats


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def value_preview(value: Any, limit: int = 100) -> str:
    if isinstance(value, dict):
        return f"{{ {len(value)} keys }}"
    if isinstance(value, list):
        return f"[ {len(value)} items ]"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        rendered = json.dumps(value, ensure_ascii=False)
    else:
        rendered = str(value)
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "…"


def child_items(value: JSON) -> Iterable[tuple[str, JSON]]:
    if isinstance(value, dict):
        return value.items()
    if isinstance(value, list):
        return ((str(index), item) for index, item in enumerate(value))
    return ()


def is_container(value: Any) -> bool:
    return isinstance(value, (dict, list))


def path_child(parent: str, key: str, parent_value: Any) -> str:
    if isinstance(parent_value, list):
        return f"{parent}[{key}]"
    if key.isidentifier():
        return f"{parent}.{key}"
    return f"{parent}[{json.dumps(key, ensure_ascii=False)}]"


def iter_nodes(value: JSON) -> Iterator[tuple[str, str, JSON]]:
    """Depth-first iteration returning JSONPath, key label and value."""
    stack: list[tuple[str, str, Any]] = [("$", "$", value)]
    while stack:
        path, key, node = stack.pop()
        yield path, key, node
        children = list(child_items(node))
        for child_key, child in reversed(children):
            stack.append((path_child(path, child_key, node), child_key, child))


def iter_nodes_with_tokens(value: JSON) -> Iterator[tuple[tuple[str | int, ...], str, str, JSON]]:
    """Depth-first iteration with machine-safe tokens and a display JSONPath."""
    stack: list[tuple[tuple[str | int, ...], str, str, Any]] = [((), "$", "$", value)]
    while stack:
        tokens, path, key, node = stack.pop()
        yield tokens, path, key, node
        children = list(child_items(node))
        for child_key, child in reversed(children):
            token: str | int = int(child_key) if isinstance(node, list) else child_key
            stack.append((tokens + (token,), path_child(path, child_key, node), child_key, child))


def search_nodes(value: JSON, query: str, *, keys: bool = True, values: bool = True) -> list[str]:
    needle = query.casefold()
    if not needle:
        return []
    matches: list[str] = []
    for path, key, node in iter_nodes(value):
        key_match = keys and needle in key.casefold()
        value_match = values and not is_container(node) and needle in value_preview(node, 10_000).casefold()
        if key_match or value_match:
            matches.append(path)
    return matches


def search_node_paths(value: JSON, query: str, *, keys: bool = True, values: bool = True) -> list[tuple[str | int, ...]]:
    needle = query.casefold()
    if not needle:
        return []
    matches: list[tuple[str | int, ...]] = []
    for tokens, _, key, node in iter_nodes_with_tokens(value):
        key_match = keys and needle in key.casefold()
        value_match = values and not is_container(node) and needle in value_preview(node, 10_000).casefold()
        if key_match or value_match:
            matches.append(tokens)
    return matches


def get_by_path(root: JSON, path: tuple[str | int, ...]) -> JSON:
    current: Any = root
    for part in path:
        current = current[part]
    return current


def set_by_path(root: JSON, path: tuple[str | int, ...], value: JSON) -> JSON:
    if not path:
        return value
    parent = get_by_path(root, path[:-1])
    parent[path[-1]] = value  # type: ignore[index]
    return root


def parse_scalar(text: str) -> JSON:
    """Parse one JSON value, rejecting objects/arrays for inline scalar editing."""
    value = json.loads(text)
    if isinstance(value, (dict, list)):
        raise ValueError("Use the Source tab to edit objects or arrays.")
    return value


def dump_pretty(value: JSON, *, indent: int = 2, sort_keys: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent, sort_keys=sort_keys, allow_nan=False) + "\n"


def dump_minified(value: JSON) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def dump_json_lines(value: JSON) -> str:
    if not isinstance(value, list):
        raise ValueError("JSON Lines export requires an array at the root.")
    return "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":"), allow_nan=False) for item in value) + "\n"


def validate_numbers(value: JSON) -> None:
    for _, _, node in iter_nodes(value):
        if isinstance(node, float) and not math.isfinite(node):
            raise ValueError("JSON cannot contain NaN or Infinity.")
