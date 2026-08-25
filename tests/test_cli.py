import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from jsonfold.app import build_parser, main


class CliTests(unittest.TestCase):
    def test_parser_accepts_file(self) -> None:
        args = build_parser().parse_args(["sample.json"])
        self.assertEqual(args.file, Path("sample.json"))

    def test_missing_file_fails_without_starting_gui(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = main(["definitely-missing-file.json"])
        self.assertEqual(result, 2)
        self.assertIn("file not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

