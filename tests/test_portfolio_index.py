"""Tests for the portfolio index operator tool. No network, no hosting CLI required."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    module = types.ModuleType("portfolio_index")
    module.__file__ = str(ROOT / "scripts" / "portfolio_index.py")
    exec(compile(Path(module.__file__).read_text(encoding="utf-8"),
                 module.__file__, "exec"), module.__dict__)
    return module


class PortfolioIndexTests(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()

    def test_days_since_handles_z_suffix_offset_and_junk(self):
        self.assertIsNone(self.tool.days_since(""))
        self.assertIsNone(self.tool.days_since("not a date"))
        self.assertEqual(self.tool.days_since("2020-01-01T00:00:00Z") > 2000, True)
        self.assertIsInstance(self.tool.days_since("2020-01-01T00:00:00+00:00"), int)

    def test_unreachable_source_is_reported_not_silently_empty(self):
        """An unreachable source must not read as a source with nothing in it."""
        report = self.tool.render([], ["gitlab group x: 404"], {}, "2026-01-01 00:00 UTC")
        self.assertIn("Unreachable sources", report)
        self.assertIn("gitlab group x: 404", report)
        self.assertIn("could not be reached is not the same", report)

    def test_index_lists_unstated_status_and_counts_it(self):
        rows = [
            {"host": "gitlab", "name": "g/a", "visibility": "private",
             "last_activity": "2026-01-01T00:00:00Z", "days_dormant": 300, "description": ""},
            {"host": "github", "name": "o/b", "visibility": "public",
             "last_activity": "", "days_dormant": None, "description": "has | pipe"},
        ]
        report = self.tool.render(rows, [], {"g/a": "primary"}, "2026-01-01 00:00 UTC")
        self.assertIn("| `g/a` | gitlab | private |", report)
        self.assertIn("primary", report)
        self.assertIn("Sources with no stated status", report)
        self.assertIn("`o/b`", report)
        # A pipe in a description must not break the table.
        self.assertIn("has / pipe", report)

    def test_no_sources_is_an_error_not_an_empty_success(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = self.tool.main([])
        self.assertEqual(code, 1)
        self.assertIn("No sources", buffer.getvalue())

    def test_missing_config_is_reported(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = self.tool.main(["--config", "does-not-exist.json"])
        self.assertEqual(code, 1)
        self.assertIn("Config not found", buffer.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
