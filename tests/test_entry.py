"""Smoke test for the `finance-skills` console entry point.

The packaged command maps to `finance_skills._entry:run`, a zero-arg wrapper that
forwards argv to `router.main`. Here we drive it the way the console script does —
argv on `sys.argv` — and confirm `help` exits 0 and prints the grouped help.
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _entry


class TestConsoleEntry(unittest.TestCase):
    def _run(self, *argv):
        out = io.StringIO()
        orig = sys.argv
        sys.argv = ["finance-skills", *argv]
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                with self.assertRaises(SystemExit) as cm:
                    _entry.run()
        finally:
            sys.argv = orig
        code = cm.exception.code or 0
        return code, out.getvalue()

    def test_help_runs_and_exits_zero(self):
        code, text = self._run("help")
        self.assertEqual(code, 0)
        self.assertIn("finance-skills", text)
        self.assertIn("By question:", text)

    def test_no_args_shows_help(self):
        code, text = self._run()
        self.assertEqual(code, 0)
        self.assertIn("Top verbs", text)

    def test_route_subcommand_via_entry(self):
        code, text = self._run("route", "is NBIS a value trap?")
        self.assertEqual(code, 0)
        self.assertIn("risk", text)


if __name__ == "__main__":
    unittest.main()
