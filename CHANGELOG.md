# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-07-11

### Added
- **Hard agent gate** in SKILL: no numbers without `route --json` + engine `--json` this turn.
- **`engine_report` on all core JSON verbs** (brief, valuation, redflags, health, company, analyze).
- **Public eval** `docs/eval.md` (20 prompts) + **transcript hard-fail** tests (`agent_eval`, `test_agent_transcripts`).
- **Demo GIF** `docs/demo.gif` (route → fixture → no-buy answer).
- **`docs/SOCIAL.md`** — post to agent/Claude communities, not investing subs.

### Changed
- README sells the **agent contract** first; data-quality (yfinance / 10-K) before demos.
- MCP described as **not shipped** (no vibe claims).

## [0.5.3] - 2026-07-11

### Added (agent middleware P0–P2)
- **Strict agent contract** in `SKILL.md` + `docs/agent-policy.md` (activation,
  sole-source evidence, response order, refuse personal advice, untrusted data).
- **`route_request()`** + `finance-skills route --json` machine-readable routing
  (`intent`, tickers, secondary_intents, refuse, learn, clarification).
- **Canonical EngineReport envelope** (`scripts/report_schema.py`,
  `docs/engine-report.schema.json`) attached to brief `--json` as `engine_report`.
- Routing table tests (40+) and schema/projection tests.
- Agent threat model section in `SECURITY.md`.

## [0.5.2] - 2026-07-11

### Changed
- **README rewritten as “AI agent financial skill”** — problem-first hero, vs ChatGPT /
  vs MCP, real fail-closed sample, agent-oriented install. Discoverability positioning
  for Claude Code / Codex / Cursor / AI engineers (not investors).

## [0.5.1] - 2026-07-11

### Changed
- **README rewrite** — focused landing page: one hero path, compact command table,
  single fixture example (brief/CRWV), short architecture. Removed outdated multi-page
  dumps, ghost-verb help sample, and per-test inventory (details stay in `SKILL.md` /
  `CHANGELOG`).

## [0.5.0] - 2026-07-11

### Added
- **Investor personas** on brief: `--style=value|growth|quality|risk` (same facts, different emphasis).
- **`--explain`**: plain-language “why this matters” for computed metrics (`explain.py`).
- **Precise missing-data diagnostics** + **filing verification checklist** on brief (`diagnostics.py`).
- **DCF scenarios** when inputs allow: bear/base/bull growth, discount-rate and FCF-conversion sensitivity (`metrics.dcf_scenarios`).
- **Peer presets** for compare: `--preset=saas|ai-infra|semiconductor|megacap` (`peers.py`); `compare list-presets`.
- **Ranking summary** on screen, compare, and `watchlist run rank` (`rank.py`).
- Shared presentation (`format.py`) and CLI plumbing (`cli.py`, `run_single_ticker`, `load_for_cli` everywhere).
- Single verb **builder registry** (`Verb.builder` → export/watchlist); co-located module dispatch.

### Changed
- `build_report` always returns a structured dict; text via `format_report` (no dual return type).
- Skill-path imports use `if __package__` so a stale site-packages install cannot shadow scripts/.
- Company **Risks** section uses `redflags.flags_for` (one policy).

### Fixed
- **DCF fail-closed on unknown net debt** (no more `net_debt or 0.0`); skip reasons name exact missing inputs (FCF, shares, debt/cash).

## [0.4.0] - 2026-07-11

### Added
- **`brief` — default answer-shaped stack** (`scripts/brief.py`): identity →
  regime/Rule of 40 → valuation → solvency → top red flags → `gaps[]` →
  disclaimer. Text + `--json` for agents.
- **Single verb registry** (`VERBS` in `router.py`) drives help, Core/Lens,
  and CLI dispatch. `route()` **always** returns a verb (default `brief`).
- **CLI dispatch**: `finance-skills brief NBIS`, bare `finance-skills NBIS`,
  and `finance-skills semiconductor CRWV` run real modules (not resolve-only).
- `redflags.flags_for(report, limit=…)` — public, severity-sorted; brief uses it.
- `data.normalize_ticker` / `load_for_cli` — shared CLI ticker boundary.

### Fixed
- **CLI verb-typo dispatch.** A mistyped verb with a ticker (`valuatoin NBIS`)
  was treated as a ticker and the real ticker dropped; a fuzzy verb now wins over
  the ticker fallback only when a later argument looks like the ticker.
- **Path traversal on the cache write surface.** A ticker like `../evil` was
  interpolated into a cache filename and could write outside the cache directory.
  Tickers are now validated at the IO boundary (`_normalize_ticker`) and
  `_cache_path` refuses any path resolving outside `CACHE_DIR`. Regression-tested.

### Changed
- Help / CANONICAL trimmed: removed unbuilt verbs (`rank`, `portfolio`, `news`,
  `earnings`, bare banking/REIT/… engines). Agent contract is answer-first +
  fail-closed guided gaps (see `SKILL.md`).

### Added (OSS hardening)
- Continuous integration (GitHub Actions): pytest matrix on Python 3.10–3.13,
  ruff lint, mypy type-check, and a build + install smoke test.
- `SECURITY.md` and `tests/test_safety.py` that **enforce** the read-only
  architecture as AST invariants (not keyword scans): one network boundary
  (`data.py` only), no brokerage/trading SDK import anywhere, and no
  `eval`/`exec`/`subprocess`/`os.system`.
- Adversarial tests for the `screen` rule parser; the parser now validates the
  whole rule up front (fail-closed) so a valid prefix can't mask a hostile clause.
- Offline tests for the `data.py` IO shell (cache, coercion, fixture fallback),
  lifting the security-surface module from ~52% to ~73% coverage; coverage floor
  raised to 80% (total ~82%).
- Community health files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue/PR
  templates, and a `dependabot.yml`.
- `ruff` + `mypy` + coverage configuration; a coverage floor in CI.
- Trusted-publishing release workflow (PyPI OIDC — no stored token).
- `[dev]` optional-dependency group.

### Changed (OSS hardening)
- **Minimum Python is now 3.10** (was 3.9). Python 3.9 reached end-of-life in
  October 2025 and no longer receives security fixes; dropping it lets CI, ruff's
  target, and mypy's checked version all agree on one supported floor. This is a
  deliberate, consumer-visible support change — pin `finance-skills<0.4` if you
  are still on 3.9.

## [0.3.0] - 2026-07-11

### Added
- Keyword routing: a `KEYWORDS` phrase→verb map and `router.py route` subcommand
  so plain-English questions resolve to a verb deterministically.
- New engine views: `redflags`, `health`, `compare`.
- Power tools: `screen` (safe `field op value` rule language), `watchlist`, `export`.
- PyPI packaging: `scripts/` installs as the importable `finance_skills` package
  with a `finance-skills` console entry point; first release on PyPI.

## [0.2.1] - and earlier

- Verb-first CLI over the shared engine; segment-aware Rule of 40; DCF; EV/EBITDA;
  fail-closed net-debt handling; offline fixtures and tests. See the git history.

[Unreleased]: https://github.com/notEhEnG/finance-skills/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/notEhEnG/finance-skills/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/notEhEnG/finance-skills/releases/tag/v0.3.0
[0.2.1]: https://github.com/notEhEnG/finance-skills/releases/tag/v0.2.1
