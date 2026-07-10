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

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # installed as the `finance_skills` package…
    from finance_skills import analyze
    from finance_skills.data import _FIXTURES, get_fundamentals_or_fixture, load_fixture
except ImportError:  # …or run directly via `python3 scripts/screen.py` (skill path)
    import analyze
    from data import _FIXTURES, get_fundamentals_or_fixture, load_fixture

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
    """Validate one clause and return (field, op, number), or raise RuleError.

    Pure validation — no report needed. Every clause in a rule is parsed up front
    (see `evaluate`) so a valid-looking prefix can never mask a malformed or
    hostile clause behind short-circuit evaluation.
    """
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


def screen(rule: str, tickers: list[str], use_fixture: bool = False) -> dict:
    results: list[dict[str, Any]] = []
    for ticker in tickers:
        f = load_fixture(ticker) if use_fixture else get_fundamentals_or_fixture(ticker)
        if f is None or not getattr(f, "available", False):
            results.append({"ticker": ticker.upper(), "passes": None, "note": "no data"})
            continue
        report = analyze.build_report(f, as_json=True)
        results.append({"ticker": report["ticker"], "passes": evaluate(rule, report),
                        "values": {k: FIELDS[k](report) for k in _fields_in(rule)}})
    return {"rule": rule, "matches": [r for r in results if r.get("passes")], "results": results}


def _fields_in(rule: str) -> list[str]:
    return [f for f in FIELDS if re.search(rf"\b{f}\b", rule)]


def _render(res: dict) -> str:
    passed = res["matches"]
    out = [f"═══ screen: {res['rule']} ═══", ""]
    fields = _fields_in(res["rule"])
    for r in res["results"]:
        if r["passes"] is None:
            out.append(f"  ·  {r['ticker']:6s} no data")
            continue
        mark = "✓" if r["passes"] else "✗"
        vals = "  ".join(f"{k}={_fmt(r['values'].get(k))}" for k in fields)
        out.append(f"  {mark}  {r['ticker']:6s} {vals}")
    out += ["", f"{len(passed)}/{len(res['results'])} pass: {', '.join(r['ticker'] for r in passed) or '—'}"]
    out += [analyze.DISCLAIMER]
    return "\n".join(out)


def _fmt(v) -> str:
    return "n/a" if v is None else f"{v:g}"


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if not args:
        print('usage: python scripts/screen.py "<rule>" [TICKER ...] [--fixture] [--json]\n'
              f"       fields: {', '.join(sorted(FIELDS))}", file=sys.stderr)
        return 2
    rule = args[0]
    tickers = [a.upper() for a in args[1:]] or sorted(_FIXTURES)
    use_fixture = "--fixture" in flags or not args[1:]  # fixtures-only universe implies fixture mode
    try:
        res = screen(rule, tickers, use_fixture=use_fixture)
    except RuleError as exc:
        print(f"bad rule: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if "--json" in flags else _render(res))
    return 0 if res["matches"] else 1  # non-zero when nothing matched, for scripting


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
