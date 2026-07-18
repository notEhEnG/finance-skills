"""Priority-ordered provider loading and reconciliation for finance workflows."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

if __package__:
    from finance_skills import context
    from finance_skills.data import Fundamentals, load_for_workflow, normalize_ticker
    from finance_skills.evidence import build_evidence_report, normalize_observations
    from finance_skills.providers import (
        EstimatesAdapter,
        InvestorRelationsAdapter,
        ProviderResult,
        SecCompanyFactsAdapter,
        reconcile_observations,
    )
else:
    import context
    from data import Fundamentals, load_for_workflow, normalize_ticker
    from evidence import build_evidence_report, normalize_observations
    from providers import (
        EstimatesAdapter,
        InvestorRelationsAdapter,
        ProviderResult,
        SecCompanyFactsAdapter,
        reconcile_observations,
    )


def _settings(config: dict[str, Any], name: str) -> dict[str, Any]:
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return {}
    settings = providers.get(name)
    return settings if isinstance(settings, dict) else {}


def _result_payload(result: ProviderResult, status: str = "success") -> dict[str, Any]:
    return {"status": status, **result.to_dict()}


def _status_payload(provider: str, status: str, message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": provider,
        "status": status,
        "data_mode": "live",
        "observation_count": 0,
    }
    if message:
        payload["message"] = message
    return payload


def _load_ir(
    root: Path,
    ticker: str,
) -> tuple[ProviderResult | None, dict[str, Any], list[str]]:
    path = context.safe_project_path(
        root,
        f".finance/companies/{ticker}/providers/investor-relations.json",
    )
    if not path.exists():
        return None, _status_payload("investor_relations", "not_configured"), []
    if not path.is_file() or path.is_symlink():
        message = "Investor-relations provider file is not a safe regular file."
        return None, _status_payload("investor_relations", "invalid", message), [message]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("IR provider payload must be an object")
        result = InvestorRelationsAdapter().normalize(ticker, payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        message = f"Investor-relations provider failed: {exc}"
        return None, _status_payload("investor_relations", "provider_error", message), [message]
    return result, _result_payload(result), list(result.warnings)


def _load_sec(
    ticker: str,
    settings: dict[str, Any],
) -> tuple[ProviderResult | None, dict[str, Any], list[str]]:
    if settings.get("enabled", True) is False:
        return None, _status_payload("sec_company_facts", "disabled"), []
    env_name = settings.get("sec_user_agent_env", "FINANCE_SEC_USER_AGENT")
    if not isinstance(env_name, str) or not env_name:
        env_name = "FINANCE_SEC_USER_AGENT"
    user_agent = os.environ.get(env_name, "")
    if not user_agent:
        message = f"SEC filing provider disabled: {env_name} is not set."
        return None, _status_payload("sec_company_facts", "disabled", message), [message]
    configured_ciks = settings.get("cik_by_ticker")
    configured = configured_ciks if isinstance(configured_ciks, dict) else {}
    raw_cik = configured.get(ticker)
    try:
        cik = (
            str(raw_cik)
            if isinstance(raw_cik, (str, int))
            else SecCompanyFactsAdapter.fetch_cik(ticker, user_agent=user_agent)
        )
        payload = SecCompanyFactsAdapter.fetch_company_facts(
            cik,
            user_agent=user_agent,
        )
        result = SecCompanyFactsAdapter().normalize(ticker, payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        message = f"SEC filing provider failed: {exc}"
        return None, _status_payload("sec_company_facts", "provider_error", message), [message]
    return result, _result_payload(result), list(result.warnings)


def _market_result(fundamentals: Fundamentals) -> ProviderResult | None:
    if not fundamentals.available:
        return None
    observations = normalize_observations(fundamentals)
    confidence_statistics = {
        "secondary": sum(
            item.get("status") == "available" for item in observations.values()
        ),
        "missing": sum(item.get("status") == "missing" for item in observations.values()),
    }
    return ProviderResult(
        provider="yfinance",
        data_mode="cached" if fundamentals.data_state == "cache" else "live",
        observations=observations,
        warnings=[],
        confidence_statistics=confidence_statistics,
    )


def _merge_sources(
    sources: list[ProviderResult],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    observations: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for source in sources:
        if not observations:
            observations = {
                concept: dict(observation)
                for concept, observation in source.observations.items()
            }
            continue
        merged = reconcile_observations(observations, source.observations)
        observations = merged["observations"]
        conflicts.extend(merged["conflicts"])
    return observations, conflicts


def _fundamentals_from_observations(
    ticker: str,
    market: Fundamentals,
    observations: dict[str, dict[str, Any]],
    source_count: int,
) -> Fundamentals:
    fundamentals = (
        replace(market)
        if market.available
        else Fundamentals(ticker=ticker, available=bool(observations))
    )
    fundamentals.available = bool(observations)
    fundamentals.source = "reconciled" if source_count > 1 else (
        next(iter(observations.values())).get("source_name", "provider")
        if observations
        else market.source
    )
    fundamentals.field_metadata = dict(fundamentals.field_metadata)
    dataclass_fields = Fundamentals.__dataclass_fields__
    for concept, observation in observations.items():
        if concept not in dataclass_fields or concept in {
            "ticker",
            "available",
            "source",
            "data_state",
            "field_metadata",
            "error",
            "estimates",
        }:
            continue
        value = observation.get("value")
        if isinstance(value, (int, float, bool)):
            setattr(fundamentals, concept, value)
            fundamentals.field_metadata[concept] = {
                "source": str(observation.get("source_name") or "provider"),
                "period_start": observation.get("period_start"),
                "period_end": observation.get("period_end"),
                "period_type": observation.get("period_type"),
                "currency": observation.get("currency"),
            }
    revenue = observations.get("revenue") or {}
    if revenue.get("period_end"):
        fundamentals.as_of = str(revenue["period_end"])
    if revenue.get("currency"):
        fundamentals.currency = str(revenue["currency"])
    retrievals = [
        str(item["retrieved_at"])
        for item in observations.values()
        if item.get("retrieved_at")
    ]
    if retrievals:
        fundamentals.retrieved_at = max(retrievals)
    return fundamentals


def build_reconciled_report(
    ticker: str,
    *,
    use_fixture: bool = False,
    include_estimates: bool = False,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build one Evidence Report from priority-ordered, reconciled providers."""
    normalized_ticker = normalize_ticker(ticker)
    if use_fixture:
        fixture = load_for_workflow(normalized_ticker, use_fixture=True)
        observations = normalize_observations(fixture) if fixture.available else {}
        fixture_provider_results = [
            {
                "provider": "fixture",
                "status": "success" if fixture.available else "provider_error",
                "data_mode": "fixture",
                "observation_count": len(observations),
            }
        ]
        return build_evidence_report(
            fixture,
            provider_results=fixture_provider_results,
        )

    root, config, _ = context.load_project_config(project_root)
    estimates_enabled = include_estimates or _settings(config, "estimates").get(
        "enabled",
        False,
    ) is True
    market_enabled = _settings(config, "market_data").get("enabled", True) is not False
    market = (
        load_for_workflow(
            normalized_ticker,
            include_estimates=estimates_enabled,
        )
        if market_enabled
        else Fundamentals(
            ticker=normalized_ticker,
            available=False,
            source="yfinance",
            data_state="unavailable",
            error="Market-data provider disabled by configuration.",
        )
    )

    provider_results: list[dict[str, Any]] = []
    warnings: list[str] = []
    sources: list[ProviderResult] = []

    sec, sec_status, sec_warnings = _load_sec(
        normalized_ticker,
        _settings(config, "filings"),
    )
    provider_results.append(sec_status)
    warnings.extend(sec_warnings)
    if sec is not None:
        sources.append(sec)

    if _settings(config, "investor_relations").get("enabled", True) is not False:
        ir, ir_status, ir_warnings = _load_ir(root, normalized_ticker)
    else:
        ir, ir_status, ir_warnings = (
            None,
            _status_payload("investor_relations", "disabled"),
            [],
        )
    provider_results.append(ir_status)
    warnings.extend(ir_warnings)
    if ir is not None:
        sources.append(ir)

    market_provider = _market_result(market)
    if market_provider is not None:
        sources.append(market_provider)
        provider_results.append(_result_payload(market_provider))
    else:
        message = market.error or "Market-data provider returned no usable observations."
        provider_results.append(_status_payload("yfinance", "provider_error", message))
        warnings.append(message)

    observations, conflicts = _merge_sources(sources)
    historical_sources = [source for source in sources if source.observations]
    fundamentals = _fundamentals_from_observations(
        normalized_ticker,
        market,
        observations,
        len(historical_sources),
    )

    estimate_observations: dict[str, dict[str, Any]] = {}
    if estimates_enabled:
        estimate_result = EstimatesAdapter().normalize(
            market.estimates,
            currency=market.currency,
            period_end=None,
            retrieved_at=market.retrieved_at,
        )
        estimate_observations = estimate_result.observations
        provider_results.append(_result_payload(estimate_result))
        warnings.extend(estimate_result.warnings)
        if not estimate_observations:
            warnings.append("Explicitly enabled estimates are unavailable.")
    else:
        provider_results.append(_status_payload("market_estimates", "disabled"))

    return build_evidence_report(
        fundamentals,
        observation_overrides=observations,
        provider_results=provider_results,
        reconciliation_conflicts=conflicts,
        extra_warnings=warnings,
        estimate_observations=estimate_observations,
    )
