"""Pure financial metrics — the analysis engine.

Every function here is deterministic and takes plain numbers in, returning
plain numbers/dicts out. There is NO network or yfinance dependency in this
module, so it is fully unit-testable offline. `data.py` is the IO shell that
feeds these functions; `analyze.py` orchestrates them into a report.

The headline capability is a *segment-aware* Rule of 40: instead of a single
40% threshold, it classifies a company's growth regime, computes Rule 40 under
both EBITDA and FCF margins, exposes the "capital-intensity gap" between them,
and compares against a stage/sector-matched benchmark. This is what separates a
CoreWeave/Nebius-style neocloud from a mature SaaS name.

All margins and growth rates are expressed in PERCENT (e.g. 40.0 == 40%).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

# --- Growth regimes -------------------------------------------------------

# Regimes describe the growth/capital bucket, not the literal business model —
# a hardware or consumer name can be "steady" without being SaaS.
REGIME_TRADITIONAL = "steady"
REGIME_HYPERGROWTH = "hypergrowth"
REGIME_NEOCLOUD = "ai_neocloud"
REGIME_EARLY = "early_stage"

# Stage/sector-matched Rule 40 bars (percent), from the 2026 medians in the
# planning notes. Used for peer context, not as a pass/fail cutoff.
STAGE_BENCHMARKS = {
    "early_stage": 18.0,       # sub-$1M ARR, deep negative FCF expected
    "growth_stage": 35.0,      # $10M-$100M ARR, 31-38% band midpoint
    "mature": 42.0,            # $100M+ ARR, top-quartile public SaaS
}

SECTOR_BENCHMARKS = {
    "ai_ml_saas": 38.0,
    "devtools": 34.0,
    "cybersecurity": 21.0,
    "fintech": 22.0,
    "saas_median": 28.0,       # 2026 B2B SaaS median (FCF-based)
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
    capex_intensity: float
    score_ebitda: float          # growth + EBITDA margin
    score_fcf: float             # growth + FCF margin (the honest one)
    capital_intensity_gap: float  # score_ebitda - score_fcf
    capex_adjusted_score: float  # score_fcf - capex_intensity ("true burn")
    dilution_adjusted_score: float  # capex_adjusted - share dilution
    preferred_score: float       # the score to actually judge on, per regime
    benchmark: float             # stage/sector-matched Rule 40 bar
    passes: bool                 # preferred_score >= benchmark
    verdict: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def rule40_report(
    revenue_growth: float,
    ebitda_margin: float,
    fcf_margin: float,
    capex_intensity: float = 0.0,
    share_dilution: float = 0.0,
    revenue: float | None = None,
    stage: str | None = None,
    sector_key: str | None = None,
) -> Rule40Report:
    """Full segment-aware Rule of 40.

    - share_dilution: YoY growth in diluted share count, percent (penalises
      revenue that was 'bought' with equity).
    - stage: one of STAGE_BENCHMARKS keys; if None, inferred from regime.
    - sector_key: one of SECTOR_BENCHMARKS keys; overrides stage benchmark.
    """
    regime = classify_regime(revenue_growth, capex_intensity, revenue)

    score_ebitda = rule40(revenue_growth, ebitda_margin)
    score_fcf = rule40(revenue_growth, fcf_margin)
    gap = round(score_ebitda - score_fcf, 1)
    capex_adjusted = round(score_fcf - capex_intensity, 1)
    dilution_adjusted = round(capex_adjusted - share_dilution, 1)

    notes: list[str] = []

    # Which score is the fair one to judge on?
    if regime == REGIME_NEOCLOUD:
        # EBITDA score is wildly inflated; judge on the capex-adjusted burn.
        preferred = capex_adjusted
        notes.append(
            "Neocloud regime: the EBITDA-based score overstates health; judging on the "
            "capex-adjusted FCF score to reflect real GPU capital burn."
        )
        if gap > 50:
            notes.append(
                f"Large capital-intensity gap ({gap:.0f} pts) — growth is capex-funded, not organically profitable."
            )
    elif regime in (REGIME_HYPERGROWTH, REGIME_EARLY):
        preferred = score_fcf
        notes.append("Early/hypergrowth: deep-negative FCF is expected; treat the bar as a floor, not a target.")
    else:
        preferred = score_fcf
        notes.append("Standard regime: FCF-based Rule 40 captures real unit economics better than EBITDA.")

    # Pick a benchmark.
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
    verdict = _rule40_verdict(regime, preferred, benchmark, gap)

    return Rule40Report(
        regime=regime,
        revenue_growth=round(revenue_growth, 1),
        ebitda_margin=round(ebitda_margin, 1),
        fcf_margin=round(fcf_margin, 1),
        capex_intensity=round(capex_intensity, 1),
        score_ebitda=score_ebitda,
        score_fcf=score_fcf,
        capital_intensity_gap=gap,
        capex_adjusted_score=capex_adjusted,
        dilution_adjusted_score=dilution_adjusted,
        preferred_score=preferred,
        benchmark=benchmark,
        passes=passes,
        verdict=verdict,
        notes=notes,
    )


def _rule40_verdict(regime: str, preferred: float, benchmark: float, gap: float) -> str:
    delta = preferred - benchmark
    if regime == REGIME_NEOCLOUD:
        if preferred < 0:
            return "Capital-intensive: growth is burning cash faster than it earns; watch backlog/RPO and funding runway."
        return "Neocloud clearing its capex-adjusted bar — unusually efficient for the regime; verify with backlog and margin guidance."
    if delta >= 10:
        return "Strong: comfortably above its stage/sector Rule 40 bar."
    if delta >= 0:
        return "Healthy: meeting its stage/sector Rule 40 bar."
    if delta >= -10:
        return "Below bar: acceptable for the stage but trending needs to improve."
    return "Weak: materially below its stage/sector Rule 40 bar."


# --- Valuation ------------------------------------------------------------

def dcf_intrinsic_value(
    fcf: float,
    growth_rate: float,
    discount_rate: float = 10.0,
    terminal_growth: float = 3.0,
    years: int = 10,
    shares_outstanding: float | None = None,
    net_debt: float = 0.0,
) -> dict:
    """A simple two-stage DCF. Rates in percent. Returns enterprise & per-share value.

    Guards against the classic bug where terminal_growth >= discount_rate makes
    the Gordon terminal value explode/negative.
    """
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


def yoy_growth(current: float | None, prior: float | None) -> float | None:
    """YoY growth percent with guards. Prior must be positive to be meaningful."""
    if current is None or prior in (None, 0) or prior < 0:
        return None
    return round((current - prior) / prior * 100.0, 1)
