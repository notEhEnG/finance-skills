# finance-skills

[![CI](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/finance-skills?color=blue)](https://pypi.org/project/finance-skills/)
[![Python versions](https://img.shields.io/pypi/pyversions/finance-skills)](https://pypi.org/project/finance-skills/)
[![License: MIT](https://img.shields.io/pypi/l/finance-skills?color=green)](LICENSE)

**Analyst-style equity research from real fundamentals — one engine, many views.**

Ask in plain English or call a verb. Numbers come from a single fetch → compute pipeline (Rule of 40, DCF, red flags, compare, screen…), so answers never drift between commands.

> **Read-only. Not investment advice.** Public data only; verify against 10-K/10-Q filings before acting.

```bash
pip install finance-skills
finance-skills brief CRWV --fixture    # offline sample
finance-skills is NBIS a value trap?   # routes → redflags
```

Also installs as an agent skill (`/finance-skills …`) for Claude Code, Codex, and similar tools.

---

## Why this exists

Most stock helpers either invent numbers or slap a flat Rule-of-40 on everything. This project:

| Principle | What you get |
|-----------|----------------|
| **One engine** | `brief`, `valuation`, `redflags`, `compare`, `screen`… all share `build_report` |
| **Regime-aware Rule of 40** | Neocloud / hypergrowth vs steady SaaS — EBITDA vs FCF capital-intensity gap |
| **Fail-closed** | Missing debt/cash/FCF → analysis skipped with **exact** missing inputs, never fabricated |
| **Agent-ready** | Deterministic keyword routing, `--json`, gaps + filing checklist for the next step |

Sharpest on growth and capital-intensive tech (AI infra, SaaS-like names) where headline growth can hide weak cash economics. Works on any public ticker yfinance can fetch.

Methodology: [`references/rule40.md`](references/rule40.md) · [`references/ai-cloud.md`](references/ai-cloud.md)

---

## Install

```bash
pip install finance-skills
finance-skills help
```

**As an agent skill** (Claude Code / Antigravity / Codex):

```bash
curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/main/install.sh | bash -s -- claude
# or: bash -s -- antigravity | codex | all
```

Then invoke: `/finance-skills is NVDA overvalued?`

Live data needs network + `yfinance`. Offline demos: `--fixture` (CRWV, NBIS sample data, clearly labelled).

---

## Quick start

```bash
# Default stack (regime, Rule 40, multiples, solvency, flags, gaps)
finance-skills brief NVDA
finance-skills NBIS --fixture                 # bare ticker → brief

# Common questions
finance-skills valuation AAPL
finance-skills redflags PLTR
finance-skills compare AMD NVDA
finance-skills framework neocloud CRWV --fixture

# Personas & teaching
finance-skills brief NBIS --fixture --style=risk --explain
finance-skills learn rule40

# Peers & screening
finance-skills compare --preset=ai-infra --fixture
finance-skills screen "growth > 50 and fcf_margin < 0" CRWV NBIS --fixture
```

Plain English is routed automatically (`value trap` → redflags, `is it a buy` → valuation, default → **brief**). Details: [`SKILL.md`](SKILL.md).

---

## Commands

| Verb | Job |
|------|-----|
| **`brief`** | Default answer stack (what most questions want) |
| `company` | 9-stage walkthrough |
| `analyze` | Dense full dump |
| `valuation` | Multiples + DCF + scenarios when allowed |
| `redflags` / `health` | Warning signs / solvency |
| `framework` | `saas` · `neocloud` · `semiconductor` checklist |
| `compare` | Side-by-side (+ `--preset=saas\|ai-infra\|semiconductor\|megacap`) |
| `screen` / `watchlist` | Filter & track a universe |
| `export` | Markdown / JSON / CSV |
| `learn` | Offline concept explainers (no ticker) |

**Flags (where relevant):** `--fixture` · `--json` · `--style=value|growth|quality|risk` · `--explain`

Aliases: `val`→valuation, `risk`→redflags, `r40`/`growth`→brief, `dcf`→valuation, `semis`→framework semiconductor.

---

## Example (offline fixture)

`finance-skills brief CRWV --fixture` — AI neocloud sample. Headline growth looks fine; cash economics and Rule of 40 do not:

```text
═══ CoreWeave, Inc. (CRWV) — brief ═══
Source: fixture · as of 2026-Q1  [SAMPLE DATA — not live]
Price: $100   Market cap: $48.00B

Regime: ai neocloud
Rule of 40: preferred -668 vs bar 38 → BELOW BAR
  EBITDA-based 167 · FCF-based -205 · capital-intensity gap 372
  Capex-adjusted -668
  Capital-intensive: growth is burning cash faster than it earns; watch backlog/RPO and funding runway.

Valuation
  EV / Sales:   31.3x
  EV / EBITDA:  55.9x
  DCF / share:  n/a — DCF skipped because free cash flow is not positive (…)

Solvency / quality
  Revenue growth: 111.1%
  FCF margin:     -315.8%
  Capex intensity: 463.2%
  Dilution:       9.1%
  Net debt/EBITDA: 10.81x

Top red flags
  ⛔ Cash burn · ⛔ Elevated leverage · ⚠ Heavy dilution

Disabled analyses (exact inputs)
  · dcf: free cash flow is not positive → unlocks via sustainable positive FCF + …

Filing verification checklist (before trusting this output)
  · free cash flow, debt, cash, share count, capex, backlog/RPO …
```

That is the product thesis in one screen: **same engine**, **regime-aware Rule of 40**, **fail-closed DCF**, **what to verify next**.

---

## Architecture

```text
data.py (IO only)  →  metrics.py (pure math)  →  analyze.build_report
                                                    ↓
                         brief · valuation · redflags · company · compare · …
```

| Layer | Role |
|-------|------|
| `data.py` | Fetch / cache / fixtures — only network module |
| `metrics.py` | Rule 40, DCF (+ scenarios), EV multiples — no I/O |
| `analyze.py` | One structured report |
| Views | Format & emphasize; never recompute |
| `router.py` | Tickers, aliases, keywords, CLI dispatch |

Safety invariants (read-only, no brokers, no `eval`) are enforced in CI — see [`SECURITY.md`](SECURITY.md).

---

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/ -q --cov=scripts
python -m ruff check scripts tests
python -m mypy
```

Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md) · Changelog: [`CHANGELOG.md`](CHANGELOG.md)

---

## License

[MIT](LICENSE) · © contributors
