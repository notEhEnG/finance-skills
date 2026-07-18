import contextlib
import io
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import watchlist


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = watchlist.main(argv)
    return rc, out.getvalue()


class TestWatchlist(unittest.TestCase):
    def setUp(self):
        # Redirect persistence to a temp dir so tests never touch the real .cache.
        self._tmp = Path("/tmp") / f"finance-skills-watchlist-{uuid.uuid4().hex}"
        self._tmp.mkdir()
        d = self._tmp
        self._orig_store, self._orig_cache = watchlist.STORE, watchlist.CACHE_DIR
        watchlist.STORE = d / "watchlists.json"
        watchlist.CACHE_DIR = d

    def tearDown(self):
        watchlist.STORE, watchlist.CACHE_DIR = self._orig_store, self._orig_cache

    def test_add_list_remove_roundtrip(self):
        _run(["add", "CRWV", "NBIS", "--name=neo"])
        rc, out = _run(["list"])
        self.assertEqual(rc, 0)
        self.assertIn("CRWV", out)
        self.assertIn("NBIS", out)
        _run(["remove", "CRWV", "--name=neo"])
        _, out = _run(["list"])
        self.assertNotIn("CRWV", out)
        self.assertIn("NBIS", out)

    def test_add_is_idempotent(self):
        _run(["add", "CRWV", "--name=neo"])
        _run(["add", "CRWV", "--name=neo"])
        self.assertEqual(watchlist._load()["neo"], ["CRWV"])
        # Both states remain recoverable; persistence never overwrites the first.
        snapshots = [watchlist.STORE, *watchlist.STORE.parent.glob("watchlists-*.json")]
        self.assertEqual(sum(path.is_file() for path in snapshots), 2)

    def test_run_verb_over_list(self):
        _run(["add", "CRWV", "NBIS", "--name=neo"])
        rc, out = _run(["run", "valuation", "--name=neo", "--fixture"])
        self.assertEqual(rc, 0)
        self.assertIn("CRWV", out)
        self.assertIn("NBIS", out)

    def test_run_compare_over_list(self):
        _run(["add", "CRWV", "NBIS", "--name=neo"])
        rc, out = _run(["run", "compare", "--name=neo", "--fixture"])
        self.assertEqual(rc, 0)
        self.assertIn("Compare", out)
        self.assertIn("| **Metric** |", out)
        self.assertIn("🏆", out)

    def test_run_rank_is_comparison_table(self):
        _run(["add", "CRWV", "NBIS", "--name=neo"])
        rc, out = _run(["run", "rank", "--name=neo", "--fixture"])
        self.assertEqual(rc, 0)
        self.assertIn("| **Metric** |", out)
        self.assertIn("🏆", out)

    def test_run_valuation_leads_with_side_by_side_table(self):
        _run(["add", "CRWV", "NBIS", "--name=neo"])
        rc, out = _run(["run", "valuation", "--name=neo", "--fixture"])
        self.assertEqual(rc, 0)
        self.assertIn("side-by-side", out)
        self.assertIn("| **Metric** |", out)
        self.assertIn("🏆", out)

    def test_list_is_table(self):
        _run(["add", "CRWV", "NBIS", "--name=neo"])
        rc, out = _run(["list"])
        self.assertEqual(rc, 0)
        self.assertIn("| **List** |", out)
        self.assertIn("CRWV", out)

    def test_run_empty_list_errors(self):
        rc, _ = _run(["run", "valuation", "--name=empty", "--fixture"])
        self.assertEqual(rc, 1)

    def test_unknown_command_errors(self):
        rc, _ = _run(["frobnicate"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
