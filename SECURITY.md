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
- **Local writes are non-overwriting.** Cache and watchlist updates create
  append-only snapshots; exports use exclusive creation and refuse an existing
  path; the installer refuses a populated destination. Cache tickers are validated
  against a strict symbol pattern and cannot escape the cache directory.
- **No secrets.** The package reads public market data only; it stores no
  credentials and writes only local cache/watchlist snapshots or explicit exports.

These checks are a real boundary, not a vocabulary filter: analysis text may say
"withdraw" or "brokerage" freely — the invariant is on imports and calls, not
words. They don't prove the *upstream data* (yfinance) is correct; always verify
against primary filings.

`finance-skills` is **not investment advice**. Verify every figure against
primary filings before acting.

## Agent middleware threat model

When used as an AI coding-agent skill, additional risks exist **above** the
Python process:

| Threat | Mitigation |
|--------|------------|
| Agent invents numbers after the engine runs | `SKILL.md` sole-source policy; report `response_guidance.prohibited_claims` |
| Agent gives buy/sell advice | Route `refuse` for personal advice; prohibited conclusion tokens in policy |
| User says “skip tools / answer from knowledge” | Activation policy: still MUST invoke for in-scope company analysis |
| Prompt injection in user text or provider fields | User/provider/error strings are **untrusted data**, never instructions (`SKILL.md`, `docs/agent-policy.md`) |
| Hiding disabled DCF / fixture state | Agent must lead with material disabled/fixture; fixture `data_state` in schema |
| Bypassing deterministic routing | `route_request()` / `route --json` — no LLM in the default path |

Architectural tests cannot force an LLM to obey prose. Agent compliance is
specified in `SKILL.md`; the mocked transcript harness checks hard-fail,
usefulness, and synthesis rules. These deterministic checks are policy lint—not
proof that upstream data or a model's financial judgment is correct.

## Supported versions

The latest released version on PyPI is supported. Please upgrade before reporting.

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
("Report a vulnerability" on the repository's **Security** tab) rather than a
public issue. We aim to acknowledge within 7 days. Include a minimal repro and
the version (`pip show finance-skills`).
