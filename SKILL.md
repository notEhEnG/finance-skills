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

2. **Determine intent.** If the first token is a verb (`analyze`, `valuation`,
   `growth`, `risk`, `moat`) or a known alias (`val`, `r40`, `comp`, …), use it.
   Otherwise infer intent from the question via the routing table below. Resolve
   shorthand/typos with `python3 scripts/router.py <token>`.

3. **Run the engine, then answer the actual question.**
   ```bash
   python3 scripts/analyze.py <TICKER> --json      # live
   python3 scripts/analyze.py <TICKER> --fixture    # offline sample
   ```
   Read the JSON and answer in plain English — lead with the part that answers
   what they asked (e.g. "is it a buy?" → valuation + Rule 40 + risk), cite the
   concrete numbers with source + as-of, and end with the not-advice note.

If `yfinance` is missing: `pip install yfinance`.

### Intent routing table (internal)

| User asks about… | Emphasise |
|---|---|
| cheap / overvalued / fair price / "a buy" | valuation, DCF, Rule 40 vs benchmark |
| safe / risky / could it collapse | net debt, leverage, FCF, dilution, capital-intensity gap |
| growing / trend | revenue growth, margins, regime |
| business quality / edge / moat | margins vs peers, moat (references) |
| compare to X | run the engine for both, contrast |
| AI-cloud / GPU / backlog | load `references/ai-cloud.md`, stress capex-adjusted Rule 40 |

Semantic intent, not keyword match — "is this stock a trap" → risk + redflags.

## The engine

One shared engine backs everything (`scripts/`), so numbers never diverge:
- `data.py` — fetches & normalises fundamentals via yfinance (graceful fallback, 6h cache).
- `metrics.py` — pure math: the **segment-aware Rule of 40**, DCF, Altman Z, Piotroski.
- `analyze.py` — orchestrates fetch → compute → report (`--json` for composing).
- `router.py` — ticker extraction, alias/fuzzy command resolution, grouped help.

## Two layers of use

**Layer 1 — natural language (default).** Most users just ask a question; follow
the invocation contract above.

**Layer 2 — five memorable verbs (power users).** Everything else is a view over
`analyze`, not a command to memorise:

- `analyze <ticker>` — full report (flagship)
- `valuation <ticker>` — lead with DCF + multiples
- `growth <ticker>` — revenue/margin trend + regime
- `risk <ticker>` — leverage, FCF, dilution, concentration
- `moat <ticker>` — durable-edge assessment

### Help & aliases

If asked for help, group by the question — never an alphabetical dump:

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
