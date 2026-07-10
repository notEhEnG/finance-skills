# finance-skills

[![CI](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/finance-skills)](https://pypi.org/project/finance-skills/)
[![Python](https://img.shields.io/pypi/pyversions/finance-skills)](https://pypi.org/project/finance-skills/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Stop AI agents from inventing stock numbers.**

`finance-skills` is a **skill** your coding agent (Claude Code, Codex, Cursor, MCP-style tools) runs before it talks about a public company. It pulls **real fundamentals**, runs **deterministic** Rule of 40 / DCF / red-flag math, and **fails closed** when inputs are missing — so the model reasons over facts, not vibes.

```text
# Install the skill (Claude Code example)
curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/main/install.sh | bash -s -- claude

# Then in the agent:
/finance-skills is CRWV a buy?
/finance-skills brief NBIS
/finance-skills compare AMD NVDA
```

<!-- TODO: 15–20s GIF — user types /finance-skills … → engine output → agent answer-first -->
![demo](docs/demo.gif)

---

## Install (agent first)

**1. Install as a skill** — primary path for Claude Code / Codex / Cursor-style agents:

```bash
curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/main/install.sh | bash -s -- claude
# or:  bash -s -- antigravity | codex | all
```

| Tool | Skill path | Invoke |
|------|------------|--------|
| Claude Code | `.claude/skills/finance-skills/` | `/finance-skills …` |
| Antigravity | `.antigravity/skills/finance-skills/` | `/finance-skills …` |
| Codex-compatible | `<skill-dir>/finance-skills/` | `/finance-skills …` |

The agent needs `python3` + network (for live data) or uses `--fixture` offline. If needed: `pip install yfinance`.

**2. Optional CLI / library** (scripts, CI, non-agent hosts):

```bash
pip install finance-skills
finance-skills help
```

Live data: network + yfinance. Offline demos: fixtures (CRWV, NBIS). Full agent contract: [`SKILL.md`](SKILL.md).

---

## Slash commands

Type **`/finance-skills`** then a question or a verb. Plain English is routed deterministically; no verb → **`brief`**.

### Everyday (plain English)

```text
/finance-skills is NVDA overvalued?
/finance-skills do you think NBIS is a buy?
/finance-skills is PLTR a value trap?
/finance-skills how does AMD compare to NVDA?
/finance-skills rule of 40 for CRM
/finance-skills tell me about SNOW
/finance-skills what's the financial health of CRWV?
```

| Sounds like… | Routes to |
|--------------|-----------|
| cheap / buy / overvalued / DCF / worth | `valuation` |
| value trap / red flags / too much debt / risky | `redflags` |
| balance sheet / runway / solvency | `health` |
| rule of 40 / quick take / growth rate | `brief` |
| compare / vs / better than | `compare` |
| walk me through / deep dive | `company` |
| (nothing matched) | **`brief`** (default) |

### Explicit verbs

```text
/finance-skills brief CRWV
/finance-skills brief NBIS --style=risk --explain
/finance-skills valuation AAPL
/finance-skills redflags PLTR
/finance-skills health CRWV
/finance-skills company NVDA
/finance-skills analyze NBIS
/finance-skills framework neocloud CRWV
/finance-skills framework saas CRM
/finance-skills compare AMD NVDA
/finance-skills compare --preset=ai-infra
/finance-skills screen "growth > 50 and fcf_margin < 0" CRWV NBIS
/finance-skills learn rule40
/finance-skills help
```

| Slash form | Job |
|------------|-----|
| `/finance-skills brief <ticker>` | Default stack: regime, Rule 40, multiples, flags, gaps |
| `/finance-skills valuation <ticker>` | Cheap or not — EV/S, EV/EBITDA, DCF + scenarios |
| `/finance-skills redflags <ticker>` | What could go wrong |
| `/finance-skills health <ticker>` | Leverage, burn, runway |
| `/finance-skills company <ticker>` | 9-stage walkthrough |
| `/finance-skills analyze <ticker>` | Dense full dump |
| `/finance-skills framework <saas\|neocloud\|semiconductor> <ticker>` | Sector checklist (honest on missing KPIs) |
| `/finance-skills compare <a> <b> …` | Side-by-side (+ peer presets) |
| `/finance-skills screen "rule" …` | Filter tickers |
| `/finance-skills learn <concept>` | Offline explainer (no ticker) |
| `/finance-skills moat <ticker>` | **Lens** — qualitative; engine numbers as evidence only |

Aliases still work inside the skill: `val`→valuation, `risk`→redflags, `r40`→brief, `dcf`→valuation, `semis`→framework semiconductor.

**After every Core run**, the agent should answer-first in 3–6 sentences using **only** engine figures, then show the table, then not-advice + gaps. Prefer `--json` on `brief` when composing.

---

## Real output

What the skill’s engine prints (offline fixture). The agent wraps this in prose.

```text
/finance-skills brief CRWV

═══ CoreWeave, Inc. (CRWV) — brief ═══
Source: fixture · as of 2026-Q1  [SAMPLE DATA — not live]
Price: $100   Market cap: $48.00B

Regime: ai neocloud
Rule of 40: preferred -668 vs bar 38 → BELOW BAR
  EBITDA-based 167 · FCF-based -205 · capital-intensity gap 372
  Capex-adjusted -668

Valuation
  EV / Sales:   31.3x
  EV / EBITDA:  55.9x
  DCF / share:  n/a — DCF skipped because free cash flow is not positive (…)

Top red flags
  ⛔ Cash burn · ⛔ Elevated leverage · ⚠ Heavy dilution

Disabled analyses (exact inputs)
  · dcf: free cash flow is not positive
      missing: positive free cash flow

Filing verification checklist (before trusting this output)
  · free cash flow, debt, cash, share count, capex, backlog/RPO …
```

Same numbers if you had typed `/finance-skills valuation CRWV` or `/finance-skills redflags CRWV` — **one engine**, many views.

---

## Why it exists

LLMs are great at *language about finance* and terrible at *honest arithmetic under incomplete data*.

They invent EV/EBITDA when debt is missing, apply SaaS Rule of 40 to a GPU neocloud, and sound confident while compounding a bad assumption.

Agents need a **financial reasoning layer** that:

1. Fetches real public data  
2. Computes metrics offline and deterministically  
3. **Fails closed** when inputs are incomplete  
4. Returns gaps so the agent can say what to check in the 10-K  

That layer is this skill. Read-only. Not investment advice. Verify filings.

---

## vs ChatGPT alone

| | Chat model alone | + `/finance-skills` |
|--|------------------|---------------------|
| Numbers | Invented or stale memory | Fetch + pure functions |
| Missing data | “Looks fine” | Skips + names the missing field |
| Rule of 40 | Flat 40 | Regime-aware (neocloud vs SaaS) |
| Reproducibility | Mood | Same inputs → same report |

Use the model for **judgment**. Use the skill for **the numbers**.

---

## vs raw MCP / yfinance in the prompt

| | Raw MCP tables | This skill |
|--|----------------|------------|
| Agent gets | Series / nulls | Analyst-shaped report |
| Math | Model re-derives (drifts) | One `build_report` |
| Consistency | Diverges per call | brief ≡ valuation ≡ redflags |
| Fail-closed | Optional | Default |

MCP is a **pipe**. This is **policy + engine** in front of the model.

---

## Features

- **Slash skill first** — `/finance-skills …` in Claude Code, Codex, Cursor-class tools  
- **Plain-English routing** — deterministic keywords; default `brief`  
- **Segment-aware Rule of 40** — capital-intensity gap  
- **Valuation / redflags / health / company / framework**  
- **Compare presets** — saas · ai-infra · semiconductor · megacap  
- **Screen + watchlist + export + learn**  
- **`--style` / `--explain`** on brief  
- **Fail-closed diagnostics** + filing checklist  
- **CI safety** — one network module, no brokers, no eval ([`SECURITY.md`](SECURITY.md))

---

## Architecture

```text
you  →  /finance-skills …
              │
              ▼
        agent skill (SKILL.md)
              │
              ▼
     router → brief | valuation | redflags | …
              │
              ▼
     analyze.build_report   ← one structured report
         │            │
      data.py      metrics.py
      (IO only)    (pure, deterministic)
```

Views never recompute. If two verbs disagree, that’s a bug.

---

## CLI (optional)

Same engine if you’re not in an agent UI:

```bash
pip install finance-skills
finance-skills brief CRWV --fixture
finance-skills route "is NBIS a value trap?"   # → redflags
```

---

## FAQ

**Is this investment advice?** No. Verify primary filings.

**Does it place trades?** No. Read-only; CI fails on broker SDKs.

**Why not let the model call yfinance itself?** It still invents the *second* step (margins, DCF, “fine” leverage). The skill owns fetch + math + refusal.

**Missing data?** Skip the analysis; list exact missing inputs + what unlocks them. No imputed net debt = 0.

**Offline?** Yes — fixtures CRWV/NBIS; pure metrics unit-tested without network.

**Python?** 3.10+

---

## Contributing

```bash
pip install -e ".[dev]"
pytest tests/ -q --cov=scripts
ruff check scripts tests && mypy
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Prefer tests that lock fail-closed behavior.

---

## License

[MIT](LICENSE)
