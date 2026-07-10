"""watchlist — save a set of tickers and run any exportable verb across all of them.

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

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

if __package__:
    from finance_skills import analyze, rank
    from finance_skills import compare as compare_mod
    from finance_skills.cli import flag_value, parse_argv
    from finance_skills.data import CACHE_DIR, load_for_cli
    from finance_skills.router import WATCHLIST_VERBS, load_builder
else:
    import analyze
    import compare as compare_mod
    import rank
    from cli import flag_value, parse_argv
    from data import CACHE_DIR, load_for_cli
    from router import WATCHLIST_VERBS, load_builder

STORE = CACHE_DIR / "watchlists.json"


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


def main(argv: list[str]) -> int:
    args, flags = parse_argv(argv)
    name = flag_value(flags, "name", "default")
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

        if verb in ("compare", "rank"):
            reports = []
            for t in tickers:
                rep = analyze.build_report(load_for_cli(t, use_fixture=use_fixture))
                if rep.get("available", True):
                    reports.append(rep)
            if verb == "rank":
                if not reports:
                    print("No tickers with data to rank.", file=sys.stderr)
                    return 1
                ranking = rank.rank_reports(reports)
                print("\n".join(rank.render_ranking(ranking)))
                print(f"\n[{name}] {', '.join(r['ticker'] for r in reports)}")
                return 0
            if len(reports) < 2:
                print("Need at least two tickers with data to compare.", file=sys.stderr)
                return 1
            print(compare_mod.build_compare(reports, as_json=False))
            return 0

        if verb not in WATCHLIST_VERBS:
            print(
                f"unknown verb {verb!r}. Try: {', '.join(sorted(WATCHLIST_VERBS))}, compare, rank",
                file=sys.stderr,
            )
            return 2
        build = load_builder(verb)
        reports = []
        for t in tickers:
            f = load_for_cli(t, use_fixture=use_fixture)
            print(build(f, False))
            print()
            if f.available:
                reports.append(analyze.build_report(f))
        if len(reports) >= 2:
            print("\n".join(rank.render_ranking(rank.rank_reports(reports))))
        return 0

    print(f"unknown command {cmd!r}. Use add / remove / list / clear / run.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
