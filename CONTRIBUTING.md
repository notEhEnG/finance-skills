# Contributing to finance-skills

Thanks for your interest! This project is analyst-style equity research over one
shared engine — contributions that keep the numbers honest and the engine the
single source of truth are very welcome.

## Ground rules

- **Read-only, no trading.** The project never places trades or touches an
  account, and only `scripts/data.py` may reach the network. `tests/test_safety.py`
  enforces this — don't work around it.
- **Never fabricate a metric.** If a number needs a disclosed KPI the financial
  statements don't contain (NRR, Magic Number, backlog/RPO…), flag it as
  "needs disclosed KPI" with its definition. An honest gap beats a fake figure.
- **One engine, many views.** New verbs should be *views* over
  `analyze.build_report`, so numbers never diverge between commands.

## Dev setup

```bash
git clone https://github.com/notEhEnG/finance-skills
cd finance-skills
python -m pip install -e ".[dev]"   # or: pip install pytest pytest-cov ruff mypy
```

## Before you open a PR

Everything CI runs, locally:

```bash
python -m pytest tests/ -q --cov=scripts   # tests + coverage gate (offline)
python -m ruff check .                      # lint
python -m mypy                              # type-check
```

- Tests are **offline** — use `--fixture` and the `_FIXTURES` in `data.py`; never
  add a test that needs the network.
- Add or update tests for any behavior change. New verbs need a `tests/test_<verb>.py`.
- Keep the `python3 scripts/<mod>.py` skill path working (the dual-import shim).
- Follow the existing style; the aligned tables are intentional.

## Scope / where to start

Good first issues are labelled [`good first issue`](https://github.com/notEhEnG/finance-skills/labels/good%20first%20issue).
Bigger ideas (sector references, more frameworks, backlog/RPO ingestion) are in
the README roadmap — open an issue to discuss before large PRs.

By contributing you agree your work is licensed under the project's [MIT License](LICENSE).
