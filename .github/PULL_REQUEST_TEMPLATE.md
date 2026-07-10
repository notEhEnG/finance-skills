<!-- Thanks for contributing! Keep the engine the single source of truth. -->

## What & why

<!-- What does this change and what investor question does it serve? -->

## Checklist

- [ ] `python -m pytest tests/ -q --cov=scripts` passes (coverage gate included)
- [ ] `python -m ruff check .` and `python -m mypy` are clean
- [ ] Added/updated tests for the change (offline — uses fixtures, no network)
- [ ] New verbs are a **view over `analyze.build_report`** (numbers don't diverge)
- [ ] No fabricated metrics — disclosed KPIs are flagged, not faked
- [ ] Stays read-only (no trading / account access); `test_safety.py` still passes
- [ ] The `python3 scripts/<mod>.py` skill path still works
- [ ] Updated `CHANGELOG.md` under **Unreleased** if user-facing
