import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data

try:
    import pandas as pd
    HAVE_PANDAS = True
except Exception:  # pandas ships with yfinance; skip cleanly where it's absent
    HAVE_PANDAS = False


class TestOrderingNoPandas(unittest.TestCase):
    def test_none_is_passthrough(self):
        self.assertIsNone(data._order_latest_first(None))


class TestNetDebt(unittest.TestCase):
    def _f(self, debt, cash):
        return data.Fundamentals(ticker="X", available=True, total_debt=debt, total_cash=cash)

    def test_none_when_either_side_missing(self):
        self.assertIsNone(self._f(1_000.0, None).net_debt)   # cash unknown
        self.assertIsNone(self._f(None, 500.0).net_debt)     # debt unknown
        self.assertIsNone(self._f(None, None).net_debt)

    def test_computes_when_both_known(self):
        self.assertEqual(self._f(1_000.0, 400.0).net_debt, 600.0)

    def test_real_zero_is_not_treated_as_missing(self):
        # A genuine reported 0.0 (net cash position) must still compute, not None.
        self.assertEqual(self._f(0.0, 750.0).net_debt, -750.0)


@unittest.skipUnless(HAVE_PANDAS, "pandas not installed")
class TestStatementOrdering(unittest.TestCase):
    def _ascending_stmt(self):
        # Columns in ASCENDING date order (older first) — the case that silently
        # swapped latest/prior before _order_latest_first existed.
        return pd.DataFrame(
            [[80.0, 100.0]],
            index=["Total Revenue"],
            columns=[pd.Timestamp("2023-12-31"), pd.Timestamp("2024-12-31")],
        )

    def test_reordered_to_latest_first(self):
        ordered = data._order_latest_first(self._ascending_stmt())
        self.assertEqual(data._col(ordered, ["Total Revenue"], 0), 100.0)  # latest
        self.assertEqual(data._col(ordered, ["Total Revenue"], 1), 80.0)   # prior
        self.assertEqual(data._first(ordered, ["Total Revenue"]), 100.0)

    def test_without_ordering_latest_and_prior_are_swapped(self):
        # Guards the regression: the raw ascending frame really is wrong, so the
        # reorder above is doing real work (not a no-op on already-sorted data).
        raw = self._ascending_stmt()
        self.assertEqual(data._col(raw, ["Total Revenue"], 0), 80.0)  # wrongly "latest"

    def test_non_date_labels_left_unchanged(self):
        df = pd.DataFrame([[1.0, 2.0]], index=["Total Revenue"], columns=["latest", "prior"])
        self.assertIs(data._order_latest_first(df), df)


class TestNumCoercion(unittest.TestCase):
    def test_num_guards(self):
        self.assertIsNone(data._num(None))
        self.assertIsNone(data._num("not-a-number"))
        self.assertIsNone(data._num(float("nan")))
        self.assertEqual(data._num("3.5"), 3.5)
        self.assertEqual(data._num(5), 5.0)


class TestFixtureFallback(unittest.TestCase):
    def test_load_fixture_known_and_unknown(self):
        self.assertEqual(data.load_fixture("crwv").ticker, "CRWV")  # case-insensitive
        self.assertIsNone(data.load_fixture("ZZZZ"))

    def test_or_fixture_falls_back_when_live_unavailable(self):
        # Force the live path to fail (no network in tests) and confirm the
        # fixture fallback kicks in for a ticker that has one, but not otherwise.
        orig = data.get_fundamentals
        data.get_fundamentals = lambda t, use_cache=True: data.Fundamentals(
            ticker=t.upper(), available=False, error="forced-unavailable")
        try:
            self.assertEqual(data.get_fundamentals_or_fixture("CRWV").source, "fixture")
            self.assertFalse(data.get_fundamentals_or_fixture("ZZZZ").available)
        finally:
            data.get_fundamentals = orig


class TestTickerTraversal(unittest.TestCase):
    def setUp(self):
        self._tmp = Path("/tmp") / f"finance-skills-data-{uuid.uuid4().hex}"
        self._tmp.mkdir()
        self._orig = data.CACHE_DIR
        # A nested cache dir so an escaping path would land in the temp root.
        data.CACHE_DIR = self._tmp / "cache"

    def tearDown(self):
        data.CACHE_DIR = self._orig

    def test_normalize_accepts_real_symbols(self):
        self.assertEqual(data.normalize_ticker("nvda"), "NVDA")
        self.assertEqual(data.normalize_ticker(" brk.b "), "BRK.B")
        self.assertEqual(data.normalize_ticker("RDS.A"), "RDS.A")

    def test_normalize_rejects_traversal_and_junk(self):
        for bad in ["../evil", "a/b", "..", "", "/etc/passwd", "x" * 20, ".hidden", "a\\b"]:
            with self.assertRaises(ValueError, msg=f"should reject {bad!r}"):
                data.normalize_ticker(bad)

    def test_cache_path_refuses_to_escape(self):
        for bad in ["../evil", "a/b", ".."]:
            with self.assertRaises(ValueError):
                data._cache_path(bad)

    def test_get_fundamentals_rejects_bad_ticker_without_writing(self):
        f = data.get_fundamentals("../evil", use_cache=False)  # offline: returns before any fetch
        self.assertFalse(f.available)
        self.assertIn("invalid ticker", f.error)
        # Nothing may be written anywhere under the temp root.
        leaked = list(self._tmp.rglob("*.json"))
        self.assertEqual(leaked, [], f"a file escaped the cache dir: {leaked}")

    def test_or_fixture_also_rejects_bad_ticker(self):
        f = data.get_fundamentals_or_fixture("../../etc/passwd", use_cache=False)
        self.assertFalse(f.available)


class TestCache(unittest.TestCase):
    def setUp(self):
        self._tmp = Path("/tmp") / f"finance-skills-cache-{uuid.uuid4().hex}"
        self._tmp.mkdir()
        self._orig_dir, self._orig_ttl = data.CACHE_DIR, data.CACHE_TTL_SECONDS
        data.CACHE_DIR = self._tmp

    def tearDown(self):
        data.CACHE_DIR, data.CACHE_TTL_SECONDS = self._orig_dir, self._orig_ttl

    def _sample(self):
        return data.Fundamentals(ticker="TEST", available=True, revenue=100.0, source="yfinance")

    def test_write_then_read_roundtrip(self):
        data._write_cache(self._sample())
        got = data._read_cache("TEST")
        self.assertIsNotNone(got)
        self.assertEqual(got.revenue, 100.0)
        self.assertEqual(got.data_state, "cache")
        self.assertEqual(len(list(data.CACHE_DIR.glob("TEST-*.json"))), 1)

    def test_cache_writes_are_append_only(self):
        data._write_cache(self._sample())
        data._write_cache(self._sample())
        self.assertEqual(len(list(data.CACHE_DIR.glob("TEST-*.json"))), 2)

    def test_get_fundamentals_serves_fresh_cache_without_network(self):
        data._write_cache(self._sample())
        got = data.get_fundamentals("TEST", use_cache=True)  # must not hit the network
        self.assertTrue(got.available)
        self.assertEqual(got.revenue, 100.0)

    def test_stale_cache_is_ignored(self):
        data._write_cache(self._sample())
        data.CACHE_TTL_SECONDS = -1  # everything is now "stale"
        self.assertIsNone(data._read_cache("TEST"))

    def test_corrupt_cache_is_ignored(self):
        (data.CACHE_DIR / "TEST.json").write_text("{ not json", encoding="utf-8")
        self.assertIsNone(data._read_cache("TEST"))

    def test_missing_cache_returns_none(self):
        self.assertIsNone(data._read_cache("NOPE"))


if __name__ == "__main__":
    unittest.main()
