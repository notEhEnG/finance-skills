"""Pure financial metrics — the analysis engine.

Every function here is deterministic and takes plain numbers in, returning
plain numbers/dicts out. There is NO network or yfinance dependency in this
module, so it is fully unit-testable offline. `data.py` is the IO shell that
feeds these functions; `analyze.py` orchestrates them into a report.

The headline capability is a *segment-aware* Rule of 40: instead of a single
40% threshold, it classifies a company's growth regime, computes Rule 40 under
both EBITDA and FCF margins, exposes the broader EBITDA-to-FCF gap between them,
and compares against a stage/sector project heuristic. This is what separates a
CoreWeave/Nebius-style neocloud from a mature SaaS name.

All margins and growth rates are expressed in PERCENT (e.g. 40.0 == 40%).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# --- Growth regimes -------------------------------------------------------

# Regimes describe the growth/capital bucket, not the literal business model —
# a hardware or consumer name can be "steady" without being SaaS.
REGIME_TRADITIONAL = "steady"
REGIME_HYPERGROWTH = "hypergrowth"
REGIME_NEOCLOUD = "ai_neocloud"
REGIME_EARLY = "early_stage"

# Project screening heuristics (percent), not cited market medians or peer
# percentiles. Expose that status in every report so agents cannot present these
# constants as empirical benchmarks.
STAGE_BENCHMARKS = {
    "early_stage": 18.0,
    "growth_stage": 35.0,
    "mature": 42.0,
}

SECTOR_BENCHMARKS = {
    "ai_ml_saas": 38.0,
    "devtools": 34.0,
    "cybersecurity": 21.0,
    "fintech": 22.0,
    "saas_general": 28.0,
}


def classify_regime(revenue_growth: float, capex_intensity: float, revenue: float | None = None) -> str:
    """Classify a company's growth regime from a few signals.

    - revenue_growth: YoY revenue growth, percent.
    - capex_intensity: capex / revenue, percent.
    - revenue: absolute revenue (USD), optional; distinguishes early-stage.
    """
    # >100% growth AND heavy capex => AI neocloud/hyperscaler bucket.
    if revenue_growth > 100 and capex_intensity > 30:
        return REGIME_NEOCLOUD
    if revenue_growth > 100:
        return REGIME_HYPERGROWTH
    if revenue is not None and revenue < 1_000_000:
        return REGIME_EARLY
    return REGIME_TRADITIONAL


def rule40(growth: float, margin: float) -> float:
    """The raw Rule of 40: growth% + margin%."""
    return round(growth + margin, 1)


@dataclass
class Rule40Report:
    regime: str
    revenue_growth: float
    ebitda_margin: float
    fcf_margin: float
    capex_intensity: float | None
    score_ebitda: float          # growth + EBITDA margin
    score_fcf: float             # growth + FCF margin (the honest one)
    capital_intensity_gap: float  # EBITDA-to-FCF gap; broader than capex alone
    capex_adjusted_score: float | None  # EBITDA Rule-40 minus capex intensity proxy
    dilution_adjusted_score: float | None  # FCF Rule-40 minus share dilution
    preferred_score: float       # the score to actually judge on, per regime
    benchmark: float             # project-authored stage/sector Rule 40 bar
    benchmark_kind: str          # project_heuristic (not a market percentile)
    passes: bool                 # preferred_score >= benchmark
    verdict: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def rule40_report(
    revenue_growth: float,
    ebitda_margin: float,
    fcf_margin: float,
    capex_intensity: float | None = None,
    share_dilution: float | None = None,
    revenue: float | None = None,
    stage: str | None = None,
    sector_key: str | None = None,
) -> Rule40Report:
    """Full segment-aware Rule of 40.

    - share_dilution: YoY growth in diluted share count, percent (penalises
      revenue that was 'bought' with equity).
    - stage: one of STAGE_BENCHMARKS keys; if None, inferred from regime.
    - sector_key: one of SECTOR_BENCHMARKS keys; overrides the stage heuristic.
    """
    regime = classify_regime(
        revenue_growth,
        capex_intensity if capex_intensity is not None else 0.0,
        revenue,
    )

    score_ebitda = rule40(revenue_growth, ebitda_margin)
    score_fcf = rule40(revenue_growth, fcf_margin)
    gap = round(score_ebitda - score_fcf, 1)
    # FCF already includes capex. Subtracting capex intensity from the FCF score
    # would therefore count the same capital spending twice. Keep an explicitly
    # labelled EBITDA-minus-capex proxy for visibility, while the FCF score is the
    # cash-economics measure used for the verdict.
    capex_adjusted = (
        round(score_ebitda - capex_intensity, 1)
        if capex_intensity is not None else None
    )
    dilution_adjusted = (
        round(score_fcf - share_dilution, 1)
        if share_dilution is not None else None
    )

    notes: list[str] = []
    if capex_intensity is None:
        notes.append("Capex intensity unavailable; no capex-adjusted score was computed.")
    if share_dilution is None:
        notes.append("Comparable share-count periods unavailable; no dilution adjustment was computed.")

    # Which score is the fair one to judge on?
    if regime == REGIME_NEOCLOUD:
        # EBITDA can flatter a buildout. FCF already captures capex, working
        # capital, cash taxes and interest, so do not deduct capex a second time.
        preferred = score_fcf
        notes.append(
            "Neocloud regime: the EBITDA-based score can overstate health; judging on "
            "the FCF-based score, which already includes GPU capital spending."
        )
        if gap > 50:
            notes.append(
                f"Large EBITDA-to-FCF gap ({gap:.0f} pts) — capex is important, but "
                "working capital, cash taxes and interest may also contribute."
            )
    elif regime in (REGIME_HYPERGROWTH, REGIME_EARLY):
        preferred = score_fcf
        notes.append("Early/hypergrowth: deep-negative FCF is expected; treat the bar as a floor, not a target.")
    else:
        preferred = score_fcf
        notes.append("Standard regime: FCF-based Rule 40 captures real unit economics better than EBITDA.")

    # Pick the project heuristic.
    if sector_key and sector_key in SECTOR_BENCHMARKS:
        benchmark = SECTOR_BENCHMARKS[sector_key]
    elif stage and stage in STAGE_BENCHMARKS:
        benchmark = STAGE_BENCHMARKS[stage]
    else:
        benchmark = {
            REGIME_EARLY: STAGE_BENCHMARKS["early_stage"],
            REGIME_HYPERGROWTH: STAGE_BENCHMARKS["growth_stage"],
            REGIME_NEOCLOUD: STAGE_BENCHMARKS["growth_stage"],
            REGIME_TRADITIONAL: STAGE_BENCHMARKS["mature"],
        }[regime]

    passes = preferred >= benchmark
    if regime == REGIME_NEOCLOUD:
        # Triple-digit growth can overwhelm even a deeply negative FCF margin in
        # the arithmetic. Do not award a green pass to a cash-consuming buildout.
        passes = passes and fcf_margin >= 0
    verdict = _rule40_verdict(regime, preferred, benchmark, gap, fcf_margin)

    return Rule40Report(
        regime=regime,
        revenue_growth=round(revenue_growth, 1),
        ebitda_margin=round(ebitda_margin, 1),
        fcf_margin=round(fcf_margin, 1),
        capex_intensity=(round(capex_intensity, 1) if capex_intensity is not None else None),
        score_ebitda=score_ebitda,
        score_fcf=score_fcf,
        capital_intensity_gap=gap,
        capex_adjusted_score=capex_adjusted,
        dilution_adjusted_score=dilution_adjusted,
        preferred_score=preferred,
        benchmark=benchmark,
        benchmark_kind="project_heuristic",
        passes=passes,
        verdict=verdict,
        notes=notes,
    )


def _rule40_verdict(
    regime: str,
    preferred: float,
    benchmark: float,
    gap: float,
    fcf_margin: float,
) -> str:
    delta = preferred - benchmark
    if regime == REGIME_NEOCLOUD:
        if fcf_margin < 0:
            return "Cash-consuming growth: FCF margin is negative despite the growth score; watch backlog/RPO and funding runway."
        return "Neocloud clearing its FCF-based bar; verify with backlog, utilization and margin guidance."
    if delta >= 10:
        return "Strong: comfortably above the project Rule of 40 heuristic."
    if delta >= 0:
        return "Healthy: meeting the project Rule of 40 heuristic."
    if delta >= -10:
        return "Below bar: acceptable for the stage but trending needs to improve."
    return "Weak: materially below the project Rule of 40 heuristic."


# --- Valuation ------------------------------------------------------------

def dcf_intrinsic_value(
    fcf: float,
    growth_rate: float,
    *,
    discount_rate: float,
    terminal_growth: float,
    years: int,
    net_debt: float,
    shares_outstanding: float | None = None,
) -> dict:
    """Two-stage DCF with caller-supplied assumptions and equity bridge.

    Rates are percentages. No discount, terminal, horizon, or net-debt default is
    supplied: callers must choose and disclose each assumption explicitly.
    """
    if fcf <= 0:
        raise ValueError("fcf must be positive")
    if years <= 0:
        raise ValueError("years must be positive")
    if shares_outstanding is not None and shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive when supplied")
    if growth_rate <= -100 or terminal_growth <= -100:
        raise ValueError("growth rates must be greater than -100%")
    if discount_rate <= terminal_growth:
        raise ValueError("discount_rate must exceed terminal_growth for a finite terminal value")

    g = growth_rate / 100.0
    r = discount_rate / 100.0
    tg = terminal_growth / 100.0

    pv_sum = 0.0
    projected = fcf
    for year in range(1, years + 1):
        projected = projected * (1 + g)
        pv_sum += projected / ((1 + r) ** year)

    terminal_value = projected * (1 + tg) / (r - tg)
    pv_terminal = terminal_value / ((1 + r) ** years)

    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - net_debt
    per_share = (equity_value / shares_outstanding) if shares_outstanding else None

    return {
        "enterprise_value": round(enterprise_value, 2),
        "equity_value": round(equity_value, 2),
        "per_share": round(per_share, 2) if per_share is not None else None,
        "assumptions": {
            "growth_rate": growth_rate,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
            "years": years,
        },
    }


def dcf_scenarios(
    fcf: float,
    base_growth: float,
    shares_outstanding: float,
    net_debt: float,
    *,
    discount_rate: float,
    terminal_growth: float,
    years: int,
    price: float | None = None,
) -> dict:
    """Bear/base/bull + discount-rate and FCF-conversion sensitivities.

    Pure helper with explicit assumptions. Growth rates are percent; FCF
    conversion multiplies the starting FCF (0.8 / 1.0 / 1.2) without inventing a
    new cash line.
    """
    # Growth scenarios around the base (clamped so bear stays non-absurd).
    bear_g = max(base_growth - 10.0, min(base_growth * 0.5, base_growth - 3.0))
    bull_g = min(base_growth + 10.0, 35.0)
    # If base is already capped near 25, keep bull from exploding past 35.

    def run(g: float, r: float, fcf_mult: float = 1.0) -> dict:
        res = dcf_intrinsic_value(
            fcf=fcf * fcf_mult,
            growth_rate=g,
            discount_rate=r,
            terminal_growth=terminal_growth,
            years=years,
            shares_outstanding=shares_outstanding,
            net_debt=net_debt,
        )
        ps = res["per_share"]
        vs_price = None
        if ps is not None and price is not None and price > 0:
            vs_price = round((ps / price - 1.0) * 100.0, 1)
        return {
            "per_share": ps,
            "growth_rate": g,
            "discount_rate": r,
            "fcf_mult": fcf_mult,
            "vs_price_pct": vs_price,
        }

    growth_table = {
        "bear": run(round(bear_g, 1), discount_rate),
        "base": run(base_growth, discount_rate),
        "bull": run(round(bull_g, 1), discount_rate),
    }
    discount_table = {
        f"r={r:g}%": run(base_growth, float(r))
        for r in (8.0, 10.0, 12.0)
    }
    fcf_table = {
        f"fcf×{m:g}": run(base_growth, discount_rate, fcf_mult=m)
        for m in (0.8, 1.0, 1.2)
    }
    return {
        "growth": growth_table,
        "discount_rate": discount_table,
        "fcf_conversion": fcf_table,
        "base_assumptions": {
            "fcf": fcf,
            "base_growth": base_growth,
            "discount_rate": discount_rate,
            "terminal_growth": terminal_growth,
            "years": years,
            "net_debt": net_debt,
            "shares_outstanding": shares_outstanding,
            "price": price,
        },
    }


# --- Financial health -----------------------------------------------------

def altman_z(
    working_capital: float,
    retained_earnings: float,
    ebit: float,
    market_value_equity: float,
    total_liabilities: float,
    sales: float,
    total_assets: float,
) -> dict:
    """Altman Z-Score for public manufacturers. >2.99 safe, 1.81-2.99 grey, <1.81 distress."""
    if total_assets <= 0:
        raise ValueError("total_assets must be positive")
    a = working_capital / total_assets
    b = retained_earnings / total_assets
    c = ebit / total_assets
    d = market_value_equity / total_liabilities if total_liabilities else 0.0
    e = sales / total_assets
    z = 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e
    zone = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"
    return {"z_score": round(z, 2), "zone": zone}


def piotroski_f_score(signals: dict) -> dict:
    """Piotroski F-Score (0-9) from 9 boolean fundamental signals.

    Expected keys (bool): positive_net_income, positive_operating_cf,
    roa_improved, cfo_gt_net_income, lower_leverage, higher_current_ratio,
    no_new_shares, higher_gross_margin, higher_asset_turnover.
    Missing keys count as False.
    """
    keys = [
        "positive_net_income", "positive_operating_cf", "roa_improved",
        "cfo_gt_net_income", "lower_leverage", "higher_current_ratio",
        "no_new_shares", "higher_gross_margin", "higher_asset_turnover",
    ]
    score = sum(1 for k in keys if signals.get(k))
    strength = "strong" if score >= 7 else "moderate" if score >= 4 else "weak"
    return {"f_score": score, "max": 9, "strength": strength}


def safe_margin(numerator: float | None, denominator: float | None) -> float | None:
    """Percent margin with divide-by-zero / None guarding (returns None if not computable)."""
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100.0, 1)


def enterprise_value(market_cap: float | None, net_debt: float | None) -> float | None:
    """Enterprise value = market cap + net debt, or None if either is unknown.

    net_debt=None yields None (fail closed, like Fundamentals.net_debt) — imputing
    0 would fabricate a concrete EV from incomplete data."""
    if market_cap is None or net_debt is None:
        return None
    return market_cap + net_debt


def _ev_multiple(market_cap: float | None, net_debt: float | None,
                 denominator: float | None) -> float | None:
    """EV / <denominator> multiple, or None if not meaningfully computable.

    None when EV can't be formed (see enterprise_value). A None, zero, or negative
    denominator also yields None — the multiple is meaningless there, so say n/a
    rather than print a nonsense number. Shared by ev_ebitda and ev_sales so the
    guard can't drift between the two."""
    ev = enterprise_value(market_cap, net_debt)
    if ev is None or denominator in (None, 0) or denominator < 0:
        return None
    return round(ev / denominator, 1)


def ev_ebitda(market_cap: float | None, net_debt: float | None, ebitda: float | None) -> float | None:
    """Enterprise-value / EBITDA multiple, or None if not meaningfully computable."""
    return _ev_multiple(market_cap, net_debt, ebitda)


def ev_sales(market_cap: float | None, net_debt: float | None, revenue: float | None) -> float | None:
    """Enterprise-value / sales multiple, or None if not computable. Useful when a
    DCF is unavailable (negative FCF) and EV/EBITDA is distorted."""
    return _ev_multiple(market_cap, net_debt, revenue)


def yoy_growth(current: float | None, prior: float | None) -> float | None:
    """YoY growth percent with guards. Prior must be positive to be meaningful."""
    if current is None or prior in (None, 0) or prior < 0:
        return None
    return round((current - prior) / prior * 100.0, 1)
