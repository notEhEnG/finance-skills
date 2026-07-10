"""watchlist — save a set of tickers and run any verb across all of them.

    python scripts/watchlist.py add NVDA AMD NBIS
    python scripts/watchlist.py list
    python scripts/watchlist.py remove AMD
    python scripts/watchlist.py run valuation [--fixture]
    python scripts/watchlist.py run compare            # side-by-side of the whole list

State is a plain JSON file in .cache/ (the same 6h-cache dir the data layer uses),
so it survives between sessions but stays local. `--name=<list>` keeps more than
one watchlist (default: "default"), e.g. a `--name=neoclouds` bucket.

READ-ONLY on the market: only ever reads public data; the sole thing it writes is
your local ticker list.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # installed as the `finance_skills` package…
    from finance_skills import analyze, health, redflags, valuation
    from finance_skills import compare as compare_mod
    from finance_skills.data import CACHE_DIR, Fundamentals, get_fundamentals_or_fixture, load_fixture
except ImportError:  # …or run directly via `python3 scripts/watchlist.py` (skill path)
    import analyze
    import compare as compare_mod
    import health
    import redflags
    import valuation
    from data import CACHE_DIR, Fundamentals, get_fundamentals_or_fixture, load_fixture

STORE = CACHE_DIR / "watchlists.json"

# verb -> single-ticker build function (text). `compare` is handled specially.
VERBS = {
    "analyze":   analyze.build_report,
    "valuation": valuation.build_valuation,
    "health":    health.build_health,
    "redflags":  redflags.build_redflags,
}


def _load() -> dict[str, list[str]]:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict[str, list[str]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _get(data: dict, name: str) -> list[str]:
    return data.get(name, [])


def _fetch(ticker: str, use_fixture: bool) -> Fundamentals:
    if use_fixture:
        return load_fixture(ticker) or Fundamentals(ticker=ticker, available=False, error="no fixture for this ticker")
    return get_fundamentals_or_fixture(ticker)


def _flag_value(flags: set[str], name: str, default: str) -> str:
    for fl in flags:
        if fl.startswith(f"--{name}="):
            return fl.split("=", 1)[1]
    return default


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    name = _flag_value(flags, "name", "default")
    use_fixture = "--fixture" in flags

    if not args:
        print("usage: python scripts/watchlist.py <add|remove|list|clear|run> ... [--name=default] [--fixture]",
              file=sys.stderr)
        return 2

    cmd, rest = args[0].lower(), [a.upper() for a in args[1:]]
    data = _load()

    if cmd == "add":
        if not rest:
            print("add what? e.g. watchlist.py add NVDA AMD", file=sys.stderr)
            return 2
        lst = _get(data, name)
        for t in rest:
            if t not in lst:
                lst.append(t)
        data[name] = lst
        _save(data)
        print(f"[{name}] {', '.join(lst)}")
        return 0

    if cmd == "remove":
        lst = [t for t in _get(data, name) if t not in rest]
        data[name] = lst
        _save(data)
        print(f"[{name}] {', '.join(lst) or '(empty)'}")
        return 0

    if cmd == "clear":
        data.pop(name, None)
        _save(data)
        print(f"[{name}] cleared")
        return 0

    if cmd == "list":
        if not data:
            print("(no watchlists yet — add one: watchlist.py add NVDA AMD)")
            return 0
        for key, tickers in data.items():
            print(f"[{key}] {', '.join(tickers) or '(empty)'}")
        return 0

    if cmd == "run":
        verb = (rest[0].lower() if rest else "valuation")
        tickers = _get(data, name)
        if not tickers:
            print(f"[{name}] is empty — add tickers first.", file=sys.stderr)
            return 1

        if verb == "compare":
            reports = []
            for t in tickers:
                rep = analyze.build_report(_fetch(t, use_fixture), as_json=True)
                if isinstance(rep, dict) and rep.get("available", True):
                    reports.append(rep)
            if len(reports) < 2:
                print("Need at least two tickers with data to compare.", file=sys.stderr)
                return 1
            print(compare_mod.build_compare(reports, as_json=False))
            return 0

        build = VERBS.get(verb)
        if build is None:
            print(f"unknown verb {verb!r}. Try: {', '.join(VERBS)}, compare", file=sys.stderr)
            return 2
        for t in tickers:
            print(build(_fetch(t, use_fixture), as_json=False))
            print()
        return 0

    print(f"unknown command {cmd!r}. Use add / remove / list / clear / run.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
