# finance-skills

[![CI](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/finance-skills)](https://pypi.org/project/finance-skills/)
[![Python](https://img.shields.io/pypi/pyversions/finance-skills)](https://pypi.org/project/finance-skills/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Stop AI agents from inventing stock numbers.**

`finance-skills` is a skill your coding agent (Claude Code, Codex, Cursor, MCP-style tools) runs before it talks about a public company. It pulls **real fundamentals**, runs **deterministic** Rule of 40 / DCF / red-flag math, and **fails closed** when inputs are missing — so the model reasons over facts, not vibes.

```bash
pip install finance-skills
# or: install as /finance-skills skill → see Install
finance-skills brief CRWV --fixture
```

<!-- TODO: record a 15–20s terminal GIF: agent asks "is CRWV a buy?" → skill runs → brief output -->
![demo](docs/demo.gif)

---

## Real output

Offline sample (`--fixture`). Live runs use yfinance + the same engine.

```text
$ finance-skills brief CRWV --fixture

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

Same numbers in `valuation`, `redflags`, `compare`, `screen` — one engine, many views.

---

## Why it exists

LLMs are great at *language about finance* and terrible at *honest arithmetic under incomplete data*.

They will:

- invent EV/EBITDA when debt is missing  
- apply SaaS Rule of 40 to a GPU neocloud  
- sound confident while compounding a bad assumption  

Agents that trade time for money need a **financial reasoning layer** that:

1. Fetches real public data  
2. Computes metrics offline and deterministically  
3. Refuses to print a figure when inputs are incomplete (**fail-closed**)  
4. Returns structured gaps so the agent can say what to check in the 10-K  

That layer is this repo. Read-only. Not investment advice. Verify filings.

---

## vs ChatGPT (or any chat model alone)

| | Chat model alone | + finance-skills |
|--|------------------|------------------|
| Numbers | Often invented or stale memory | From fetch + pure functions |
| Missing data | Fills in zeros / “looks fine” | Skips analysis + names the missing field |
| Rule of 40 | One flat 40 | Regime-aware (neocloud vs SaaS), dual margin |
| Reproducibility | Temperature & mood | Same inputs → same report |
| Agent contract | Prose blob | Tables + `--json` + gaps[] |

Use the model for **judgment and prose**. Use this for **the numbers**.

---

## vs “just give the agent MCP / yfinance”

| | Raw MCP / yfinance in the prompt | finance-skills |
|--|----------------------------------|----------------|
| What the agent gets | Tables, series, nulls | Analyst-shaped report |
| Math | Model re-derives (and drifts) | One `build_report` path |
| Consistency | Every tool call diverges | brief ≡ valuation ≡ redflags |
| Safety | Easy to eval rules or over-fetch | Screen is a tiny parser; no eval; AST safety tests |
| Fail-closed | Optional | Default |

MCP is a **pipe**. This is a **policy + engine** the agent is forced to go through.

---

## Features

- **Agent skill** — `/finance-skills …` or CLI `finance-skills`  
- **Plain English routing** — `is it a value trap?` → redflags; bare ticker → brief  
- **Segment-aware Rule of 40** — capital-intensity gap; neocloud ≠ SaaS bar  
- **Valuation** — EV/S, EV/EBITDA, DCF when allowed + bear/base/bull scenarios  
- **Red flags / health** — burn, leverage, dilution, runway  
- **Compare + peer presets** — `--preset=saas|ai-infra|semiconductor|megacap`  
- **Screen / watchlist** — tiny rule language + ranking summary  
- **`--style` / `--explain`** — value · growth · quality · risk emphasis  
- **Fail-closed diagnostics** — disabled analyses + filing checklist  
- **Offline fixtures** — CRWV / NBIS without network  
- **CI-enforced safety** — one network module, no brokers, no eval ([`SECURITY.md`](SECURITY.md))

---

## Architecture

```text
agent (Claude Code / Codex / Cursor / …)
        │
        ▼
  router  →  brief | valuation | redflags | compare | …
        │
        ▼
  analyze.build_report   ← one structured report
        │
   ┌────┴────┐
   ▼         ▼
 data.py   metrics.py
 (IO only) (pure, deterministic)
```

Views never recompute. If two verbs disagree, that’s a bug.

---

## Installation

**CLI / library**

```bash
pip install finance-skills
finance-skills help
```

**As a skill** (Claude Code, Antigravity, Codex-style dirs)

```bash
curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/main/install.sh | bash -s -- claude
# bash -s -- antigravity | codex | all
```

Live data: network + yfinance. Sandbox / offline: `--fixture`.

---

## Quick start

```bash
finance-skills brief NVDA
finance-skills NBIS --fixture
finance-skills "is PLTR a value trap?"
finance-skills valuation AAPL --json
finance-skills compare --preset=ai-infra --fixture
finance-skills brief CRWV --fixture --style=risk --explain
```

Agent path: `/finance-skills is NVDA overvalued?` → skill runs engine → answer-first prose using **only** engine figures.

Full contract: [`SKILL.md`](SKILL.md)

---

## Examples

**Route a question (deterministic)**

```bash
$ finance-skills route "is NBIS a value trap?"
redflags  [keyword]
```

**Valuation table**

```bash
finance-skills valuation CRWV --fixture
```

**Peer preset + ranking**

```bash
finance-skills compare --preset=ai-infra --fixture
```

**Teach a concept (no network)**

```bash
finance-skills learn rule40
```

---

## FAQ

**Is this investment advice?**  
No. Research/education only. Verify primary filings.

**Does it place trades?**  
No. Read-only by architecture; CI fails if a broker SDK appears.

**Why not let the model call yfinance itself?**  
Because the model will still invent the *second* step (margins, DCF, “fine” leverage). The skill owns fetch + math + refusal.

**What if data is missing?**  
We skip the analysis and list exact missing inputs + what filing unlocks them. We do not impute net debt as 0.

**Does it work offline?**  
Yes — `--fixture` for CRWV/NBIS. Pure metrics are fully unit-tested offline.

**Python versions?**  
3.10+

---

## Contributing

```bash
pip install -e ".[dev]"
pytest tests/ -q --cov=scripts
ruff check scripts tests
mypy
```

PRs welcome. Prefer tests that lock fail-closed behavior. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

[MIT](LICENSE)
