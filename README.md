# finance-skills

[![CI](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/notEhEnG/finance-skills/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/finance-skills)](https://pypi.org/project/finance-skills/)
[![Python](https://img.shields.io/pypi/pyversions/finance-skills)](https://pypi.org/project/finance-skills/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**The guardrailed fundamentals layer for AI agents. When your agent talks about a stock, this is what keeps it honest.**

Ask any coding agent "is NBIS a buy?" and you'll get one of two failure modes: confidently *invented* numbers (a DCF "reasoned" from memory), or a data dump with no argument. finance-skills is built on a different split:

> **A deterministic engine computes every number. Your agent builds the argument. Neither is allowed to do the other's job.**

```text
# 1) Install skill (Claude Code)
curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/v0.13.0/install.sh | bash -s -- claude

# 2) In the agent
/finance-skills is CRWV a buy?
```

**Real session — Claude Code answering "is NVDA overvalued?" with live data:**

![agent demo](docs/demo-agent.gif)

*([full-quality video](docs/demo-agent.mp4) · engine-only terminal demo below)*

![demo](docs/demo.gif)

**Who this is for:** Claude Code / Codex / Antigravity / Cursor-style agent users, and people building tool-using agents who need financial claims they can audit.
**Who this is not for:** stock tips, portfolio advice, or r/investing "what should I buy" threads.

---

## Why use this finance skill

Five design strengths:

1. **Numbers are computed, never narrated.** Rule of 40 and EV multiples are calculated by tested Python (`scripts/metrics.py`), not "reasoned" by the model. DCF, Altman Z, and Piotroski remain pure helpers that require their stated inputs; the company path never fills them by guesswork. If a number isn't in the engine report, the agent cannot present it as engine output.
2. **Fail-closed, not fail-plausible.** Missing debt is never a silent zero. Negative FCF doesn't produce a fake DCF — it produces `disabled_analyses` with the reason and the unlock. The skill would rather tell you what it *can't* conclude than invent a conclusion.
3. **The analyst layer is mandated, not hoped for.** The agent contract ([`SKILL.md`](SKILL.md) §4a) requires a **conditional thesis** — setup, the bull case the numbers support, the bear case, a conditional screen, what to watch — never a metric dump, never "Buy/Hold/Sell + target price." Two tickers must never produce interchangeable answers.
4. **A public three-tier checker makes the contract testable.** Answers are linted as **safe → useful → synthesized** ([`docs/eval.md`](docs/eval.md)): policy failures, caveat walls/JSON dumps, and generic ticker-swappable prose. It is a deterministic contract checker, not proof of investment accuracy or universal model compliance.
5. **Capital-intensive growth gets a separate lens.** The engine shows EBITDA- and FCF-based Rule of 40, the broader EBITDA-to-FCF gap, capex intensity, and an explicitly labelled EBITDA-minus-capex proxy. FCF already includes capex, so capex is never deducted from FCF twice ([`references/ai-cloud.md`](references/ai-cloud.md), [`references/rule40.md`](references/rule40.md)).

Plus: **no paid API key** (free yfinance layer + explicit offline fixtures), portable across agents, MIT-licensed, and no brokerage/trading side effects. Local cache/watchlist/report writes are append-only or refuse existing paths.

---

## The failure mode (exact)

| Without skill | With skill |
|---------------|------------|
| Model invents FCF % or intrinsic value | Metrics from one engine report |
| Missing debt → silent zero | Fail-closed; DCF/EV disabled with reason |
| "I'd buy the dip" | Policy: analysis only, never a recommendation |
| Metric dump with no argument | Mandated conditional thesis (§4a) |
| Fixture demo treated as live tape | `data_state: fixture` + mandatory disclosure |

**Data quality:** live pulls use **yfinance** (delayed, incomplete, label-noisy). Reports preserve provider state, currency, retrieval time, financial period, source URL, and per-field period metadata when available; mixed annual/TTM margins fail closed. Always verify revenue, FCF, debt, cash, shares, and capex in **10-K/10-Q**. Fixtures (CRWV, NBIS) are **sample data, not live** and are never automatic fallbacks.

---

## How this differs from other finance skills

Most agent finance skills on GitHub fall into three classes — each fails a different way:

| Class | Where numbers come from | The problem | This skill |
|-------|------------------------|-------------|------------|
| **Prompt-only** ("no runtime, every skill is a prompt") | The model *reasons about* a DCF or F-Score from memory | Hallucinated numbers with confident formatting | The engine **computes** every metric; the model may not state a number that isn't in the report |
| **Web-search analysts** | Search results pasted into the context | Unverifiable figures + explicit "Buy/Hold/Sell + target price" output | Fail-closed evidence policy; **never** a recommendation — a conditional valuation screen instead |
| **API wrappers** | A paid data vendor behind an API key | Data delivery without an analysis contract; vendor lock-in | Free data layer + an explicit **agent contract**: the engine keeps the agent honest, the agent builds the argument |

Prompt-only skills emphasize analyst prose; API wrappers emphasize data delivery. finance-skills combines a deterministic fact layer with an explicit agent contract and a public, reproducible checker.

---

## Architecture

```text
                    "Is NBIS a buy?"
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │ Your agent (Claude Code, Codex,     │
        │ Antigravity, Cursor, …)             │
        └───────────────┬─────────────────────┘
                        │  one call:
                        │  python3 scripts/ask.py --json "<question>"
                        ▼
  ┌───────────────────────────────────────────────────┐
  │ FACT LAYER — deterministic, tested in CI          │
  │                                                   │
  │  router.py   intent + tickers (valuation /        │
  │              redflags / learn / refuse / …)       │
  │  data.py     yfinance fetch · offline fixtures ·  │
  │              6h cache · fail-closed normalization │
  │  metrics.py  Rule of 40 · EV multiples · explicit │
  │              assumption DCF · Z · Piotroski helpers│
  │  analyze.py  → engine_report: calculations,       │
  │              flags, disabled_analyses, source     │
  └───────────────┬───────────────────────────────────┘
                  │  answer_draft (evidence floor)
                  │  + full report (verification)
                  ▼
  ┌───────────────────────────────────────────────────┐
  │ ANALYST LAYER — your agent, mandated by SKILL.md  │
  │                                                   │
  │  weighs the bull/bear tension in the report       │
  │  writes the conditional thesis (§4a)              │
  │  every number must trace back to the report       │
  └───────────────┬───────────────────────────────────┘
                  ▼
     setup → bull case → bear case → conditional
     screen → what to watch → not investment advice

     scored by the public eval: safe → useful → synthesized
```

Every verb (`brief`, `valuation`, `redflags`, `health`, `company`, `compare`, `framework`) is a **view over the same engine**, so numbers never diverge between commands.

---

## Agent interaction (contract)

1. **User:** "Is CRWV a buy?"
2. **Agent runs one command:**
   `python3 scripts/ask.py --json "Is CRWV a buy?"` (add `--fixture` for sample data)
3. **Engine returns** `answer_draft` + full `report` (disabled DCF, fixture flag, evidence)
4. **Agent writes its own analyst answer on top** — weighing the bull/bear tensions in
   the report, in the conditional-thesis shape (SKILL.md §4a) — then **stops scripting**
   (`stop_tool_loop`). `answer_draft` is the evidence floor, not the final reply.
5. No buy/sell recommendation; numbers only from the draft/report

**Hard gate:** if `ask` (or legacy `route --json` + engine `--json`) did not run this turn for an in-scope company question, **do not state financial numbers.**

**Anti-pattern:** chaining five Python scripts and dumping JSON.
**Success:** one `ask` → an original analyst answer where every number traces to the report.

Full policy: [`SKILL.md`](SKILL.md) · templates: [`docs/agent-policy.md`](docs/agent-policy.md) · eval: [`docs/eval.md`](docs/eval.md)

---

## Install

**Skill (primary)**

```bash
curl -fsSL https://raw.githubusercontent.com/notEhEnG/finance-skills/v0.13.0/install.sh | bash -s -- claude
# codex | antigravity | all
```

The installer is version-pinned, copies an allowlisted payload, and refuses to
overwrite an existing skill directory. Set `FINANCE_SKILLS_REF` only when you
intentionally want a different tag.

| Runtime | Status | Path |
|---------|--------|------|
| Claude Code | **tested** (skill dir + bash engine) | `.claude/skills/finance-skills/` |
| Codex-compatible | **best effort** | `.codex/skills/` (or `CODEX_SKILLS_DIR`) |
| Antigravity | **best effort** | `.antigravity/skills/finance-skills/` |
| Cursor-style | **best effort** (attach skill + run scripts) | project skill copy |
| MCP server | **not shipped** (see roadmap) | — |

**CLI (secondary)**

```bash
pip install finance-skills
finance-skills brief CRWV --fixture
```

---

## Slash commands

```text
/finance-skills is NVDA overvalued?
/finance-skills is PLTR a value trap?
/finance-skills brief CRWV
/finance-skills valuation AAPL
/finance-skills compare AMD NVDA
/finance-skills learn rule40
/finance-skills help
```

| Intent | Module |
|--------|--------|
| default / quick take | `brief` |
| cheap / buy / worth / DCF | `valuation` (analysis, not a rec) |
| value trap / red flags | `redflags` |
| balance sheet / runway | `health` |
| compare / vs | `compare` |
| walkthrough | `company` |
| sector checklist (saas / neocloud / semis) | `framework` |
| concept only (no ticker) | `learn` |
| personal "what should I buy/sell" | **refuse** |

```bash
python3 scripts/router.py route --json "Is CRWV a buy?"
python3 scripts/brief.py CRWV --fixture --json   # includes engine_report
```

---

## Output & fail-closed

Every core verb JSON includes **`engine_report`**:

- `source.data_state`: live | cache | fixture | unavailable | …
- `disabled_analyses`: reason_code + unlock
- `response_guidance.prohibited_claims` / `mandatory_caveats`
- calculations never encode unknown net debt as `0`
- metric provenance includes currency/period/source metadata when supplied
- cached snapshots are labelled `cache`, never `live`

Schema: [`docs/engine-report.schema.json`](docs/engine-report.schema.json)

---

## Eval (public)

The repository ships a deterministic contract checker with three tiers ([`docs/eval.md`](docs/eval.md)):

| Tier | Catches |
|------|---------|
| **Safe** (hard fails) | unrecognized report numbers · buy/sell language · hidden disabled DCF · fixture-as-live |
| **Useful** | caveat walls · raw JSON dumps · answers with no analytical substance |
| **Synthesized** | `answer_draft` pasted verbatim (courier behavior) · missing conditional-thesis structure · generic answers that would survive a **ticker swap** |

```bash
python -m pytest tests/test_agent_transcripts.py tests/test_route_request.py -q
```

Plus a 20-prompt bare-model-vs-skill protocol you can re-run on your own model.
The checker is a policy/provenance lint, not a substitute for validating upstream
data or financial methodology against filings.

---

## Roadmap

**Shipped**

- ✅ 0.13.0 — provenance + period alignment, no capex double-counting, explicit-assumption DCF boundary, contract-complete framework/compare/screen JSON, safer routing/eval/install/export persistence
- ✅ 0.8.x — one-shot `ask` path, table/emoji multi-ticker output, hardened error handling
- ✅ 0.9.0 — **analyst-layer contract**: fact layer → analyst layer, §4a conditional thesis, `respond_with_synthesis`
- ✅ 0.10.0 — **synthesis eval tier**: safe → useful → synthesized, ticker-swap proxy, courier detection

**Next**

- **Published per-agent eval table** — run the 20-prompt eval on Claude Code / Codex / Antigravity and publish hard-fail, synthesized, and ticker-swap rates per agent
- **AI-infrastructure vertical, deepened** — fail-closed backlog/RPO ingestion (user-pasted, never invented), GPU-fleet depreciation flags, funding-runway calculation — the metrics that actually decide the CRWV/NBIS debate
- **Semiconductor vertical** — cycle-aware framework depth for NVDA/AMD-class questions (inventory, capex intensity, concentration)

**Later**

- MCP server packaging (same engine, MCP transport)
- Additional data-provider fallbacks behind the same fail-closed normalization
- More sector frameworks (banks, REITs, insurance) promoted from references to computed checklists

Roadmap principle: **depth in verticals where invented numbers are most dangerous, before breadth.**

---

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -q --cov=scripts
ruff check scripts tests && mypy scripts
```

Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md) · Security: [`SECURITY.md`](SECURITY.md) · Changelog: [`CHANGELOG.md`](CHANGELOG.md)

Where to talk about this: agent / Claude Code / tool communities — **not** as stock advice on investing subs. See [`docs/SOCIAL.md`](docs/SOCIAL.md).

---

## License

[MIT](LICENSE) · Read-only research · **Not investment advice**
