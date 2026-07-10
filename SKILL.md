---
name: finance-skills
description: Analyze a public stock from real fundamentals and answer investor questions in plain English. Use whenever someone asks about a ticker or company — is it a good buy, overvalued, cheap, or fairly priced; its revenue growth, margins, free cash flow, Rule of 40, DCF / intrinsic value, moat, management, dilution, debt / leverage, financial health, red flags, or risks; a head-to-head comparison of two tickers; or AI-cloud / neocloud GPU capex and backlog (CoreWeave CRWV, Nebius NBIS), semiconductors, banks, or REITs. Triggers on questions like "is NVDA a good buy", "do you think NBIS is a buy", "why is AMD's margin dropping", "should I worry about PLTR's cash flow", "is Nebius overvalued", "rule of 40 for CRM", "how does AMD compare to NVDA". Read-only market research; never places trades and is not investment advice.
when_to_use: Any question about a specific public company's fundamentals, valuation, growth, profitability, financial health, moat, risks, or a comparison — whether typed as `/finance-skills ...` or asked in plain chat.
argument-hint: "[verb] <ticker or plain-English question>"
allowed-tools: Read, Grep, Glob, Bash(python3 *), Bash(python *), Bash(pip install *)
---

# finance-skills

Analyst-style equity research driven by **real data**, not narrated numbers.
Ask in plain English; the skill extracts the ticker, runs a fetch → compute
pipeline, and answers the specific question.

## Safety & scope (read first)

- **Read-only.** Reads public market data only. Never places trades or touches an account.
- **Not investment advice.** Research/education. Tell the user to verify against primary filings.
- **Live data needs Claude Code / a networked host.** Fetching uses `yfinance`; on the Claude.ai sandbox there is no network — use `--fixture` (CRWV, NBIS samples) or say live data is unavailable.
- Always show the data **source** and **as-of** date; fixture data is labelled `[SAMPLE DATA — not live]`.

## Invocation contract

Works as `/finance-skills <plain-English question>` **or**
`/finance-skills <verb> <plain-English question>`. For example, all of these are
valid and mean the same thing:

```
/finance-skills is NBIS a buy?
/finance-skills analyze Do you think NBIS is a buy?
/finance-skills analyze NBIS
```

Handle any of them in three steps:

1. **Identify the ticker(s).** Map company names you know (Nvidia → NVDA,
   Nebius → NBIS). For explicit symbols in a sentence, you may use the helper:
   ```bash
   python3 scripts/router.py tickers "Do you think NBIS is a buy?"   # -> NBIS
   ```
   If no ticker can be found, ask the user which company they mean.

2. **Determine intent.** If the first token is a verb (`company`, `analyze`,
   `valuation`, `framework`, `compare`, `learn`, `growth`, `risk`, `moat`,
   `dcf`, `rule40`, `redflags`, `health`, `screen`, `fiveforces`, `industry`, …)
   or a known alias (`co`, `fw`, `val`, `r40`, `comp`, …), use it. Otherwise infer
   intent. For plain-English questions, the router has an explicit **keyword map**
   (`KEYWORDS`) that resolves the phrase to a verb deterministically — prefer it
   over guessing:
   ```bash
   python3 scripts/router.py route "is NBIS a value trap?"   # -> risk
   python3 scripts/router.py route "any red flags in PLTR?"  # -> redflags
   ```
   `route` returns a verb only when a trigger phrase matches (longest phrase
   wins); when it returns none, fall back to the semantic routing table below.
   Resolve shorthand/typos on a single token with `python3 scripts/router.py <token>`.

3. **Run the matching command, then answer the actual question.** Every command
   is a view over the one engine (`scripts/analyze.py`), so numbers never diverge:
   ```bash
   python3 scripts/company.py    <TICKER> [--fixture|--json]   # sequential walkthrough
   python3 scripts/valuation.py  <TICKER> [--fixture|--json]   # "is it cheap?" as a table
   python3 scripts/framework.py  <name> <TICKER> [--fixture]   # a framework as a checklist
   python3 scripts/redflags.py   <TICKER> [--fixture|--json]   # "what could go wrong?" flags
   python3 scripts/health.py     <TICKER> [--fixture|--json]   # solvency / leverage / runway
   python3 scripts/compare.py    <A> <B> [...] [--fixture]     # side-by-side table
   python3 scripts/analyze.py    <TICKER> [--fixture|--json]   # flagship report
   python3 scripts/screen.py     "<rule>" [TICKER ...]         # filter a set by a rule
   python3 scripts/watchlist.py  <add|list|run ...>            # saved lists, any verb across them
   python3 scripts/export.py     <TICKER> [--verb= --format=]  # md/json/csv report file
   python3 scripts/learn.py      <concept>                     # explain a concept (offline)
   ```
   Read the output and answer in plain English — lead with the part that answers
   what they asked (e.g. "is it a buy?" → valuation + Rule 40 + risk), cite the
   concrete numbers with source + as-of, and end with the not-advice note.

**Formatting — table vs prose (match the shape of the answer):**
- **Table** when the answer is comparable numbers: `valuation`, `framework`,
  `rule40`, `growth`, `risk`. Use a **Metric | Value | Read** layout (the Read
  column says how to interpret each number). `valuation.py` and `framework.py`
  already emit this; mirror it for the agent-rendered verbs.
- **Side-by-side table** for `compare <a> <b>` — one column per ticker, metrics
  as rows, so the contrast is instant.
- **Prose / narrative** when the shape is a story or a judgment: `company` (keep
  the sequential ▼ walkthrough), `moat` / `fiveforces` (qualitative), and
  `learn` (an explainer). A table would flatten these — don't force one.

If `yfinance` is missing: `pip install yfinance`.

### Intent routing table (internal)

| User asks about… | Emphasise |
|---|---|
| cheap / overvalued / fair price / "a buy" | valuation, DCF, Rule 40 vs benchmark |
| safe / risky / could it collapse | net debt, leverage, FCF, dilution, capital-intensity gap |
| growing / trend | revenue growth, margins, regime |
| business quality / edge / moat | margins vs peers, moat (references) |
| "tell me about X" / full picture | `company.py` — the 9-stage walkthrough |
| SaaS / neocloud / semis checklist | `framework.py <name>` — runs the whole lens at once |
| "what is / explain <concept>" | `learn.py <concept>` — teach it, no ticker needed |
| compare to X | run the engine for both, contrast |
| AI-cloud / GPU / backlog | load `references/ai-cloud.md`, stress capex-adjusted Rule 40 |

Semantic intent, not keyword match — "is this stock a trap" → risk + redflags.

## The engine

One shared engine backs everything (`scripts/`), so numbers never diverge:
- `data.py` — fetches & normalises fundamentals via yfinance (graceful fallback, 6h cache).
- `metrics.py` — pure math: the **segment-aware Rule of 40**, DCF, EV/EBITDA, Altman Z, Piotroski.
- `analyze.py` — orchestrates fetch → compute → report (`--json` for composing).
- `company.py` — sequences the engine into a 9-stage narrative walkthrough.
- `framework.py` — runs a named framework (saas, neocloud, semiconductor) as a checklist.
- `redflags.py` — scans the engine report for warning signs, with severity.
- `health.py` — solvency view: leverage, self-funding, cash runway, dilution.
- `compare.py` — side-by-side table for two+ tickers, one column each.
- `screen.py` — filters a set of tickers by a tiny, safe `field op value` rule language.
- `watchlist.py` — persists named ticker lists (`.cache/`) and runs any verb across them.
- `export.py` — renders a verb's output to a Markdown/JSON/CSV file.
- `learn.py` — offline concept explainers (no ticker, no network).
- `router.py` — ticker extraction, alias/fuzzy resolution, **keyword→verb routing**, grouped help.

Honesty rule: `framework.py` computes only what the filings support. Metrics that
need a **disclosed KPI not in the financial statements** (Magic Number, CAC
payback, NRR, backlog/RPO) are flagged "needs disclosed KPI" with their
definition — never fabricated. Say the same when answering in prose.

## Two layers of use

**Layer 1 — natural language (default).** Most users just ask a question; follow
the invocation contract above.

**Layer 2 — memorable verbs (power users), the primary interface.** Each is a
view over the same engine, so numbers never diverge:

- `company <ticker>` — 9-stage sequential walkthrough (Business Model → … → Verdict)
- `analyze <ticker>` — full analyst report (flagship engine dump)
- `framework <name> <ticker>` — a whole lens at once (saas / neocloud / semiconductor)
- `valuation <ticker>` — "is it cheap?" as a Metric/Value/Read table (DCF, EV/Sales, EV/EBITDA, Rule 40) → `scripts/valuation.py`
- `dcf <ticker>` — intrinsic value only
- `rule40 <ticker>` — the segment-aware Rule of 40 slice
- `growth <ticker>` — revenue/margin trend + regime
- `risk <ticker>` — leverage, FCF, dilution, concentration
- `redflags <ticker>` — warning-sign scan with severity → `scripts/redflags.py`
- `health <ticker>` — solvency, leverage, cash runway → `scripts/health.py`
- `moat <ticker>` / `fiveforces <ticker>` — durable-edge / Porter assessment
- `compare <a> <b> [...]` — real side-by-side table → `scripts/compare.py`
- `screen "<rule>" [tickers]` — filter by `field op value` (rule40, growth, fcf_margin, …) → `scripts/screen.py`
- `watchlist add|list|run <verb>` — saved lists, any verb across them → `scripts/watchlist.py`
- `export <ticker> --format md|json|csv` — shareable report file → `scripts/export.py`
- `learn <concept>` — teach a concept (dcf, rule40, magic-number, nrr, …)

`fiveforces` and `industry` are qualitative: apply the framework using the
engine's margins/growth as evidence (`learn.py five-forces` gives the template);
don't invent force ratings from the financials.

### Help & aliases

If asked for help, group by the question — never an alphabetical dump:

```
Whole company         → company, analyze, framework
Is it cheap?          → valuation, dcf, rule40, benchmark
Is it safe?           → risk, redflags, health
Will it grow?         → growth, opportunities, earnings
Does it have an edge? → moat, fiveforces, management
How does it compare?  → compare, competitors, industry
Learn a concept       → learn
Sector-specific       → semiconductor, ai-cloud, banking, reit, insurance
Power tools           → screen, rank, portfolio, watchlist, export
```

Shorthand/typos resolve, not error (`val`→valuation, `r40`→rule40, `vluation`→valuation):
`python3 scripts/router.py help` and `python3 scripts/router.py <token>`.

## Reading the segment-aware Rule of 40

Do **not** treat 40 as a universal pass mark — see `references/rule40.md`:
- A **neocloud** (CRWV/NBIS) shows a huge EBITDA-based score that is misleading;
  judge it on the **capex-adjusted** score and the **capital-intensity gap**.
- A **steady** name is judged on the FCF-based score vs a mature (~42) bar.
- Always report EBITDA-based *and* FCF-based, and call out the gap.

## References (load on demand)

- `references/rule40.md` — segment-aware Rule of 40 methodology and benchmarks.
- `references/ai-cloud.md` — AI-cloud/neocloud framework (GPU capex, backlog/RPO, runway).
