# finance-skills

[![PyPI version](https://img.shields.io/pypi/v/finance-skills?color=blue)](https://pypi.org/project/finance-skills/)
[![Python versions](https://img.shields.io/pypi/pyversions/finance-skills)](https://pypi.org/project/finance-skills/)
[![License: MIT](https://img.shields.io/pypi/l/finance-skills?color=green)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/notEhEnG/finance-skills?sort=semver)](https://github.com/notEhEnG/finance-skills/releases)
[![GitHub stars](https://img.shields.io/github/stars/notEhEnG/finance-skills?style=flat)](https://github.com/notEhEnG/finance-skills/stargazers)

Analyst-style equity research as an agent skill — driven by **real fundamentals**,
not narrated numbers. Ask about any public ticker in plain English and get a
report built from a fetch → compute pipeline.

**Install:** `pip install finance-skills` · **[PyPI](https://pypi.org/project/finance-skills/)** · read-only, not investment advice.

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

### Keyword routing (plain English → verb)

Step 2 isn't a guess. The router carries an explicit **keyword map**: trigger
phrases resolve a plain-English question to a verb deterministically (the
**longest matching phrase wins**, so `"is it a buy"` beats a bare `"buy"`). Only
the top verbs are keyworded; anything else still resolves from an explicit verb
token or the semantic routing table.

```bash
python3 scripts/router.py route "is NBIS a value trap?"   # -> risk
python3 scripts/router.py route "any red flags in PLTR?"  # -> redflags
python3 scripts/router.py route "how does AMD compare to NVDA"  # -> compare
```

| If the question sounds like… | Trigger phrases (examples) | Routes to |
|---|---|---|
| is it cheap / a buy | `is it a buy`, `overvalued`, `undervalued`, `fair value`, `should i buy`, `cheap` | `valuation` |
| is it safe | `is it safe`, `value trap`, `blow up`, `go bankrupt`, `too much debt`, `risky` | `risk` |
| anything wrong | `red flag(s)`, `warning sign`, `going concern`, `anything to worry` | `redflags` |
| can it survive | `financial health`, `balance sheet`, `cash runway`, `solvency`, `self-funding` | `health` |
| is it growing | `growth rate`, `top line`, `is it growing`, `decelerating`, `accelerating` | `growth` |
| does it have an edge | `a moat`, `competitive advantage`, `pricing power`, `defensible` | `moat` |
| what's it worth | `intrinsic value`, `discounted cash flow`, `fair price`, `dcf`, `worth` | `dcf` |
| is growth efficient | `rule of 40`, `rule40`, `r40` | `rule40` |
| which is better | `compare`, `versus`, `vs`, `head-to-head`, `better than` | `compare` |
| tell me everything | `tell me about`, `walk me through`, `full picture`, `deep dive` | `company` |

`route` returns nothing when no phrase matches (then the agent falls back to the
semantic routing table); a leading question word like *what*/*how* never hijacks
routing. The map lives in `KEYWORDS` in [`scripts/router.py`](scripts/router.py).

## Slash commands

Plain English always works (Layer 1). But the **verbs are the primary interface** —
a polished CLI over one shared engine, so numbers never diverge across commands.

| Command | Answers | Backed by |
|---|---|---|
| `/finance-skills <question>` | anything — routes to the right lens | `analyze` + intent routing |
| `/finance-skills company <ticker>` | "tell me about this company" — a guided walkthrough | `scripts/company.py` |
| `/finance-skills analyze <ticker>` | "should I invest?" end-to-end (flagship) | `scripts/analyze.py` |
| `/finance-skills framework <name> <ticker>` | "run the SaaS / neocloud / semis lens" | `scripts/framework.py` |
| `/finance-skills valuation <ticker>` | "is it cheap?" | DCF + EV/EBITDA + Rule 40 |
| `/finance-skills dcf <ticker>` | "what's it worth?" | DCF slice of `analyze` |
| `/finance-skills rule40 <ticker>` | "is growth efficient?" | segment-aware Rule of 40 |
| `/finance-skills growth <ticker>` | "is it growing?" | growth + margins + regime |
| `/finance-skills risk <ticker>` | "what could go wrong?" | leverage, FCF, dilution, capex gap |
| `/finance-skills redflags <ticker>` | "any warning signs?" | `scripts/redflags.py` (severity-ranked flags) |
| `/finance-skills health <ticker>` | "can it survive?" | `scripts/health.py` (leverage, runway, dilution) |
| `/finance-skills moat <ticker>` | "does it have a durable edge?" | margins vs peers + `references/` |
| `/finance-skills fiveforces <ticker>` | "how good is the industry structure?" | Porter, applied to engine evidence |
| `/finance-skills compare <a> <b> [...]` | "which is better?" | `scripts/compare.py` (side-by-side table) |
| `/finance-skills screen "<rule>" [tickers]` | "which pass this filter?" | `scripts/screen.py` (`field op value`) |
| `/finance-skills watchlist add\|list\|run <verb>` | "track a set, run any verb across it" | `scripts/watchlist.py` |
| `/finance-skills export <ticker> --format md\|json\|csv` | "give me a shareable file" | `scripts/export.py` |
| `/finance-skills learn <concept>` | "what *is* a Magic Number / DCF / NRR?" | `scripts/learn.py` (offline) |
| `/finance-skills help` | grouped command help | `scripts/router.py help` |

Shorthand and typos resolve instead of erroring (`co`→company, `fw`→framework,
`val`→valuation, `r40`→rule40, `5forces`→fiveforces, `vluation`→valuation).

### `company` — example output (the guided walkthrough)

`/finance-skills company CRWV` steps through the business top-to-bottom, each
stage flowing into the next, and ends with a synthesised verdict:

**At a glance:** the 9 stages for CRWV — strong margins (gross **70%**) but
**BELOW** its Rule-of-40 bar, negative FCF, and a verdict that hinges on
**backlog & funding runway**.

```text
═══ CoreWeave, Inc. (CRWV) — company walkthrough ═══
Source: fixture · as of 2026-Q1  [SAMPLE DATA — not live]
Price: $100   Market cap: $48.00B

■ Business Model
    Sector: Technology / Information Technology Services
    AI neocloud/hyperscaler — extreme growth funded by heavy GPU capex; judged on cash burn and backlog, not headline EBITDA.
        ▼
■ Competitive Advantage
    Gross margin 70.0% — high; suggests pricing power or a software-like cost structure.
    EBITDA margin 56.0% — operating leverage already showing.
        ▼
■ Revenue Drivers
    Revenue: $1.90B
    Growth (YoY): 111.1%.
        ▼
■ Margins
    Gross: 70.0%   EBITDA: 56.0%   FCF: -315.8%
    Negative free cash flow — growth is consuming cash (normal for the regime, watch runway).
        ▼
■ Financial Health
    Net debt: $11.50B
    Net debt / EBITDA: 10.81x — elevated; watch refinancing and covenants.
        ▼
■ Growth
    Growth rate: 111.1%
    AI neocloud/hyperscaler regime.
        ▼
■ Valuation
    DCF: DCF skipped: free cash flow is not positive (typical for capex-heavy growth names).
    EV/EBITDA: 55.9x.
        ▼
■ Risks
    Capital-intensity gap 372 pts — growth is capex-funded, not organically profitable.
    Below its Rule-of-40 bar (judged -668 vs 38).
    Share dilution 9.1% YoY — growth partly 'bought' with equity.
    Cash burn — depends on continued access to funding.
        ▼
■ Final Verdict
    A capital-intensive neocloud: the story is backlog and funding runway, not this quarter's margin.
    Falls short of its Rule-of-40 bar today.
    No DCF (FCF not positive), so lean on Rule-of-40 and multiples instead of intrinsic value.
    Not a recommendation — verify against primary filings before acting.
```

### `valuation` — "is it cheap?" as a table

`/finance-skills valuation <ticker>` lays the valuation slice out as a scannable
**Metric | Value | Read** table (DCF, EV/Sales, EV/EBITDA, Rule 40), flagging a
distorted EV/EBITDA when EBITDA margin exceeds 100%:

```text
═══ CoreWeave, Inc. (CRWV) — valuation ═══
Source: fixture · as of 2026-Q1  [SAMPLE DATA — not live]

  Metric              Value        Read
  ───────────────────────────────────────────────────────────────────
  Price               $100         —
  Market cap          $48.00B      —
  Enterprise value    $59.50B      market cap + net debt
  EV / Sales          31.3x        extreme — priced on growth, not sales
  EV / EBITDA         55.9x        expensive
  DCF / share         n/a          FCF negative — DCF skipped
  Rule of 40          -668 vs 38   BELOW BAR (ai neocloud)
  Revenue growth      111.1%       hypergrowth
  FCF margin          -315.8%      cash burn — depends on funding
  Net debt / EBITDA   10.81x       elevated — watch refinancing

Verdict: No DCF (FCF not positive), so it can't be anchored to intrinsic value — expensive on EV/Sales 31.3x; a growth/backlog bet, not supported by current cash flows.
```

### `framework` — run a whole lens at once (honest about data)

`/finance-skills framework saas CRWV` runs every SaaS metric instead of making
you pick. Metrics that need a **disclosed KPI not in the financial statements**
(Magic Number, CAC payback, NRR) are flagged with their definition — never faked:

**At a glance:** computed from filings — Rule of 40 **BELOW BAR**, gross margin
**70.0%**, EV/EBITDA **55.9x**; Magic Number, CAC payback & NRR flagged
_**needs disclosed KPI**_ rather than fabricated.

```text
═══ CoreWeave, Inc. (CRWV) — SaaS / software quality framework ═══
Source: fixture · as of 2026-Q1  [SAMPLE DATA — not live]

  Metric                        Value / status
  ───────────────────────────────────────────────────────────────────
  Rule of 40                    judged -668 vs 38 bar → BELOW BAR (EBITDA 167 / FCF -205, gap 372)
  Gross margin                  70.0%
  FCF margin                    -315.8%
  Revenue growth (YoY)          111.1%
  EV/EBITDA                     55.9x
  Magic Number                  ⚠ needs disclosed KPI
  CAC payback                   ⚠ needs disclosed KPI
  Net revenue retention (NRR)   ⚠ needs disclosed KPI

  Not in the financial statements — check the 10-K / investor deck (defined, not faked):
    • Magic Number — net-new ARR ÷ prior-quarter S&M spend; >0.75 = efficient growth. Needs S&M + ARR disclosure.
    • CAC payback — months of gross-margin-adjusted revenue to recover customer acquisition cost. Needs S&M + new-customer/ARR disclosure.
    • Net revenue retention (NRR) — expansion − churn on existing customers; >120% is elite. A disclosed KPI, not in the financial statements.
```

Frameworks: `saas`, `neocloud`, `semiconductor` (`python3 scripts/framework.py list`).

### `learn` — teach the concept, no ticker needed

`/finance-skills learn dcf` (also `rule40`, `magic-number`, `nrr`, `five-forces`, …):

```text
═══ dcf ═══
Discounted cash flow: a company is worth the present value of its future free cash flow.

How to compute / read it:
  Two-stage model: grow FCF for N years, discount each year back, add a Gordon terminal value, subtract net debt, divide by shares. Here growth is a heuristic (trailing revenue growth, capped), discount 10%, terminal 3%.

Common trap:
  Output is only as good as the assumptions — tiny changes in growth/discount swing it wildly. Treat it as a rough anchor, and note it's skipped when FCF is negative.
```

### `analyze` — example output

`/finance-skills analyze CRWV` (shown on the offline sample via `--fixture`;
live output has the same shape with a yfinance source + timestamp):

**At a glance:** CRWV — AI-neocloud regime · Rule of 40 **BELOW BAR** (-668 vs
38) · burning cash (FCF **-315.8%**) · leverage **10.81x**.

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
the 372-pt capital-intensity gap, and dilution).

### `help` — example output

`/finance-skills help`:

```text
finance-skills — ask in plain English, or use a verb.

Top verbs:  company  analyze  valuation  framework  compare  learn

By question:
  Whole company          →  company, analyze, framework
  Is it cheap?           →  valuation, dcf, rule40, benchmark
  Is it safe?            →  risk, redflags, health
  Will it grow?          →  growth, opportunities, earnings
  Does it have an edge?  →  moat, fiveforces, management
  How does it compare?   →  compare, competitors, industry
  Learn a concept        →  learn
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
├── pyproject.toml          # PEP 621 packaging (installs scripts/ as `finance_skills`)
├── scripts/                # sources — also the importable `finance_skills` package
│   ├── __init__.py         # package marker + __version__
│   ├── _entry.py           # console entry: `finance-skills` -> router.main(argv)
│   ├── data.py             # yfinance fetch + normalise + 6h cache + graceful fallback
│   ├── metrics.py          # PURE engine: segment-aware Rule 40, DCF, EV/EBITDA, Altman Z, Piotroski
│   ├── analyze.py          # orchestrator: fetch → compute → report (flagship `analyze`)
│   ├── company.py          # 9-stage sequential walkthrough (view over analyze)
│   ├── framework.py        # named frameworks as checklists (saas/neocloud/semiconductor)
│   ├── redflags.py         # warning-sign scan with severity (view over analyze)
│   ├── health.py           # solvency: leverage, cash runway, dilution (view over analyze)
│   ├── compare.py          # side-by-side table for two+ tickers
│   ├── screen.py           # filter a set of tickers by a tiny `field op value` rule
│   ├── watchlist.py        # saved named ticker lists; run any verb across them
│   ├── export.py           # render a verb to a Markdown / JSON / CSV file
│   ├── learn.py            # offline concept explainers (no ticker, no network)
│   └── router.py           # ticker extraction + alias/fuzzy + keyword→verb routing (pure)
├── references/
│   ├── rule40.md           # segment-aware Rule of 40 methodology + benchmarks
│   └── ai-cloud.md         # AI-cloud/neocloud sector framework (capex, backlog/RPO)
├── tests/                  # offline unit tests (pure math + orchestrator + router + CLI)
└── requirements.txt        # yfinance
```

The same files serve two roles. Run in place, `python3 scripts/<mod>.py` drives
the agent skill (what SKILL.md / install.sh use). Installed from PyPI, the
directory is remapped to the importable **`finance_skills`** package with a
`finance-skills` console command — the intra-module imports resolve both ways via
a small `try: from finance_skills import … / except ImportError: import …` shim.

The **engine is one source of truth**: `metrics.py` is pure and offline-testable;
`data.py` is the only module that touches the network; `analyze.py` composes them.
Every specialised command (company, framework, valuation, dcf, rule40, risk…) is
a *view* over `analyze`, so numbers never diverge between commands.

## Install as a Python package

```bash
pip install finance-skills          # console command + importable engine
finance-skills help                 # grouped command help
python -c "import finance_skills"   # the engine as a library
```

## CLI usage (also drives the skill)

```bash
pip install -r requirements.txt

python3 scripts/analyze.py NVDA            # full live report
python3 scripts/company.py NVDA             # guided 9-stage walkthrough
python3 scripts/framework.py saas NVDA      # run the SaaS lens as a checklist
python3 scripts/learn.py rule40             # explain a concept (offline)
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
python3 -m pytest tests/ -q     # 118 offline tests (no network needed)
```

- `tests/test_metrics.py` — regime classification, dual-margin/capex-adjusted
  Rule 40 (locks the CoreWeave/Nebius examples), DCF guards, Altman Z, Piotroski.
- `tests/test_analyze.py` — orchestrator on fixtures + graceful no-data path.
- `tests/test_data.py` — statement column-ordering + net-debt fail-closed behaviour.
- `tests/test_company.py` — the 9 walkthrough stages, in order, with data-gap flags.
- `tests/test_framework.py` — computed metrics vs honestly-flagged disclosed KPIs.
- `tests/test_learn.py` — concept/alias/fuzzy resolution for the explainers.
- `tests/test_router.py` — ticker extraction, alias/fuzzy + keyword→verb routing, grouped help.
- `tests/test_redflags.py` / `test_health.py` / `test_compare.py` — the new engine views.
- `tests/test_screen.py` — the safe `field op value` rule parser and fail-closed missing data.
- `tests/test_watchlist.py` / `test_export.py` — persistence and md/json/csv output.
- `tests/test_entry.py` — the `finance-skills` console entry point runs `help`.

## Status & roadmap

The real engine proven end-to-end on live data plus offline fixtures, installable
as a cross-tool skill, with a **verb-first CLI** (`company`, `framework`, `learn`,
…) layered over it. Next, over the same engine: more sector references
(`semiconductor.md`, `banking.md`, `reit.md`), `screen`/`rank` views, trend
arrows, and backlog/RPO ingestion to light up the framework KPI rows.
