# financial-skills

Analyst-style equity research as a Claude skill — driven by **real fundamentals**,
not narrated numbers. Ask about any public ticker in plain English (or with a few
memorable verbs) and get a report built from a fetch → compute pipeline.

> **Read-only. Not investment advice.** It only reads public market data, never
> places trades, and every figure should be verified against primary filings.

## What makes it different

Most "Rule of 40" tools compute one flat number. This one **classifies the
company's growth/capital regime first**, then picks the right formula and peer
benchmark — the mistake experienced analysts flag most often on names like
CoreWeave (CRWV) and Nebius (NBIS), whose GPU capex breaks the classic formula.
See [`references/rule40.md`](references/rule40.md).

## Architecture (vertical slice)

```
financial-skills/
├── SKILL.md                # skill entry: triggers, safety, routing (NL + 5 verbs)
├── scripts/
│   ├── data.py             # yfinance fetch + normalise + 6h cache + graceful fallback
│   ├── metrics.py          # PURE engine: segment-aware Rule 40, DCF, Altman Z, Piotroski
│   ├── analyze.py          # orchestrator: fetch → compute → report (flagship `analyze`)
│   └── router.py           # alias/fuzzy command resolver + grouped help (pure)
├── references/
│   ├── rule40.md           # segment-aware Rule of 40 methodology + benchmarks
│   └── ai-cloud.md         # AI-cloud/neocloud sector framework (capex, backlog/RPO)
├── tests/                  # offline unit tests (pure math + orchestrator on fixtures)
└── requirements.txt        # yfinance
```

The **engine is one source of truth**: `metrics.py` is pure and offline-testable;
`data.py` is the only module that touches the network; `analyze.py` composes them.
Every specialised command (valuation, growth, risk, rule40, ai-cloud, compare…) is
a *view* over `analyze`, so numbers never diverge between commands.

## Usage

```bash
pip install -r requirements.txt

python3 scripts/analyze.py NVDA            # full live report
python3 scripts/analyze.py NVDA --json      # structured output
python3 scripts/analyze.py CRWV --fixture   # offline sample (no network)
```

As a skill, users can just ask: *"is NVDA a good buy?"*, *"why is AMD's margin
dropping?"*, *"rule of 40 for CRM"*, *"how does AMD compare to NVDA?"* — the
`description` field in `SKILL.md` auto-activates it.

## Platform note

Live fetching uses `yfinance` (network) → works on **Claude Code** and locally,
**not** on the Claude.ai sandbox. Without network, use `--fixture` (CRWV, NBIS
samples, clearly labelled non-live) or the skill will say live data is unavailable.

## Development

```bash
python3 -m pytest tests/ -q     # 27 offline tests (no network needed)
```

- `tests/test_metrics.py` — regime classification, dual-margin/capex-adjusted
  Rule 40 (locks the CoreWeave/Nebius examples), DCF guards, Altman Z, Piotroski.
- `tests/test_analyze.py` — orchestrator on fixtures + graceful no-data path.
- `tests/test_router.py` — alias/fuzzy command resolution + grouped help taxonomy.

## Status & roadmap

This is the **vertical slice**: the real engine proven end-to-end on live data
plus offline fixtures. Next, layered over the same engine:

- More sector references (`semiconductor.md`, `banking.md`, `reit.md`, `insurance.md`).
- `compare`, `screen`, `rank` views; trend arrows (multi-quarter Rule 40).
- Backlog/RPO ingestion for neoclouds from filings.
- A `SKILL.md` lint check (description length / trigger coverage) before publishing.
