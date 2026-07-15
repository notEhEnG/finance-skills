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
from dataclasses import asdict, dataclass, field
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


@dataclass
class Fundamentals:
    ticker: str
    available: bool
    source: str = "yfinance"
    data_state: str = "live"
    as_of: str | None = None
    retrieved_at: str | None = None
    currency: str | None = None
    source_url: str | None = None
    field_metadata: dict[str, dict[str, str | None]] = field(default_factory=dict)
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

    def currencies_align(self, *names: str) -> bool:
        """Whether known currencies agree for fields used in one calculation.

        Legacy records without field-level metadata remain usable, but once the
        provider identifies currencies the engine refuses cross-currency sums.
        """
        currencies = {
            (self.field_metadata.get(name) or {}).get("currency")
            for name in names
            if getattr(self, name, None) is not None
        }
        currencies.discard(None)
        return len(currencies) <= 1

    def periods_align(self, *names: str) -> bool:
        """Whether period-based fields can be used in one calculation.

        Older cache records and hand-built test inputs have no field metadata; in
        that case compatibility is unknown and the existing fail-closed input
        checks remain authoritative. When metadata is present, annual and TTM
        values must not be mixed in the same margin or growth calculation.
        """
        kinds = {
            (self.field_metadata.get(name) or {}).get("period_type")
            for name in names
            if getattr(self, name, None) is not None
        }
        kinds.discard(None)
        comparable = {"annual", "ttm", "spot"}
        relevant = kinds & comparable
        return len(relevant) <= 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_path(ticker: str, snapshot: str | None = None) -> Path:
    # Defense-in-depth: even though callers normalize, refuse any path that would
    # resolve outside CACHE_DIR (a second line against traversal on the write surface).
    suffix = f"-{snapshot}" if snapshot else ""
    path = CACHE_DIR / f"{normalize_ticker(ticker)}{suffix}.json"
    if path.resolve().parent != CACHE_DIR.resolve():
        raise ValueError(f"cache path escapes CACHE_DIR for ticker {ticker!r}")
    return path


def _read_cache(ticker: str) -> Fundamentals | None:
    ticker = normalize_ticker(ticker)
    try:
        legacy = _cache_path(ticker)
        candidates = list(CACHE_DIR.glob(f"{ticker}-*.json"))
        if legacy.is_file():
            candidates.append(legacy)
        for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
            if time.time() - path.stat().st_mtime > CACHE_TTL_SECONDS:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached = Fundamentals(**payload)
            cached.data_state = "cache"
            return cached
    except (OSError, ValueError, TypeError):
        return None
    return None


def _write_cache(f: Fundamentals) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Append-only snapshots: never overwrite a prior observation. The
        # nanosecond suffix also makes concurrent fetches collision-resistant.
        path = _cache_path(f.ticker, str(time.time_ns()))
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(f.to_dict(), indent=2))
    except OSError:
        pass  # caching is best-effort


def _period_label(df, column: int = 0) -> str | None:
    """ISO period end for a statement column, when yfinance supplies one."""
    try:
        if df is None or getattr(df, "empty", True) or df.shape[1] <= column:
            return None
        value = df.columns[column]
        if hasattr(value, "date"):
            return value.date().isoformat()
        return str(value)
    except Exception:
        return None


def _pick_value(
    statement_value: float | None,
    info_value: float | None,
    *,
    statement_name: str,
    statement_period: str | None,
    currency: str | None,
    fallback_period_type: str = "ttm",
) -> tuple[float | None, dict[str, str | None]]:
    """Choose a value without treating a reported zero as missing."""
    if statement_value is not None:
        return statement_value, {
            "source": statement_name,
            "period_end": statement_period,
            "period_type": "annual",
            "currency": currency,
        }
    return info_value, {
        "source": "yfinance.info",
        "period_end": None,
        "period_type": fallback_period_type,
        "currency": currency,
    }


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
        ticker = normalize_ticker(ticker)
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

        currency = info.get("financialCurrency") or info.get("currency")
        income_period = _period_label(income)
        income_prior_period = _period_label(income, 1)
        cash_period = _period_label(cash)
        balance_period = _period_label(balance)

        revenue, revenue_meta = _pick_value(
            _col(income, ["Total Revenue", "TotalRevenue"], 0),
            _num(info.get("totalRevenue")),
            statement_name="income_statement",
            statement_period=income_period,
            currency=currency,
        )
        gross_profit, gross_meta = _pick_value(
            _first(income, ["Gross Profit", "GrossProfit"]),
            _num(info.get("grossProfits")),
            statement_name="income_statement",
            statement_period=income_period,
            currency=currency,
        )
        ebitda, ebitda_meta = _pick_value(
            _first(income, ["EBITDA", "Normalized EBITDA"]),
            _num(info.get("ebitda")),
            statement_name="income_statement",
            statement_period=income_period,
            currency=currency,
        )
        free_cash_flow, fcf_meta = _pick_value(
            _first(cash, ["Free Cash Flow", "FreeCashFlow"]),
            _num(info.get("freeCashflow")),
            statement_name="cash_flow_statement",
            statement_period=cash_period,
            currency=currency,
        )
        net_income, net_income_meta = _pick_value(
            _first(income, ["Net Income", "NetIncome"]),
            _num(info.get("netIncomeToCommon")),
            statement_name="income_statement",
            statement_period=income_period,
            currency=currency,
        )
        total_debt, debt_meta = _pick_value(
            _first(balance, ["Total Debt", "TotalDebt"]),
            _num(info.get("totalDebt")),
            statement_name="balance_sheet",
            statement_period=balance_period,
            currency=currency,
            fallback_period_type="point_in_time",
        )
        total_cash, cash_meta = _pick_value(
            _first(balance, ["Cash And Cash Equivalents"]),
            _num(info.get("totalCash")),
            statement_name="balance_sheet",
            statement_period=balance_period,
            currency=currency,
            fallback_period_type="point_in_time",
        )
        capex_raw = _first(cash, ["Capital Expenditure", "CapitalExpenditures"])
        prior_revenue = _col(income, ["Total Revenue", "TotalRevenue"], 1)
        retrieved_at = _now_iso()
        f = Fundamentals(
            ticker=ticker,
            available=True,
            data_state="live",
            as_of=income_period or cash_period or balance_period,
            retrieved_at=retrieved_at,
            currency=currency,
            source_url=f"https://finance.yahoo.com/quote/{ticker}/financials/",
            name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            price=_num(info.get("currentPrice")) if info.get("currentPrice") is not None else _num(info.get("regularMarketPrice")),
            market_cap=_num(info.get("marketCap")),
            revenue=revenue,
            revenue_prior=prior_revenue,
            gross_profit=gross_profit,
            ebitda=ebitda,
            free_cash_flow=free_cash_flow,
            capex=abs(capex_raw) if capex_raw is not None else None,
            net_income=net_income,
            total_debt=total_debt,
            total_cash=total_cash,
            shares_outstanding=_num(info.get("sharesOutstanding")),
            shares_prior=_col(balance, ["Share Issued", "Ordinary Shares Number"], 1),
            field_metadata={
                "price": {"source": "yfinance.info", "period_end": retrieved_at, "period_type": "spot", "currency": info.get("currency")},
                "market_cap": {"source": "yfinance.info", "period_end": retrieved_at, "period_type": "spot", "currency": info.get("currency")},
                "revenue": revenue_meta,
                "revenue_prior": {"source": "income_statement", "period_end": income_prior_period, "period_type": "annual", "currency": currency},
                "gross_profit": gross_meta,
                "ebitda": ebitda_meta,
                "free_cash_flow": fcf_meta,
                "capex": {"source": "cash_flow_statement", "period_end": cash_period, "period_type": "annual", "currency": currency},
                "net_income": net_income_meta,
                "total_debt": debt_meta,
                "total_cash": cash_meta,
                "shares_outstanding": {"source": "yfinance.info", "period_end": retrieved_at, "period_type": "spot", "currency": "shares"},
                "shares_prior": {"source": "balance_sheet", "period_end": _period_label(balance, 1), "period_type": "annual", "currency": "shares"},
            },
        )

        # Fall back to yfinance's own revenueGrowth (fraction) if we lack a prior year.
        if f.revenue_prior is None and f.revenue is not None:
            rg = info.get("revenueGrowth")
            if isinstance(rg, (int, float)) and rg not in (0, None) and rg > -1:
                f.revenue_prior = f.revenue / (1 + rg)
                f.field_metadata["revenue_prior"] = {
                    "source": "yfinance.info.revenueGrowth",
                    "period_end": None,
                    "period_type": "ttm",
                    "currency": currency,
                }

        if not any(
            value is not None
            for value in (f.price, f.market_cap, f.revenue, f.ebitda, f.free_cash_flow)
        ):
            return Fundamentals(
                ticker=ticker,
                available=False,
                source="yfinance",
                data_state="unavailable",
                retrieved_at=retrieved_at,
                error="yfinance returned no usable market or financial fields",
            )

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
        ticker="CRWV", available=True, source="fixture", data_state="fixture", as_of="2026-Q1",
        currency="USD", source_url=None,
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
        ticker="NBIS", available=True, source="fixture", data_state="fixture", as_of="2026-Q1",
        currency="USD", source_url=None,
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


def list_fixtures() -> list[str]:
    """Tickers that have offline sample records (public; do not import `_FIXTURES`)."""
    return sorted(_FIXTURES)


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
    """Validate ticker, then load explicitly requested fixture or live data."""
    try:
        t = normalize_ticker(ticker)
    except ValueError as exc:
        return Fundamentals(ticker=ticker.strip().upper(), available=False, error=str(exc))
    if use_fixture:
        return load_fixture(t) or Fundamentals(
            ticker=t, available=False, error="no fixture for this ticker"
        )
    return get_fundamentals(t)
