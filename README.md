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

## Slash commands

The default is **plain English** (Layer 1). For power users there are **5
memorable verbs** (Layer 2); everything else is auto-triggered inside `analyze`
or reachable by asking, not memorised. All verbs are served by the one shared
engine, so numbers never diverge.

| Command | Answers | Backed by |
|---|---|---|
| `/finance-skills <question>` | anything — routes to the right lens | `analyze` + intent routing |
| `/finance-skills analyze <ticker\|question>` | "should I invest?" end-to-end (flagship) | `scripts/analyze.py` |
| `/finance-skills valuation <ticker>` | "is it cheap?" | DCF + multiples + Rule 40 view of `analyze` |
| `/finance-skills growth <ticker>` | "is it growing?" | growth + margins + regime view |
| `/finance-skills risk <ticker>` | "what could go wrong?" | leverage, FCF, dilution, capital-intensity gap |
| `/finance-skills moat <ticker>` | "does it have a durable edge?" | margins vs peers + `references/` |
| `/finance-skills help` | grouped command help | `scripts/router.py help` |

Shorthand and typos resolve instead of erroring (`val`→valuation, `r40`→rule40,
`comp`→compare, `semis`→semiconductor, `vluation`→valuation). Sub-frameworks like
`rule40`, `ai-cloud`, `compare`, `redflags` remain reachable for power users but
aren't top-level verbs.

### `analyze` — example output

`/finance-skills analyze CRWV` (shown on the offline sample via `--fixture`;
live output has the same shape with a yfinance source + timestamp):

```text
═══ CoreWeave, Inc. (CRWV) ═══
Source: fixture · as of 2026-Q1  [SAMPLE DATA — not live]
Sector: Technology / Information Technology Services
Price: $100   Market cap: $48.00B

Fundamentals (derived):
  Revenue growth (YoY): 111.1%
  EBITDA margin: 56.0%   FCF margin: -315.8%
  Capex intensity: 463.2%   Share dilution: 9.1%
  Net debt: $11.50B

Rule of 40 — regime: ai neocloud
  EBITDA-based: 167   FCF-based: -205   capital-intensity gap: 372
  Capex-adjusted: -668   dilution-adjusted: -677
  Judged on -668 vs benchmark 38 → BELOW BAR
  Verdict: Capital-intensive: growth is burning cash faster than it earns; watch backlog/RPO and funding runway.
    • Neocloud regime: the EBITDA-based score overstates health; judging on the capex-adjusted FCF score to reflect real GPU capital burn.
    • Large capital-intensity gap (372 pts) — growth is capex-funded, not organically profitable.

DCF: DCF skipped: free cash flow is not positive (typical for capex-heavy growth names).
Leverage: net debt / EBITDA = 10.81x

────────────────────────────────────────────────────────────
Read-only market analysis for research/education. Not investment advice; no trades are placed. Verify figures against primary filings before acting.
```

The `valuation`, `growth`, `risk`, and `moat` verbs run the same engine and lead
with the matching slice of that report (e.g. `risk` leads with leverage 10.81×,
the −372 capital-intensity gap, and dilution).

### `help` — example output

`/finance-skills help`:

```text
finance-skills — ask in plain English, or use a verb.

Top verbs:  analyze  valuation  growth  risk  moat

By question:
  Is it cheap?           →  valuation, rule40, benchmark
  Is it safe?            →  risk, redflags, health
  Will it grow?          →  growth, opportunities, earnings
  Does it have an edge?  →  moat, management, classify
  How does it compare?   →  compare, competitors, benchmark
  What's happening now?  →  news, earnings
  Sector-specific        →  semiconductor, ai-cloud, banking, reit, insurance
  Power tools            →  screen, rank, portfolio, watchlist, export

Shorthand works too: val→valuation, r40→rule40, comp→compare, semis→semiconductor.
Typos are tolerated (e.g. 'vluation' → valuation).
```

### Natural-language front door — example

`/finance-skills Do you think NBIS and CRWV is a buy?` first extracts the tickers,
then runs the engine per ticker:

```text
$ python3 scripts/router.py tickers "Do you think NBIS and CRWV is a buy?"
NBIS CRWV
$ python3 scripts/router.py r40
r40 → rule40 (alias)
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
