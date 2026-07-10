"""export — render a verb's output to a shareable file (Markdown / JSON / CSV).

    python scripts/export.py <TICKER> [--verb=valuation] [--format=md] [--out=PATH] [--fixture]

Reuses the same build functions as the interactive verbs, so an exported report
is byte-for-byte the numbers the skill would have shown. CSV flattens the
Metric/Value/Read table (the table verbs only); Markdown wraps the text report;
JSON is the engine's structured `--json` payload. Writes to --out or stdout.

READ-ONLY: writes a local report file; never touches an account or the network
beyond the same fetch the other verbs do.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # installed as the `finance_skills` package…
    from finance_skills import analyze, health, redflags, valuation
    from finance_skills.data import Fundamentals, get_fundamentals_or_fixture, load_fixture
except ImportError:  # …or run directly via `python3 scripts/export.py` (skill path)
    import analyze
    import health
    import redflags
    import valuation
    from data import Fundamentals, get_fundamentals_or_fixture, load_fixture

# verb -> (text_builder, json_builder). Both take (Fundamentals, as_json=bool).
BUILDERS = {
    "analyze":   analyze.build_report,
    "valuation": valuation.build_valuation,
    "health":    health.build_health,
    "redflags":  redflags.build_redflags,
}


def _rows_from_json(payload: dict) -> list[tuple[str, str, str]]:
    """Best-effort (metric, value, read) rows from a verb's JSON, for CSV."""
    rows = payload.get("rows", [])
    out = []
    for row in rows:
        metric = row.get("metric", "")
        value = row.get("value")
        read = row.get("read") or row.get("kpi") or ""
        out.append((metric, "" if value is None else str(value), read))
    return out


def export(f: Fundamentals, verb: str, fmt: str) -> str:
    build = BUILDERS[verb]
    if fmt == "json":
        return json.dumps(build(f, as_json=True), indent=2)
    if fmt == "md":
        text = build(f, as_json=False)
        title = f"# {f.name or f.ticker} ({f.ticker}) — {verb}"
        return f"{title}\n\n```\n{text}\n```\n"
    if fmt == "csv":
        payload = build(f, as_json=True)
        rows = _rows_from_json(payload)
        if not rows:
            raise ValueError(f"{verb} has no tabular rows to export as CSV; try --format=md or json")
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ticker", "metric", "value", "read"])
        for metric, value, read in rows:
            w.writerow([f.ticker, metric, value, read])
        return buf.getvalue()
    raise ValueError(f"unknown format {fmt!r} — use md, json, or csv")


def _flag(flags: set[str], name: str, default: str) -> str:
    for fl in flags:
        if fl.startswith(f"--{name}="):
            return fl.split("=", 1)[1]
    return default


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print("usage: python scripts/export.py <TICKER> [--verb=valuation] [--format=md] [--out=PATH] [--fixture]\n"
              f"       verbs: {', '.join(BUILDERS)}   formats: md, json, csv", file=sys.stderr)
        return 2

    ticker = args[0].upper()
    verb = _flag(flags, "verb", "valuation")
    fmt = _flag(flags, "format", "md")
    out = _flag(flags, "out", "")
    if verb not in BUILDERS:
        print(f"unknown verb {verb!r}. Exportable: {', '.join(BUILDERS)}", file=sys.stderr)
        return 2

    if "--fixture" in flags:
        f = load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    else:
        f = get_fundamentals_or_fixture(ticker)
    if not f.available:
        print(f"No data for {ticker}: {f.error}", file=sys.stderr)
        return 1

    try:
        rendered = export(f, verb, fmt)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if out:
        Path(out).write_text(rendered, encoding="utf-8")
        print(f"Wrote {verb} report for {ticker} → {out} ({fmt}, {len(rendered)} bytes)")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
