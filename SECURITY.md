# Security Policy

## Threat model & safety guarantees

`finance-skills` is **read-only market research**. The guarantees below are
*architectural* and enforced on the AST by `tests/test_safety.py`, so they fail
the build rather than relying on prose:

- **It never trades.** No brokerage or trading SDK (Alpaca, IBKR, ccxt, …) is
  imported by any module, and there is no order/withdraw code path. The test
  fails the build on any broker-SDK import.
- **One network boundary.** All outbound I/O lives in `scripts/data.py` (a
  read-only `yfinance` fetch). No other module may import a networking client
  (`requests`, `httpx`, `aiohttp`, `urllib3`, `yfinance`) — checked per module.
- **No dynamic execution or shell-out.** No `eval`/`exec`, no `subprocess`
  import, and no `os.system` anywhere — the escape hatches a keyword scan misses.
- **The math engine is pure and offline.** Importing `scripts/metrics.py` pulls
  in no network client; it is deterministic and unit-tested from fixtures.
- **Untrusted input is parsed, not evaluated.** The `screen` rule language is a
  tiny hand-written parser (`field op value`) that validates the whole rule up
  front; adversarial inputs (e.g. `__import__('os')`) raise, covered by tests.
- **The one write surface is traversal-guarded.** A ticker is interpolated into a
  cache filename, so it's untrusted input. It's validated against a strict symbol
  pattern (`_normalize_ticker`) and the cache path is refused if it would resolve
  outside the cache directory — so `../evil` can't escape. Regression-tested.
- **No secrets.** The package reads public market data only; it stores no
  credentials and writes only local files (a 6h cache and optional watchlists).

These checks are a real boundary, not a vocabulary filter: analysis text may say
"withdraw" or "brokerage" freely — the invariant is on imports and calls, not
words. They don't prove the *upstream data* (yfinance) is correct; always verify
against primary filings.

`finance-skills` is **not investment advice**. Verify every figure against
primary filings before acting.

## Supported versions

The latest released version on PyPI is supported. Please upgrade before reporting.

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
("Report a vulnerability" on the repository's **Security** tab) rather than a
public issue. We aim to acknowledge within 7 days. Include a minimal repro and
the version (`pip show finance-skills`).
