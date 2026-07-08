import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import metrics


class TestRegime(unittest.TestCase):
    def test_neocloud_needs_growth_and_capex(self):
        # CoreWeave-like: 112% growth + very heavy capex.
        self.assertEqual(metrics.classify_regime(112, 463), metrics.REGIME_NEOCLOUD)

    def test_hypergrowth_without_heavy_capex(self):
        self.assertEqual(metrics.classify_regime(150, 10), metrics.REGIME_HYPERGROWTH)

    def test_traditional(self):
        self.assertEqual(metrics.classify_regime(28, 6), metrics.REGIME_TRADITIONAL)

    def test_early_stage_by_revenue(self):
        self.assertEqual(metrics.classify_regime(60, 5, revenue=500_000), metrics.REGIME_EARLY)


class TestRule40(unittest.TestCase):
    def test_raw_examples_from_notes(self):
        # CoreWeave: 112% growth + 56% EBITDA margin = 168 score.
        self.assertEqual(metrics.rule40(112, 56), 168.0)
        # Nebius: 684% growth + 13% EBITDA margin ≈ 697 by the EBITDA formula.
        self.assertEqual(metrics.rule40(684, 13), 697.0)

    def test_dual_margin_and_gap(self):
        r = metrics.rule40_report(
            revenue_growth=684, ebitda_margin=13, fcf_margin=-450,
            capex_intensity=507, share_dilution=12,
        )
        self.assertEqual(r.regime, metrics.REGIME_NEOCLOUD)
        self.assertEqual(r.score_ebitda, 697.0)
        self.assertEqual(r.score_fcf, 234.0)                 # 684 + (-450)
        self.assertEqual(r.capital_intensity_gap, 463.0)     # 697 - 234, matches the notes
        self.assertEqual(r.capex_adjusted_score, 234.0 - 507)
        # Neocloud is judged on the capex-adjusted (burn) score, not the flattering EBITDA one.
        self.assertEqual(r.preferred_score, r.capex_adjusted_score)
        self.assertFalse(r.passes)

    def test_mature_saas_uses_fcf_and_mature_bar(self):
        r = metrics.rule40_report(revenue_growth=18, ebitda_margin=35, fcf_margin=30)
        self.assertEqual(r.regime, metrics.REGIME_TRADITIONAL)
        self.assertEqual(r.preferred_score, r.score_fcf)     # FCF-based
        self.assertEqual(r.benchmark, metrics.STAGE_BENCHMARKS["mature"])
        self.assertTrue(r.passes)                            # 48 >= 42

    def test_sector_key_overrides_benchmark(self):
        r = metrics.rule40_report(revenue_growth=25, ebitda_margin=10, fcf_margin=8, sector_key="cybersecurity")
        self.assertEqual(r.benchmark, metrics.SECTOR_BENCHMARKS["cybersecurity"])


class TestValuation(unittest.TestCase):
    def test_dcf_monotonic_in_growth(self):
        low = metrics.dcf_intrinsic_value(1_000_000, growth_rate=5, shares_outstanding=1_000_000)
        high = metrics.dcf_intrinsic_value(1_000_000, growth_rate=15, shares_outstanding=1_000_000)
        self.assertGreater(high["per_share"], low["per_share"])

    def test_dcf_rejects_terminal_ge_discount(self):
        with self.assertRaises(ValueError):
            metrics.dcf_intrinsic_value(1_000_000, growth_rate=10, discount_rate=5, terminal_growth=6)

    def test_dcf_net_debt_reduces_equity(self):
        no_debt = metrics.dcf_intrinsic_value(1_000_000, 8, shares_outstanding=1000, net_debt=0)
        with_debt = metrics.dcf_intrinsic_value(1_000_000, 8, shares_outstanding=1000, net_debt=5_000_000)
        self.assertGreater(no_debt["per_share"], with_debt["per_share"])


class TestHealth(unittest.TestCase):
    def test_altman_zones(self):
        strong = metrics.altman_z(4e5, 6e5, 3e5, 2e6, 5e5, 1.5e6, 1e6)
        self.assertEqual(strong["zone"], "safe")
        with self.assertRaises(ValueError):
            metrics.altman_z(0, 0, 0, 0, 0, 0, 0)

    def test_piotroski_counts_signals(self):
        res = metrics.piotroski_f_score({
            "positive_net_income": True, "positive_operating_cf": True, "roa_improved": True,
            "cfo_gt_net_income": True, "lower_leverage": True, "higher_current_ratio": True,
            "no_new_shares": True, "higher_gross_margin": False, "higher_asset_turnover": False,
        })
        self.assertEqual(res["f_score"], 7)
        self.assertEqual(res["strength"], "strong")


class TestEvEbitda(unittest.TestCase):
    def test_computes_with_known_net_debt(self):
        # EV = 48B market cap + 11.5B net debt = 59.5B; / 1.064B EBITDA ≈ 55.9x.
        self.assertEqual(metrics.ev_ebitda(48e9, 11.5e9, 1.064e9), 55.9)

    def test_none_when_net_debt_unknown(self):
        # Fail closed — do not impute 0 and fabricate a concrete multiple.
        self.assertIsNone(metrics.ev_ebitda(48e9, None, 1.064e9))

    def test_none_when_ebitda_not_positive(self):
        self.assertIsNone(metrics.ev_ebitda(48e9, 1e9, 0))
        self.assertIsNone(metrics.ev_ebitda(48e9, 1e9, -5e8))


class TestGuards(unittest.TestCase):
    def test_safe_margin_divzero_and_none(self):
        self.assertIsNone(metrics.safe_margin(10, 0))
        self.assertIsNone(metrics.safe_margin(None, 10))
        self.assertEqual(metrics.safe_margin(50, 200), 25.0)

    def test_yoy_growth_guards(self):
        self.assertIsNone(metrics.yoy_growth(10, 0))
        self.assertIsNone(metrics.yoy_growth(10, -5))
        self.assertEqual(metrics.yoy_growth(150, 100), 50.0)


if __name__ == "__main__":
    unittest.main()
