import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
