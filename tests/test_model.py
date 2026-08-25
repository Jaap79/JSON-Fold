import json
from pathlib import Path
import tempfile
import unittest

from jsonfold.model import (
    collect_stats,
    dump_json_lines,
    dump_minified,
    dump_pretty,
    get_by_path,
    json_type,
    parse_json,
    parse_scalar,
    search_node_paths,
    set_by_path,
)


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.value = {
            "name": "JSON Fold",
            "flags": [True, False, None],
            "nested key": {"answer": 42, "unicode": "café"},
        }

    def test_parse_and_collect_stats(self) -> None:
        result = parse_json(json.dumps(self.value))
        self.assertEqual(result.value, self.value)
        self.assertEqual(result.stats.objects, 2)
        self.assertEqual(result.stats.arrays, 1)
        self.assertEqual(result.stats.keys, 5)
        self.assertEqual(result.stats.booleans, 2)
        self.assertEqual(result.stats.nulls, 1)
        self.assertEqual(result.stats.max_depth, 2)

    def test_duplicate_keys_are_reported_and_last_value_wins(self) -> None:
        result = parse_json('{"role":"reader","role":"editor"}')
        self.assertEqual(result.duplicates, ["role"])
        self.assertEqual(result.value["role"], "editor")

    def test_non_standard_numbers_are_rejected(self) -> None:
        for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_json(text)

    def test_search_returns_machine_safe_paths(self) -> None:
        matches = search_node_paths(self.value, "answer")
        self.assertEqual(matches, [("nested key", "answer")])
        self.assertEqual(search_node_paths(self.value, "café"), [("nested key", "unicode")])

    def test_get_and_set_path(self) -> None:
        self.assertIs(get_by_path(self.value, ("flags", 0)), True)
        set_by_path(self.value, ("nested key", "answer"), 43)
        self.assertEqual(get_by_path(self.value, ("nested key", "answer")), 43)

    def test_scalar_editing(self) -> None:
        self.assertEqual(parse_scalar('"hello"'), "hello")
        self.assertEqual(parse_scalar("12.5"), 12.5)
        self.assertIsNone(parse_scalar("null"))
        with self.assertRaises(ValueError):
            parse_scalar("[]")

    def test_exports(self) -> None:
        self.assertTrue(dump_pretty(self.value).endswith("\n"))
        self.assertNotIn("\n", dump_minified(self.value))
        lines = dump_json_lines([{"a": 1}, {"b": 2}]).splitlines()
        self.assertEqual(len(lines), 2)
        with self.assertRaises(ValueError):
            dump_json_lines(self.value)

    def test_json_types(self) -> None:
        cases = [(None, "null"), (True, "boolean"), ({}, "object"), ([], "array"), (1, "number"), ("x", "string")]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(json_type(value), expected)


if __name__ == "__main__":
    unittest.main()
