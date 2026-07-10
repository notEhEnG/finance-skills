import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import export
from data import load_fixture


class TestExport(unittest.TestCase):
    def test_json_is_parseable(self):
        import json
        out = export.export(load_fixture("NBIS"), "valuation", "json")
        self.assertEqual(json.loads(out)["ticker"], "NBIS")

    def test_csv_has_header_and_rows(self):
        out = export.export(load_fixture("NBIS"), "valuation", "csv")
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], "ticker,metric,value,read")
        self.assertTrue(any(line.startswith("NBIS,") for line in lines[1:]))

    def test_markdown_wraps_report(self):
        out = export.export(load_fixture("CRWV"), "analyze", "md")
        self.assertTrue(out.startswith("# "))
        self.assertIn("```", out)

    def test_csv_rejects_non_tabular_verb(self):
        # analyze has no metric/value/read rows -> CSV must error, not emit junk.
        with self.assertRaises(ValueError):
            export.export(load_fixture("CRWV"), "analyze", "csv")

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            export.export(load_fixture("CRWV"), "valuation", "pdf")

    def test_writes_out_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "r.md"
            rc = export.main(["NBIS", "--verb=health", "--format=md", f"--out={path}", "--fixture"])
            self.assertEqual(rc, 0)
            self.assertTrue(path.read_text().startswith("# "))


if __name__ == "__main__":
    unittest.main()
