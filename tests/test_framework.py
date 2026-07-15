import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ask
import framework
from data import load_fixture


def _exit_code(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return framework.main(argv)


class TestFramework(unittest.TestCase):
    def test_resolve_aliases(self):
        self.assertEqual(framework.resolve_framework("SaaS"), "saas")
        self.assertEqual(framework.resolve_framework("software"), "saas")
        self.assertEqual(framework.resolve_framework("gpu"), "neocloud")
        self.assertIsNone(framework.resolve_framework("nonsense"))

    def test_saas_computes_real_metrics_and_flags_kpis(self):
        r = framework.build_framework("saas", load_fixture("CRWV"), as_json=True)
        rows = {row["metric"]: row for row in r["rows"]}
        # Computable from the engine — must have a value, no KPI note.
        self.assertIsNotNone(rows["Gross margin"]["value"])
        self.assertEqual(rows["Gross margin"]["value"], "70.0%")
        self.assertIsNone(rows["Gross margin"]["kpi"])
        # Disclosed KPIs — must be flagged, never fabricated into a number.
        for kpi_metric in ("Magic Number", "CAC payback", "Net revenue retention (NRR)"):
            self.assertIsNone(rows[kpi_metric]["value"])
            self.assertIsNotNone(rows[kpi_metric]["kpi"])

    def test_json_has_canonical_engine_report(self):
        r = framework.build_framework("neocloud", load_fixture("CRWV"), as_json=True)
        self.assertIn("engine_report", r)
        self.assertEqual(r["engine_report"]["source"]["data_state"], "fixture")

    def test_ask_framework_discloses_fixture(self):
        out = ask.run_ask("neocloud framework for CRWV", use_fixture=True)
        self.assertTrue(out["has_engine_report"])
        self.assertIn("Sample/fixture", out["answer_draft"])

    def test_text_render_labels_kpis_and_sample_data(self):
        text = framework.build_framework("saas", load_fixture("CRWV"), as_json=False)
        self.assertIn("needs disclosed KPI", text)
        self.assertIn("SAMPLE DATA", text)
        self.assertIn("Not investment advice", text)

    def test_every_framework_renders_for_a_fixture(self):
        for name in framework.FRAMEWORKS:
            text = framework.build_framework(name, load_fixture("NBIS"), as_json=False)
            self.assertIn("framework", text)

    def test_exit_code_signals_availability(self):
        self.assertEqual(_exit_code(["saas", "CRWV", "--fixture"]), 0)   # fixture exists
        self.assertEqual(_exit_code(["saas", "ZZZZ", "--fixture"]), 1)   # no fixture → unavailable
        self.assertEqual(_exit_code(["bogus", "CRWV"]), 2)              # unknown framework


if __name__ == "__main__":
    unittest.main()
