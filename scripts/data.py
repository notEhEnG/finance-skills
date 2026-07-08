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
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6h; fundamentals change slowly


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
        if self.total_debt is None and self.total_cash is None:
            return None
        return (self.total_debt or 0.0) - (self.total_cash or 0.0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker.upper()}.json"


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
    ticker = ticker.strip().upper()

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
        ebitda=205_000_000,                                 # ~13% EBITDA margin
        free_cash_flow=-7_300_000_000, capex=8_000_000_000,
        net_income=-400_000_000, total_debt=2_000_000_000, total_cash=3_000_000_000,
        shares_outstanding=235_000_000, shares_prior=210_000_000,
    ),
}


def load_fixture(ticker: str) -> Fundamentals | None:
    """Return a synthetic sample record for offline demos/tests, or None."""
    return _FIXTURES.get(ticker.strip().upper())


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
