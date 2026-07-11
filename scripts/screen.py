"""screen — filter a set of tickers by a rule, over the shared engine.

    python scripts/screen.py "rule40 > 0 and fcf_margin > -100" CRWV NBIS [--fixture|--json]

The rule is a safe, tiny expression language — NOT Python `eval`. It is a set of
`field op value` clauses joined by `and` / `or`. Supported fields are named
accessors over `analyze.build_report` (so a screen can never reference a metric
the engine doesn't actually compute), and operators are the six comparisons.
This keeps screening deterministic and injection-free.

A ticker whose field is unavailable (None) fails the clause rather than being
silently skipped — a screen that "passes" on missing data would be misleading.

Universe: the tickers you pass. With no tickers, screens the built-in fixtures
(offline demo). There is no bundled market universe — live screening across
thousands of names needs a data source the sandbox doesn't have.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze, rank
    from finance_skills.cli import parse_argv
    from finance_skills.data import list_fixtures, load_for_cli
    from finance_skills.format import DISCLAIMER, markdown_table, mult, pct
else:
    import analyze
    import rank
    from cli import parse_argv
    from data import list_fixtures, load_for_cli
    from format import DISCLAIMER, markdown_table, mult, pct

# Field name -> how to read it out of the engine report. Add here to expose more.
FIELDS: dict[str, Callable[[dict], Any]] = {
    "rule40":       lambda r: (r.get("rule40") or {}).get("preferred_score"),
    "growth":       lambda r: r["derived"].get("revenue_growth_pct"),
    "gross_margin": lambda r: r["derived"].get("gross_margin_pct"),
    "ebitda_margin": lambda r: r["derived"].get("ebitda_margin_pct"),
    "fcf_margin":   lambda r: r["derived"].get("fcf_margin_pct"),
    "capex_intensity": lambda r: r["derived"].get("capex_intensity_pct"),
    "dilution":     lambda r: r["derived"].get("share_dilution_pct"),
    "ev_sales":     lambda r: r["derived"].get("ev_sales"),
    "ev_ebitda":    lambda r: r["derived"].get("ev_ebitda"),
    "net_debt":     lambda r: r["derived"].get("net_debt"),
    "market_cap":   lambda r: r.get("market_cap"),
    "price":        lambda r: r.get("price"),
}

_OPS = {
    ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b, "<": lambda a, b: a < b,
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
}

# One clause: field, operator, number. e.g. "fcf_margin >= -50". The field may
# contain digits (e.g. rule40), but must start with a letter.
_CLAUSE_RE = re.compile(r"^\s*([a-z][a-z_0-9]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")


class RuleError(ValueError):
    """A malformed screen rule (bad field, operator, or structure)."""


def _parse_clause(clause: str) -> tuple[str, str, float]:
    """Validate one clause and return (field, op, number), or raise RuleError."""
    m = _CLAUSE_RE.match(clause)
    if not m:
        raise RuleError(f"can't parse clause: {clause!r} — expected `field op number`")
    field, op, num = m.group(1), m.group(2), float(m.group(3))
    if field not in FIELDS:
        raise RuleError(f"unknown field {field!r}. Known: {', '.join(sorted(FIELDS))}")
    return field, op, num


def _eval_clause(clause: str, report: dict) -> bool:
    field, op, num = _parse_clause(clause)
    value = FIELDS[field](report)
    if value is None:
        return False  # missing data fails the clause, never silently passes
    return _OPS[op](value, num)


def evaluate(rule: str, report: dict) -> bool:
    """Evaluate a rule (clauses joined by `and`/`or`) against one engine report.

    `and` binds tighter than `or` (standard precedence): the rule is a disjunction
    of conjunctions. No parentheses — deliberately tiny.

    Fail-closed: the WHOLE rule is parsed and validated before any clause is
    evaluated, so a malformed or injection-shaped clause anywhere raises RuleError
    rather than being skipped by short-circuiting.
    """
    if not rule.strip():
        raise RuleError("empty rule")
    or_groups = [re.split(r"\band\b", g) for g in re.split(r"\bor\b", rule)]
    for group in or_groups:                    # validate everything first
        for clause in group:
            _parse_clause(clause)
    for group in or_groups:                    # then evaluate, short-circuit ok
        if all(_eval_clause(c, report) for c in group):
            return True
    return False


# Extra columns always shown for multi-ticker screens (comparison visibility).
_COMPARE_COLS = ("growth", "fcf_margin", "ev_sales", "rule40")
# higher_is_better for leader highlighting on value columns
_COL_HIB: dict[str, bool] = {
    "rule40": True,
    "growth": True,
    "gross_margin": True,
    "ebitda_margin": True,
    "fcf_margin": True,
    "capex_intensity": False,
    "dilution": False,
    "ev_sales": False,
    "ev_ebitda": False,
    "net_debt": False,
    "market_cap": True,
    "price": True,
}


def screen(rule: str, tickers: list[str], use_fixture: bool = False) -> dict:
    results: list[dict[str, Any]] = []
    reports: list[dict] = []
    rule_fields = _fields_in(rule)
    # Union: rule fields + comparison columns (unique, stable order)
    display_fields: list[str] = list(rule_fields)
    for c in _COMPARE_COLS:
        if c not in display_fields:
            display_fields.append(c)

    for ticker in tickers:
        f = load_for_cli(ticker, use_fixture=use_fixture)
        if not f.available:
            results.append({
                "ticker": ticker.upper(),
                "passes": None,
                "note": "no data",
                "values": {},
            })
            continue
        report = analyze.build_report(f)
        reports.append(report)
        results.append({
            "ticker": report["ticker"],
            "passes": evaluate(rule, report),
            "values": {k: FIELDS[k](report) for k in display_fields},
        })
    matches = [r for r in results if r.get("passes")]
    match_reports = [
        rep for rep in reports
        if any(m["ticker"] == rep["ticker"] for m in matches)
    ]
    ranking = rank.rank_reports(reports)
    ranking_matches = (
        rank.rank_reports(match_reports) if match_reports else rank.rank_reports([])
    )
    md = _markdown_screen_table(results, display_fields)
    return {
        "rule": rule,
        "matches": matches,
        "results": results,
        "display_fields": display_fields,
        "markdown_table": md,
        "ranking": ranking,
        "ranking_matches": ranking_matches,
        "ranking_lines": rank.render_ranking(ranking),
        "ranking_matches_lines": rank.render_ranking(ranking_matches),
    }


def _fields_in(rule: str) -> list[str]:
    return [f for f in FIELDS if re.search(rf"\b{f}\b", rule)]


def _fmt_field(field: str, v: Any) -> str:
    if v is None:
        return "n/a"
    if field in (
        "growth", "gross_margin", "ebitda_margin", "fcf_margin",
        "capex_intensity", "dilution",
    ):
        return pct(v)
    if field in ("ev_sales", "ev_ebitda"):
        return mult(v)
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _leaders_by_field(
    results: list[dict[str, Any]],
    fields: list[str],
) -> dict[str, str | None]:
    """Per-field best ticker (for 🏆), among rows with data."""
    leaders: dict[str, str | None] = {}
    scored_rows = [r for r in results if r.get("passes") is not None]
    for field in fields:
        hib = _COL_HIB.get(field)
        if hib is None:
            leaders[field] = None
            continue
        scored: list[tuple[float, str]] = []
        for r in scored_rows:
            v = (r.get("values") or {}).get(field)
            if v is None:
                continue
            try:
                scored.append((float(v), r["ticker"]))
            except (TypeError, ValueError):
                continue
        if len(scored) < 2:
            leaders[field] = None
            continue
        vals = [v for v, _ in scored]
        if max(vals) == min(vals):
            leaders[field] = None
            continue
        scored.sort(key=lambda x: x[0], reverse=hib)
        leaders[field] = scored[0][1]
    return leaders


def _markdown_screen_table(
    results: list[dict[str, Any]],
    fields: list[str],
) -> str:
    leaders = _leaders_by_field(results, fields)
    headers = ["Ticker", "Result", *list(fields)]
    rows: list[list[str]] = []
    for r in results:
        t = r["ticker"]
        if r.get("passes") is None:
            rows.append([f"**{t}**", "⚪ no data", *["n/a"] * len(fields)])
            continue
        if r["passes"]:
            result_cell = "✅ **PASS**"
        else:
            result_cell = "❌ FAIL"
        cells = [f"**{t}**", result_cell]
        for f in fields:
            raw = (r.get("values") or {}).get(f)
            disp = _fmt_field(f, raw)
            if leaders.get(f) == t and disp != "n/a":
                disp = f"🏆 **{disp}**"
            cells.append(disp)
        rows.append(cells)
    return markdown_table(headers, rows, aligns=["left", "center"] + ["right"] * len(fields))


def _render(res: dict) -> str:
    passed = res["matches"]
    fields = res.get("display_fields") or _fields_in(res["rule"])
    md = res.get("markdown_table") or _markdown_screen_table(res["results"], fields)
    n_pass = len(passed)
    n_tot = len(res["results"])
    pass_list = ", ".join(f"**{r['ticker']}**" for r in passed) or "—"

    out = [
        f"═══ screen: `{res['rule']}` ═══",
        "",
        f"**{n_pass}/{n_tot} pass:** {pass_list}",
        "",
        "_Legend: ✅ PASS · ❌ FAIL · 🏆 best on that column_",
        "",
        md,
    ]
    if res.get("ranking_lines") or res.get("ranking"):
        lines = res.get("ranking_lines") or rank.render_ranking(res["ranking"])
        out += ["", *lines]
    if res.get("ranking_matches") and res["ranking_matches"].get("n"):
        out += ["", "**Among matches only:**"]
        mlines = res.get("ranking_matches_lines") or rank.render_ranking(res["ranking_matches"])
        for line in mlines:
            out.append("  " + line if not line.startswith("  ") else line)
    out += ["", DISCLAIMER]
    return "\n".join(out)


def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:g}"


def main(argv: list[str]) -> int:
    args, flags = parse_argv(argv)
    if not args:
        print('usage: python scripts/screen.py "<rule>" [TICKER ...] [--fixture] [--json]\n'
              f"       fields: {', '.join(sorted(FIELDS))}", file=sys.stderr)
        return 2
    rule = args[0]
    tickers = [a.upper() for a in args[1:]] or list_fixtures()
    use_fixture = "--fixture" in flags or not args[1:]  # fixtures-only universe implies fixture mode
    try:
        res = screen(rule, tickers, use_fixture=use_fixture)
    except RuleError as exc:
        print(f"bad rule: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if "--json" in flags else _render(res))
    return 0 if res["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
