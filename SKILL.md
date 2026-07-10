---
name: finance-skills
description: Analyze a public stock from real fundamentals and answer investor questions in plain English. Use whenever someone asks about a ticker or company — is it a good buy, overvalued, cheap, or fairly priced; its revenue growth, margins, free cash flow, Rule of 40, DCF / intrinsic value, moat, management, dilution, debt / leverage, financial health, red flags, or risks; a head-to-head comparison of two tickers; or AI-cloud / neocloud GPU capex and backlog (CoreWeave CRWV, Nebius NBIS), semiconductors, banks, or REITs. Triggers on questions like "is NVDA a good buy", "do you think NBIS is a buy", "why is AMD's margin dropping", "should I worry about PLTR's cash flow", "is Nebius overvalued", "rule of 40 for CRM", "how does AMD compare to NVDA". Read-only market research; never places trades and is not investment advice.
when_to_use: Any question about a specific public company's fundamentals, valuation, growth, profitability, financial health, moat, risks, or a comparison — whether typed as `/finance-skills ...` or asked in plain chat.
argument-hint: "[verb] <ticker or plain-English question>"
allowed-tools: Read, Grep, Glob, Bash(python3 *), Bash(python *), Bash(pip install *)
---

# finance-skills

Analyst-style equity research driven by **real data**, not narrated numbers.
**General on any public ticker**; sharpest where capital intensity breaks naive
SaaS math (regime-aware Rule of 40). One fetch → compute engine so numbers
never diverge across questions.

## Safety & scope (read first)

- **Read-only.** Public market data only. Never places trades.
- **Not investment advice.** Verify against primary filings.
- **Live data** needs a networked host + `yfinance`. Offline: `--fixture` (CRWV, NBIS) or say live data is unavailable.
- Always show **source** and **as-of**; fixtures are labelled `[SAMPLE DATA — not live]`.
- **Fail-closed + guided gaps.** Never invent net debt, Rule of 40 inputs, or KPIs. If a field is missing, say so and what disclosure unlocks it.

## Product tiers

| Tier | Verbs | Rule |
|------|--------|------|
| **Core** (engine) | `brief`, `company`, `analyze`, `valuation`, `dcf`, `rule40`, `growth`, `risk`, `redflags`, `health`, `framework`, `compare`, `screen`, `watchlist`, `export`, `learn` | Numbers from `build_report` only |
| **Lens** (qualitative) | `moat`, `fiveforces` | Use engine margins/growth as **evidence**; do **not** invent force ratings or moat scores |
| **Framework names** | `saas`, `neocloud`, `semiconductor` (alias `ai-cloud` → neocloud) | Run `framework.py <name> <TICKER>` — not fake top-level engines |
| **Not product verbs** | rank, portfolio, news, earnings, banking, reit, … | Do not advertise; freeform only if the user insists, without claiming a module |

## Invocation contract

`/finance-skills <plain-English>` **or** `/finance-skills <verb> …`.

### Three steps

1. **Ticker(s)** — map names you know; or:
   ```bash
   python3 scripts/router.py tickers "Do you think NBIS is a buy?"
   ```
   If none, ask which company.

2. **Intent** — prefer the router (deterministic; **always** returns a verb):
   ```bash
   python3 scripts/router.py route "is NBIS a value trap?"   # -> redflags
   python3 scripts/router.py route "thoughts on NBIS?"       # -> brief (default)
   finance-skills brief NBIS --fixture                       # CLI dispatches Core modules
   finance-skills NBIS --fixture                             # bare ticker → brief
   ```
   - Keyword / explicit Core verb → that module.
   - Sector word → `framework <name>` (structured: command=framework).
   - **Nothing matched → `brief`** (always; not opt-in).
   - Legacy aliases: `r40`/`rule40`/`growth`→`brief`, `dcf`→`valuation`, `risk`→`redflags`.
   - Lens (`moat`, `fiveforces`) = qualitative only — no engine module.
   - Explicit `analyze` / `company` only for full dump / walkthrough.

3. **Run the engine view, then answer-first.**

### Answer-first (mandatory after Core output)

1. **3–6 sentences** that answer the user’s question, using **only** engine figures + regime frame.
2. Then the table / structured brief (or cite key lines).
3. End with not-advice; list **gaps** if any (what’s missing + what unlocks it).
4. Prefer **`--json`** on `brief` when composing so you don’t re-parse ASCII.

### Commands

```bash
python3 scripts/brief.py       <TICKER> [--fixture|--json]   # DEFAULT stack
python3 scripts/company.py     <TICKER> [--fixture|--json]   # 9-stage walkthrough
python3 scripts/analyze.py     <TICKER> [--fixture|--json]   # dense flagship dump
python3 scripts/valuation.py   <TICKER> [--fixture|--json]
python3 scripts/framework.py   <saas|neocloud|semiconductor> <TICKER> [--fixture]
python3 scripts/redflags.py    <TICKER> [--fixture|--json]
python3 scripts/health.py      <TICKER> [--fixture|--json]
python3 scripts/compare.py     <A> <B> [...] [--fixture]
python3 scripts/screen.py      "<rule>" [TICKER ...]
python3 scripts/watchlist.py   <add|list|run ...>
python3 scripts/export.py      <TICKER> [--verb=brief|valuation|...] [--format=md|json|csv]
python3 scripts/learn.py       <concept>
```

If `yfinance` is missing: `pip install yfinance`.

### Default stack = `brief`

Fixed spine over `analyze.build_report` (no second math path):

1. Identity (source, as-of)
2. Regime + dual/preferred Rule of 40 + capital-intensity gap
3. Valuation (EV/S, EV/EBITDA, DCF if allowed)
4. Solvency (net debt, FCF margin, dilution)
5. Top red flags (0–3)
6. **`gaps[]`**
7. Disclaimer

### Formatting

- **Table** for comparable numbers (`valuation`, `framework`, …).
- **Side-by-side** for `compare`.
- **Prose walkthrough** for `company`; **answer-first prose** for `brief` and most questions.
- **Lens** (`moat` / `fiveforces`): short structured judgment with engine numbers as evidence only.

## The engine

- `data.py` — fetch/normalize (only network module); tickers path-safe.
- `metrics.py` — pure math: segment-aware Rule of 40, DCF, EV multiples, …
- `analyze.py` — orchestrates `build_report`.
- `brief.py` — default answer-shaped view.
- Other verbs — views over the same report.
- `router.py` — tickers, aliases, keywords, Core/Lens help, default `brief`.

Honesty: never fabricate disclosed KPIs (Magic Number, NRR, backlog/RPO). Flag **needs disclosed KPI** and add a gap.

## Segment-aware Rule of 40

Do **not** treat 40 as universal — see `references/rule40.md`:

- **Neocloud** (e.g. CRWV/NBIS): judge **capex-adjusted** + capital-intensity gap; EBITDA score alone misleads.
- **Steady**: FCF-based vs stage/sector bar.
- Always report dual scores when present.

## References (on demand)

- `references/rule40.md` — regime methodology.
- `references/ai-cloud.md` — neocloud lens (GPU capex, backlog/RPO).
