# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Changed
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

[Unreleased]: https://github.com/notEhEnG/finance-skills/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/notEhEnG/finance-skills/releases/tag/v0.3.0
[0.2.1]: https://github.com/notEhEnG/finance-skills/releases/tag/v0.2.1
