"""Data layer — the IO shell around yfinance.

This is the ONLY module that touches the network. It normalises whatever
yfinance returns into a flat `Fundamentals` record that the pure engine
(`metrics.py`) can consume. It is built to degrade gracefully:

  * If yfinance is not installed  -> Fundamentals(available=False, ...).
  * If the network is unavailable -> Fundamentals(available=False, ...).
  * If a field is missing         -> that field is None (never crashes).

Live fetching only works where the network and yfinance are available
(Claude Code, not the Claude.ai sandbox). For offline demos and tests, use
`load_fixture(ticker)`, which returns hand-checked sample records.

READ-ONLY: this module never places trades or mutates any account. It only
reads public market data.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6h; fundamentals change slowly

# A ticker is interpolated into a cache filename, so it is untrusted input on the
# one write surface. Constrain it to real symbol characters (letters, digits, and
# the class/exchange separators . _ -) with an alphanumeric first char — no path
# separators, no leading dot. This deletes the path-traversal class at the
# boundary rather than sanitising per call site. BRK.B / RDS.A still pass.
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,15}$")


def normalize_ticker(ticker: str) -> str:
    """Upper-case and validate a ticker, or raise ValueError.

    Public boundary helper — every CLI door should use this (or `load_for_cli`)
    so path-unsafe symbols never reach the cache filename. Callers that must
    never raise (e.g. get_fundamentals) catch ValueError and return unavailable.
    """
    t = ticker.strip().upper()
    if not _TICKER_RE.fullmatch(t):
        raise ValueError(f"invalid ticker: {ticker!r}")
    return t


# Back-compat private alias (tests / older call sites).
_normalize_ticker = normalize_ticker


@dataclass
class Fundamentals:
    ticker: str
    available: bool
    source: str = "yfinance"
    as_of: str | None = None
    error: str | None = None

    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    price: float | None = None
    market_cap: float | None = None

    revenue: float | None = None
    revenue_prior: float | None = None
    gross_profit: float | None = None
    ebitda: float | None = None
    free_cash_flow: float | None = None
    capex: float | None = None            # stored as a positive magnitude
    net_income: float | None = None
    total_debt: float | None = None
    total_cash: float | None = None
    shares_outstanding: float | None = None
    shares_prior: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def net_debt(self) -> float | None:
        """Total debt minus cash, or None unless BOTH sides are known. A missing
        side must not be imputed as 0 — that fabricates a concrete leverage figure
        (and a DCF net-debt input) from incomplete data. `_num` maps genuinely
        missing fields to None, so a real reported 0.0 still computes."""
        if self.total_debt is None or self.total_cash is None:
            return None
        return self.total_debt - self.total_cash


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_path(ticker: str) -> Path:
    # Defense-in-depth: even though callers normalize, refuse any path that would
    # resolve outside CACHE_DIR (a second line against traversal on the write surface).
    path = CACHE_DIR / f"{_normalize_ticker(ticker)}.json"
    if path.resolve().parent != CACHE_DIR.resolve():
        raise ValueError(f"cache path escapes CACHE_DIR for ticker {ticker!r}")
    return path


def _read_cache(ticker: str) -> Fundamentals | None:
    path = _cache_path(ticker)
    try:
        if not path.is_file():
            return None
        if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Fundamentals(**data)
    except (OSError, ValueError, TypeError):
        return None


def _write_cache(f: Fundamentals) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(f.ticker).write_text(json.dumps(f.to_dict(), indent=2), encoding="utf-8")
    except OSError:
        pass  # caching is best-effort


def _order_latest_first(df):
    """Reorder statement columns most-recent-first, tolerant of yfinance changing
    its column order. Statement columns are period-end dates; sort by parsed date
    descending so column 0 is reliably the latest period and column 1 the prior
    year. If the labels aren't all date-like, trust the given order unchanged."""
    try:
        import pandas as pd
        cols = list(df.columns)
        if len(cols) < 2:
            return df
        parsed = [pd.to_datetime(c, errors="coerce") for c in cols]
        if any(pd.isna(p) for p in parsed):
            return df  # non-date labels — don't guess, keep as returned
        order = sorted(range(len(cols)), key=lambda i: parsed[i], reverse=True)
        if order == list(range(len(cols))):
            return df  # already latest-first
        return df.iloc[:, order]
    except Exception:
        return df


def _first(df, keys):
    """Return the most recent value for the first matching row label in a yfinance
    statement DataFrame, or None. Tolerant of label/format variation. Assumes
    columns are latest-first (see `_order_latest_first`)."""
    if df is None:
        return None
    try:
        if getattr(df, "empty", True):
            return None
        index = {str(i).lower(): i for i in df.index}
        for key in keys:
            row = index.get(key.lower())
            if row is not None:
                series = df.loc[row]
                for value in series:  # most recent column first
                    if value is not None and value == value:  # not NaN
                        return float(value)
    except Exception:
        return None
    return None


def _col(df, keys, column=0):
    """Value from a specific column (0=latest, 1=prior year) for a matching row."""
    if df is None:
        return None
    try:
        if getattr(df, "empty", True) or df.shape[1] <= column:
            return None
        index = {str(i).lower(): i for i in df.index}
        for key in keys:
            row = index.get(key.lower())
            if row is not None:
                value = df.loc[row].iloc[column]
                if value is not None and value == value:
                    return float(value)
    except Exception:
        return None
    return None


def get_fundamentals(ticker: str, use_cache: bool = True) -> Fundamentals:
    """Fetch and normalise fundamentals for `ticker`. Never raises."""
    try:
        ticker = _normalize_ticker(ticker)
    except ValueError as exc:
        # Reject before any cache read/write — a malformed ticker must never reach
        # the filesystem path builder (path-traversal guard on the write surface).
        return Fundamentals(ticker=ticker.strip().upper(), available=False, error=str(exc))

    if use_cache:
        cached = _read_cache(ticker)
        if cached is not None:
            return cached

    try:
        import yfinance as yf
    except Exception as exc:  # ImportError or partial install
        return Fundamentals(ticker=ticker, available=False, error=f"yfinance unavailable: {exc}")

    try:
        t = yf.Ticker(ticker)
        info = {}
        try:
            info = t.get_info() if hasattr(t, "get_info") else t.info
        except Exception:
            info = {}

        income = _order_latest_first(_safe_stmt(t, "income_stmt"))
        cash = _order_latest_first(_safe_stmt(t, "cashflow"))
        balance = _order_latest_first(_safe_stmt(t, "balance_sheet"))

        capex_raw = _first(cash, ["Capital Expenditure", "CapitalExpenditures"])
        f = Fundamentals(
            ticker=ticker,
            available=True,
            as_of=_now_iso(),
            name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            price=_num(info.get("currentPrice") or info.get("regularMarketPrice")),
            market_cap=_num(info.get("marketCap")),
            revenue=_col(income, ["Total Revenue", "TotalRevenue"], 0) or _num(info.get("totalRevenue")),
            revenue_prior=_col(income, ["Total Revenue", "TotalRevenue"], 1),
            gross_profit=_first(income, ["Gross Profit", "GrossProfit"]) or _num(info.get("grossProfits")),
            ebitda=_first(income, ["EBITDA", "Normalized EBITDA"]) or _num(info.get("ebitda")),
            free_cash_flow=_first(cash, ["Free Cash Flow", "FreeCashFlow"]) or _num(info.get("freeCashflow")),
            capex=abs(capex_raw) if capex_raw is not None else None,
            net_income=_first(income, ["Net Income", "NetIncome"]) or _num(info.get("netIncomeToCommon")),
            total_debt=_num(info.get("totalDebt")) or _first(balance, ["Total Debt", "TotalDebt"]),
            total_cash=_num(info.get("totalCash")) or _first(balance, ["Cash And Cash Equivalents"]),
            shares_outstanding=_num(info.get("sharesOutstanding")),
            shares_prior=_col(balance, ["Share Issued", "Ordinary Shares Number"], 1),
        )

        # Fall back to yfinance's own revenueGrowth (fraction) if we lack a prior year.
        if f.revenue_prior is None and f.revenue is not None:
            rg = info.get("revenueGrowth")
            if isinstance(rg, (int, float)) and rg not in (0, None) and rg > -1:
                f.revenue_prior = f.revenue / (1 + rg)

        _write_cache(f)
        return f
    except Exception as exc:
        return Fundamentals(ticker=ticker, available=False, error=f"fetch failed: {exc}")


def _safe_stmt(ticker_obj, attr):
    try:
        return getattr(ticker_obj, attr)
    except Exception:
        return None


def _num(value):
    try:
        if value is None:
            return None
        v = float(value)
        return v if v == v else None  # drop NaN
    except (TypeError, ValueError):
        return None


# --- Offline fixtures (for tests and no-network demos) --------------------
# Hand-entered approximations drawn from the planning notes; clearly synthetic
# and labelled as such via source="fixture".

_FIXTURES = {
    "CRWV": Fundamentals(
        ticker="CRWV", available=True, source="fixture", as_of="2026-Q1",
        name="CoreWeave, Inc.", sector="Technology", industry="Information Technology Services",
        price=100.0, market_cap=48_000_000_000,
        revenue=1_900_000_000, revenue_prior=900_000_000,   # ~112% YoY
        gross_profit=1_330_000_000,                         # ~70% gross margin
        ebitda=1_064_000_000,                               # ~56% EBITDA margin
        free_cash_flow=-6_000_000_000, capex=8_800_000_000,  # heavy GPU capex
        net_income=-300_000_000, total_debt=12_900_000_000, total_cash=1_400_000_000,
        shares_outstanding=480_000_000, shares_prior=440_000_000,
    ),
    "NBIS": Fundamentals(
        ticker="NBIS", available=True, source="fixture", as_of="2026-Q1",
        name="Nebius Group N.V.", sector="Technology", industry="Information Technology Services",
        price=45.0, market_cap=10_000_000_000,
        revenue=1_577_000_000, revenue_prior=201_000_000,   # ~684% YoY
        gross_profit=505_000_000,                           # ~32% gross margin
        ebitda=205_000_000,                                 # ~13% EBITDA margin
        free_cash_flow=-7_300_000_000, capex=8_000_000_000,
        net_income=-400_000_000, total_debt=2_000_000_000, total_cash=3_000_000_000,
        shares_outstanding=235_000_000, shares_prior=210_000_000,
    ),
}


def load_fixture(ticker: str) -> Fundamentals | None:
    """Return a synthetic sample record for offline demos/tests, or None."""
    try:
        t = normalize_ticker(ticker)
    except ValueError:
        return None
    return _FIXTURES.get(t)


def get_fundamentals_or_fixture(ticker: str, use_cache: bool = True) -> Fundamentals:
    """Try live data; if unavailable, fall back to a fixture when one exists.
    Lets `analyze` produce a demo report offline without pretending it is live."""
    live = get_fundamentals(ticker, use_cache=use_cache)
    if live.available:
        return live
    fixture = load_fixture(ticker)
    if fixture is not None:
        return fixture
    return live  # unavailable, with its error message intact


def load_for_cli(ticker: str, *, use_fixture: bool = False) -> Fundamentals:
    """Validate ticker then load fixture or live/fixture-fallback. Never raises."""
    try:
        t = normalize_ticker(ticker)
    except ValueError as exc:
        return Fundamentals(ticker=ticker.strip().upper(), available=False, error=str(exc))
    if use_fixture:
        return load_fixture(t) or Fundamentals(
            ticker=t, available=False, error="no fixture for this ticker"
        )
    return get_fundamentals_or_fixture(t)
