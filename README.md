# finance-skills

Analyst-style equity research as an agent skill — driven by **real fundamentals**,
not narrated numbers. Ask about any public ticker in plain English and get a
report built from a fetch → compute pipeline.

> **Read-only. Not investment advice.** It only reads public market data, never
> places trades, and every figure should be verified against primary filings.

```
/finance-skills analyze Do you think NBIS is a buy?
/finance-skills is NVDA overvalued?
/finance-skills compare AMD and NVDA
```

## What makes it different

Most "Rule of 40" tools compute one flat number. This one **classifies the
company's growth/capital regime first**, then picks the right formula and peer
benchmark — the mistake experienced analysts flag most often on names like
CoreWeave (CRWV) and Nebius (NBIS), whose GPU capex breaks the classic formula.
See [`references/rule40.md`](references/rule40.md).

## Install as a skill (`/finance-skills`)

The whole repo installs as one skill for Claude Code, Antigravity, or a
Codex-compatible tool. Easiest — ask your agent:

```text
Hey Claude, install this skill https://github.com/notEhEnG/finance-skills
```

Or one command:

```bash
curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/main/install.sh | bash -s -- claude
# or: ... | bash -s -- antigravity   (or codex, or all)
```

Or manually copy the repo into the tool's skill dir (`scripts/` must sit next to
`SKILL.md` so the engine can run):

| Tool | Install path | Invoke |
|---|---|---|
| Claude Code | `.claude/skills/finance-skills/SKILL.md` | `/finance-skills analyze Do you think NBIS is a buy?` |
| Antigravity IDE | `.antigravity/skills/finance-skills/SKILL.md` | `/finance-skills is NVDA a buy?` or assign to an agent |
| Codex-compatible | `<codex-skill-dir>/finance-skills/SKILL.md` | `/finance-skills ...` |

Then, if needed: `pip install yfinance`.

## How invocation works

`/finance-skills [verb] <plain-English question>`. The skill (1) extracts the
ticker (mapping company names, e.g. Nebius → NBIS), (2) determines intent (an
explicit verb or inferred from the question), (3) runs the engine and answers
the actual question with cited numbers. So all of these are equivalent:

```
/finance-skills is NBIS a buy?
/finance-skills analyze Do you think NBIS is a buy?
/finance-skills analyze NBIS
```

## Architecture

```
finance-skills/
├── SKILL.md                # skill entry: triggers, safety, invocation contract
├── install.sh              # install as an agent skill (claude/antigravity/codex)
├── scripts/
│   ├── data.py             # yfinance fetch + normalise + 6h cache + graceful fallback
│   ├── metrics.py          # PURE engine: segment-aware Rule 40, DCF, Altman Z, Piotroski
│   ├── analyze.py          # orchestrator: fetch → compute → report (flagship `analyze`)
│   └── router.py           # ticker extraction + alias/fuzzy resolver + grouped help (pure)
├── references/
│   ├── rule40.md           # segment-aware Rule of 40 methodology + benchmarks
│   └── ai-cloud.md         # AI-cloud/neocloud sector framework (capex, backlog/RPO)
├── tests/                  # offline unit tests (pure math + orchestrator + router)
└── requirements.txt        # yfinance
```

The **engine is one source of truth**: `metrics.py` is pure and offline-testable;
`data.py` is the only module that touches the network; `analyze.py` composes them.
Every specialised command (valuation, growth, risk, rule40, ai-cloud, compare…) is
a *view* over `analyze`, so numbers never diverge between commands.

## CLI usage (also drives the skill)

```bash
pip install -r requirements.txt

python3 scripts/analyze.py NVDA            # full live report
python3 scripts/analyze.py NVDA --json      # structured output
python3 scripts/analyze.py CRWV --fixture   # offline sample (no network)
python3 scripts/router.py tickers "is NBIS a buy?"   # -> NBIS
python3 scripts/router.py help              # grouped help
```

## Platform note

Live fetching uses `yfinance` (network) → works on **Claude Code** and locally,
**not** on the Claude.ai sandbox. Without network, use `--fixture` (CRWV, NBIS
samples, clearly labelled non-live) or the skill will say live data is unavailable.

## Development

```bash
python3 -m pytest tests/ -q     # 32 offline tests (no network needed)
```

- `tests/test_metrics.py` — regime classification, dual-margin/capex-adjusted
  Rule 40 (locks the CoreWeave/Nebius examples), DCF guards, Altman Z, Piotroski.
- `tests/test_analyze.py` — orchestrator on fixtures + graceful no-data path.
- `tests/test_router.py` — ticker extraction, alias/fuzzy resolution, grouped help.

## Status & roadmap

The **vertical slice**: the real engine proven end-to-end on live data plus
offline fixtures, installable as a cross-tool skill. Next, layered over the same
engine: more sector references (`semiconductor.md`, `banking.md`, `reit.md`),
`compare`/`screen`/`rank` views, trend arrows, and backlog/RPO ingestion.
