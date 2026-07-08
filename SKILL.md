---
name: financial-skills
description: Analyze a public stock ticker from real fundamentals. Use when the user asks whether a stock is a good buy, is overvalued, cheap, or fairly priced; asks about revenue growth, margins, free cash flow, Rule of 40, DCF/intrinsic value, moat, management, dilution, debt/leverage, financial health, red flags, or risks; asks to compare two tickers; asks about AI-cloud/neocloud GPU capex and backlog (CoreWeave CRWV, Nebius NBIS), semiconductors, banks, or REITs; or types questions like "is NVDA a good buy", "why is AMD's margin dropping", "should I worry about PLTR's cash flow", "is Nebius overvalued", "rule of 40 for CRM", "how does AMD compare to NVDA". Read-only market research; never places trades and is not investment advice.
when_to_use: Any question about a specific public company's fundamentals, valuation, growth, profitability, financial health, competitive moat, risks, or a head-to-head comparison — whether phrased as a slash command or plain English.
argument-hint: "<ticker or plain-English question>"
allowed-tools: Read, Grep, Glob, Bash(python3 *), Bash(python *), Bash(pip install *)
---

# financial-skills

Analyst-style equity research driven by **real data**, not narrated numbers.
Every figure comes from a fetch + compute pipeline, so the model never guesses a
margin or growth rate.

## Safety & scope (read first)

- **Read-only.** This skill only reads public market data. It never places trades or touches an account.
- **Not investment advice.** Outputs are for research/education. Tell the user to verify against primary filings before acting.
- **Live data needs Claude Code.** Fetching uses `yfinance` (network). It works on Claude Code; on the Claude.ai sandbox there is no network, so use `--fixture` for the bundled samples (CRWV, NBIS) or state that live data is unavailable.
- Always show the data **source** and **as-of** date. Fixture data is labelled `[SAMPLE DATA — not live]`.

## The engine

One shared engine backs everything (`scripts/`):
- `data.py` — fetches & normalises fundamentals via yfinance (graceful fallback, 6h cache).
- `metrics.py` — pure math: the **segment-aware Rule of 40**, DCF, Altman Z, Piotroski, margins.
- `analyze.py` — orchestrates fetch → compute → report.

Run it:

```bash
python3 scripts/analyze.py NVDA          # full report (live)
python3 scripts/analyze.py NVDA --json    # structured output to compose from
python3 scripts/analyze.py CRWV --fixture # offline sample (no network)
```

If `yfinance` is missing, install it: `pip install yfinance`.

## How to respond (two layers)

### Layer 1 — natural language (default)

Most users ask questions, not commands. Parse the ticker(s) and intent, run
`analyze.py <ticker> --json`, then answer the *specific* question using those
numbers. Route intent to the relevant part of the report:

| User asks about… | Emphasise from the report |
|---|---|
| cheap / overvalued / fair price | valuation, DCF, Rule 40 vs benchmark |
| safe / risky / could it collapse | net debt, leverage, FCF, dilution, capital-intensity gap |
| growing / trend | revenue growth, margins, regime |
| business quality / edge | margins vs peers, moat (see references) |
| compare to X | run `analyze.py` for both, contrast side by side |
| AI-cloud / GPU / backlog | load `references/ai-cloud.md`, stress capex-adjusted Rule 40 |

### Layer 2 — explicit verbs (power users)

Five memorable verbs map onto the same engine; treat any others (`rule40`,
`ai-cloud`, `compare`, …) as views over `analyze`:

- `analyze <ticker>` — full report (flagship)
- `valuation <ticker>` — lead with DCF + multiples
- `growth <ticker>` — lead with revenue/margin trend + regime
- `risk <ticker>` — lead with leverage, FCF, dilution, concentration
- `moat <ticker>` — durable-edge assessment (references + margins)

### Help & aliases

If the user asks for help / a command list, group by the question they're
answering — never dump an alphabetical list:

```
Is it cheap?          → valuation, rule40, benchmark
Is it safe?           → risk, redflags, health
Will it grow?         → growth, opportunities, earnings
Does it have an edge? → moat, management, classify
How does it compare?  → compare, competitors, benchmark
What's happening now? → news, earnings
Sector-specific       → semiconductor, ai-cloud, banking, reit, insurance
Power tools           → screen, rank, portfolio, watchlist, export
```

Shorthand and typos should resolve, not error — `val`→valuation, `r40`→rule40,
`comp`→compare, `semis`→semiconductor, `vluation`→valuation. Use the resolver to
canonicalize any command token and to print help:

```bash
python3 scripts/router.py <token>   # e.g. vluation → valuation (fuzzy)
python3 scripts/router.py help       # grouped help above
```

## Reading the segment-aware Rule of 40

Do **not** treat 40 as a universal pass mark. The engine classifies a growth
regime and picks the fair lens — see `references/rule40.md`:
- A **neocloud** (CRWV/NBIS) posts a huge EBITDA-based score that is misleading;
  judge it on the **capex-adjusted** score and the **capital-intensity gap**.
- A **steady** name is judged on the FCF-based score vs a mature (~42) bar.
- Always report EBITDA-based *and* FCF-based, and call out the gap.

## References (load on demand)

- `references/rule40.md` — the full segment-aware Rule of 40 methodology and benchmarks.
- `references/ai-cloud.md` — the AI-cloud/neocloud sector framework (GPU capex, backlog/RPO, funding runway).
