"""Peer comparison presets — curated ticker sets for common workflows.

Used by `compare --preset=…`. Tickers are starting points, not investment
recommendations; users can still pass explicit tickers for custom sets.
"""

from __future__ import annotations

# Preset name → ordered tickers. Offline demos: only CRWV/NBIS have fixtures;
# live mode fetches the rest via yfinance.
PRESETS: dict[str, list[str]] = {
    "saas": ["CRM", "NOW", "SNOW", "DDOG", "NET", "CRWD"],
    "ai-infra": ["CRWV", "NBIS", "NVDA", "AMD", "AVGO"],
    "ai": ["CRWV", "NBIS", "NVDA", "AMD", "AVGO"],  # alias
    "semiconductor": ["NVDA", "AMD", "AVGO", "MU", "TSM"],
    "semis": ["NVDA", "AMD", "AVGO", "MU", "TSM"],
    "megacap": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
    "megacap-tech": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
}

ALIASES = {
    "ai-infrastructure": "ai-infra",
    "ai_infra": "ai-infra",
    "neocloud": "ai-infra",
    "software": "saas",
    "chips": "semiconductor",
    "semi": "semiconductor",
    "big-tech": "megacap",
    "faang": "megacap",
}


def resolve_preset(name: str) -> tuple[str, list[str]] | None:
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    tickers = PRESETS.get(key)
    if not tickers:
        return None
    # Canonical key for display (collapse aliases)
    canon = key
    for a, t in ALIASES.items():
        if key == a:
            canon = t
            break
    return canon, list(tickers)


def list_presets() -> dict[str, list[str]]:
    """Unique preset bodies (skip pure aliases that share lists)."""
    seen: set[tuple[str, ...]] = set()
    out: dict[str, list[str]] = {}
    for name, tickers in PRESETS.items():
        key = tuple(tickers)
        if key in seen:
            continue
        if name in ("ai", "semis", "megacap-tech"):
            continue  # secondary names
        seen.add(key)
        out[name] = list(tickers)
    return out
