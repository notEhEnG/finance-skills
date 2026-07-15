"""export — render a verb's output to a shareable file (Markdown / JSON / CSV).

    python scripts/export.py <TICKER> [--verb=valuation] [--format=md] [--out=PATH] [--fixture]

Reuses the same build functions as the interactive verbs (via the shared verb
registry), so an exported report is the numbers the skill would have shown.
CSV flattens the Metric/Value/Read table (the table verbs only); Markdown wraps
the text report; JSON is the engine's structured payload. Writes to --out or stdout.

READ-ONLY: writes a local report file; never touches an account or the network
beyond the same fetch the other verbs do.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills.cli import flag_value, parse_argv
    from finance_skills.data import load_for_cli
    from finance_skills.router import EXPORTABLE, load_builder
else:
    from cli import flag_value, parse_argv
    from data import load_for_cli
    from router import EXPORTABLE, load_builder


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


def export(f, verb: str, fmt: str) -> str:
    build = load_builder(verb)
    if fmt == "json":
        return json.dumps(build(f, True), indent=2)
    if fmt == "md":
        text = build(f, False)
        title = f"# {f.name or f.ticker} ({f.ticker}) — {verb}"
        return f"{title}\n\n```\n{text}\n```\n"
    if fmt == "csv":
        payload = build(f, True)
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


def main(argv: list[str]) -> int:
    args, flags = parse_argv(argv)
    if not args:
        print("usage: python scripts/export.py <TICKER> [--verb=valuation] [--format=md] [--out=PATH] [--fixture]\n"
              f"       verbs: {', '.join(sorted(EXPORTABLE))}   formats: md, json, csv", file=sys.stderr)
        return 2

    ticker = args[0]
    verb = flag_value(flags, "verb", "valuation")
    fmt = flag_value(flags, "format", "md")
    out = flag_value(flags, "out", "")
    if verb not in EXPORTABLE:
        print(f"unknown verb {verb!r}. Exportable: {', '.join(sorted(EXPORTABLE))}", file=sys.stderr)
        return 2

    f = load_for_cli(ticker, use_fixture="--fixture" in flags)
    if not f.available:
        print(f"No data for {f.ticker}: {f.error}", file=sys.stderr)
        return 1

    try:
        rendered = export(f, verb, fmt)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if out:
        path = Path(out)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        except FileExistsError:
            print(
                f"Refusing to overwrite existing file: {path}. Choose a new --out path.",
                file=sys.stderr,
            )
            return 2
        print(f"Wrote {verb} report for {f.ticker} → {out} ({fmt}, {len(rendered)} bytes)")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
