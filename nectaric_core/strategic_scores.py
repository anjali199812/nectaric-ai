# nectaric_core/strategic_scores.py

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from nectaric_core.market_providers import FMPClient


STRATEGIC_WEIGHTS = {
    "revenue_linkage": 0.25,
    "infrastructure_utilization": 0.20,
    "platform_control": 0.20,
    "capex_risk": 0.15,
    "strategic_durability": 0.20,
}

# These are BUSINESS-TYPE templates, not ticker hardcoding.
BUSINESS_TYPE_TEMPLATES = {
    "semiconductor": {
        "revenue_linkage": 8.0,
        "platform_control": 5.5,
        "capex_profile": 4.5,
        "moat_strength": 7.5,
    },
    "cloud_platform": {
        "revenue_linkage": 8.0,
        "platform_control": 9.0,
        "capex_profile": 6.0,
        "moat_strength": 9.0,
    },
    "enterprise_software": {
        "revenue_linkage": 7.0,
        "platform_control": 8.0,
        "capex_profile": 8.5,
        "moat_strength": 8.0,
    },
    "consumer_ecosystem": {
        "revenue_linkage": 6.0,
        "platform_control": 9.0,
        "capex_profile": 8.0,
        "moat_strength": 8.5,
    },
    "marketplace_platform": {
        "revenue_linkage": 7.0,
        "platform_control": 8.5,
        "capex_profile": 7.0,
        "moat_strength": 8.0,
    },
    "fintech_platform": {
        "revenue_linkage": 7.0,
        "platform_control": 7.5,
        "capex_profile": 8.0,
        "moat_strength": 7.0,
    },
    "industrial_infrastructure": {
        "revenue_linkage": 6.0,
        "platform_control": 4.5,
        "capex_profile": 4.0,
        "moat_strength": 6.5,
    },
    "capital_intensive_operator": {
        "revenue_linkage": 5.5,
        "platform_control": 4.0,
        "capex_profile": 3.5,
        "moat_strength": 5.5,
    },
    "asset_light_software": {
        "revenue_linkage": 6.5,
        "platform_control": 7.5,
        "capex_profile": 9.0,
        "moat_strength": 7.5,
    },
}


def _safe_num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return float(v)
    except Exception:
        return None


def _pick_first(mapping: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        if key in mapping:
            value = _safe_num(mapping.get(key))
            if value is not None:
                return value
    return None


def _pct_or_number(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100 if abs(value) <= 1.5 else value


def _clamp_0_10(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return max(0.0, min(10.0, float(value)))


def _score_band_higher_better(value: Optional[float], bands: list[tuple[float, float]]) -> Optional[float]:
    if value is None:
        return None
    for threshold, score in bands:
        if value >= threshold:
            return score
    return 0.0


def _score_band_lower_better(value: Optional[float], bands: list[tuple[float, float]]) -> Optional[float]:
    if value is None:
        return None
    for threshold, score in bands:
        if value <= threshold:
            return score
    return 0.0


def _weighted_average(parts: Dict[str, Optional[float]], weights: Dict[str, float]) -> Optional[float]:
    weighted_sum = 0.0
    used_weight = 0.0

    for key, weight in weights.items():
        value = parts.get(key)
        if value is None:
            continue
        weighted_sum += value * weight
        used_weight += weight

    if used_weight == 0:
        return None

    return round(weighted_sum / used_weight, 2)


def classify_business_type(sector: str, industry: str, description: str) -> str:
    text = f"{sector} {industry} {description}".lower()

    if "semiconductor" in text or "chip" in text or "gpu" in text:
        return "semiconductor"

    if "cloud" in text or "infrastructure software" in text or "iaas" in text:
        return "cloud_platform"

    if "enterprise software" in text or ("software" in text and "enterprise" in text):
        return "enterprise_software"

    if (
        "consumer electronics" in text
        or "consumer hardware" in text
        or "smartphone" in text
        or "wearable" in text
        or "ecosystem" in text
    ):
        return "consumer_ecosystem"

    if "marketplace" in text or "e-commerce" in text or "online retail" in text:
        return "marketplace_platform"

    if "fintech" in text or "payments" in text or "payment processing" in text:
        return "fintech_platform"

    if "industrial" in text or "infrastructure" in text or "energy" in text or "utility" in text:
        return "industrial_infrastructure"

    if "airline" in text or "telecom" in text or "railroad" in text or "oil & gas" in text:
        return "capital_intensive_operator"

    return "asset_light_software"


def _get_profile(client: FMPClient, symbol: str) -> Dict[str, Any]:
    """
    Uses the existing FMP client internal caller to fetch profile data.
    """
    try:
        data = client._call("profile", {"symbol": symbol})  # noqa: SLF001
        if isinstance(data, list) and data:
            return data[0]
        return {}
    except Exception:
        return {}


def _extract_metrics(snapshot: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Optional[float]]:
    ratios = snapshot.get("ratios_ttm", {})
    metrics = snapshot.get("key_metrics_ttm", {})
    growth = snapshot.get("income_statement_growth", {})
    scores = snapshot.get("financial_scores", {})
    quote = snapshot.get("quote", {})

    revenue_growth = _pick_first(growth, "growthRevenue", "revenueGrowth", "revenueGrowthTTM")
    operating_margin = _pick_first(
        ratios,
        "operatingProfitMarginTTM",
        "operatingMarginTTM",
        "operatingMargin",
        "operatingProfitMargin",
    )
    gross_margin = _pick_first(
        ratios,
        "grossProfitMarginTTM",
        "grossMarginTTM",
        "grossProfitMargin",
        "grossMargin",
    )
    roe = _pick_first(metrics, "roeTTM", "roe", "returnOnEquityTTM", "returnOnEquity")
    roic = _pick_first(metrics, "roicTTM", "roic", "returnOnInvestedCapital")
    debt_to_equity = _pick_first(
        ratios,
        "debtEquityRatioTTM",
        "debtToEquityTTM",
        "debtToEquity",
        "debtEquityRatio",
    )
    if debt_to_equity is None:
        debt_to_equity = _pick_first(scores, "debtToEquity")

    fcf_yield = _pick_first(
        metrics,
        "freeCashFlowYieldTTM",
        "freeCashFlowYield",
        "fcfYieldTTM",
        "fcfYield",
    )

    market_cap = _safe_num(quote.get("marketCap"))
    if market_cap is None:
        market_cap = _safe_num(profile.get("mktCap"))

    return {
        "revenue_growth_pct": _pct_or_number(revenue_growth),
        "operating_margin_pct": _pct_or_number(operating_margin),
        "gross_margin_pct": _pct_or_number(gross_margin),
        "roe_pct": _pct_or_number(roe),
        "roic_pct": _pct_or_number(roic),
        "debt_to_equity": debt_to_equity,
        "fcf_yield_pct": _pct_or_number(fcf_yield),
        "market_cap": market_cap,
    }


def score_revenue_linkage(metrics: Dict[str, Optional[float]], template: Dict[str, float]) -> tuple[Optional[float], Dict[str, Any]]:
    template_base = _clamp_0_10(template.get("revenue_linkage", 5.0))

    revenue_growth_signal = _score_band_higher_better(
        metrics.get("revenue_growth_pct"),
        [(40, 10), (25, 8), (15, 6), (5, 4), (0, 2)],
    )

    parts = {
        "template_base": template_base,
        "revenue_growth_signal": revenue_growth_signal,
    }
    weights = {
        "template_base": 0.60,
        "revenue_growth_signal": 0.40,
    }

    return _weighted_average(parts, weights), parts


def score_infrastructure_utilization(metrics: Dict[str, Optional[float]]) -> tuple[Optional[float], Dict[str, Any]]:
    margin_realization = _score_band_higher_better(
        metrics.get("operating_margin_pct"),
        [(30, 10), (20, 8), (10, 6), (5, 4), (0, 2)],
    )

    return_efficiency = None
    if metrics.get("roic_pct") is not None:
        return_efficiency = _score_band_higher_better(
            metrics.get("roic_pct"),
            [(25, 10), (18, 8), (12, 6), (6, 4), (0, 2)],
        )
    elif metrics.get("roe_pct") is not None:
        return_efficiency = _score_band_higher_better(
            metrics.get("roe_pct"),
            [(25, 10), (18, 8), (12, 6), (6, 4), (0, 2)],
        )

    growth_support = _score_band_higher_better(
        metrics.get("revenue_growth_pct"),
        [(40, 10), (25, 8), (15, 6), (5, 4), (0, 2)],
    )

    parts = {
        "margin_realization": margin_realization,
        "return_efficiency": return_efficiency,
        "growth_support": growth_support,
    }
    weights = {
        "margin_realization": 0.35,
        "return_efficiency": 0.35,
        "growth_support": 0.30,
    }

    return _weighted_average(parts, weights), parts


def score_platform_control(metrics: Dict[str, Optional[float]], template: Dict[str, float]) -> tuple[Optional[float], Dict[str, Any]]:
    template_platform_control = _clamp_0_10(template.get("platform_control", 5.0))

    pricing_power_proxy = None
    if metrics.get("gross_margin_pct") is not None:
        pricing_power_proxy = _score_band_higher_better(
            metrics.get("gross_margin_pct"),
            [(70, 10), (55, 8), (40, 6), (25, 4), (0, 2)],
        )
    elif metrics.get("operating_margin_pct") is not None:
        pricing_power_proxy = _score_band_higher_better(
            metrics.get("operating_margin_pct"),
            [(30, 10), (20, 8), (10, 6), (5, 4), (0, 2)],
        )

    market_cap = metrics.get("market_cap")
    scale_proxy = None
    if market_cap is not None:
        if market_cap >= 500_000_000_000:
            scale_proxy = 10
        elif market_cap >= 200_000_000_000:
            scale_proxy = 8
        elif market_cap >= 50_000_000_000:
            scale_proxy = 6
        elif market_cap >= 10_000_000_000:
            scale_proxy = 4
        else:
            scale_proxy = 2

    parts = {
        "template_platform_control": template_platform_control,
        "pricing_power_proxy": pricing_power_proxy,
        "scale_proxy": scale_proxy,
    }
    weights = {
        "template_platform_control": 0.50,
        "pricing_power_proxy": 0.30,
        "scale_proxy": 0.20,
    }

    return _weighted_average(parts, weights), parts


def score_capex_risk(metrics: Dict[str, Optional[float]], template: Dict[str, float]) -> tuple[Optional[float], Dict[str, Any]]:
    # Higher score = lower capex risk
    template_capex_profile = _clamp_0_10(template.get("capex_profile", 5.0))

    fcf_support = _score_band_higher_better(
        metrics.get("fcf_yield_pct"),
        [(6, 10), (4, 8), (2, 6), (0, 4), (-5, 2)],
    )

    leverage_support = _score_band_lower_better(
        metrics.get("debt_to_equity"),
        [(20, 10), (50, 8), (100, 6), (150, 4), (250, 2)],
    )

    margin_support = _score_band_higher_better(
        metrics.get("operating_margin_pct"),
        [(30, 10), (20, 8), (10, 6), (5, 4), (0, 2)],
    )

    parts = {
        "fcf_support": fcf_support,
        "leverage_support": leverage_support,
        "margin_support": margin_support,
        "template_capex_profile": template_capex_profile,
    }
    weights = {
        "fcf_support": 0.35,
        "leverage_support": 0.25,
        "margin_support": 0.20,
        "template_capex_profile": 0.20,
    }

    return _weighted_average(parts, weights), parts


def score_strategic_durability(metrics: Dict[str, Optional[float]], template: Dict[str, float]) -> tuple[Optional[float], Dict[str, Any]]:
    template_moat_strength = _clamp_0_10(template.get("moat_strength", 5.0))

    return_stability = None
    if metrics.get("roic_pct") is not None:
        return_stability = _score_band_higher_better(
            metrics.get("roic_pct"),
            [(25, 10), (18, 8), (12, 6), (6, 4), (0, 2)],
        )
    elif metrics.get("roe_pct") is not None:
        return_stability = _score_band_higher_better(
            metrics.get("roe_pct"),
            [(25, 10), (18, 8), (12, 6), (6, 4), (0, 2)],
        )

    margin_stability = _score_band_higher_better(
        metrics.get("operating_margin_pct"),
        [(30, 10), (20, 8), (10, 6), (5, 4), (0, 2)],
    )

    balance_sheet_resilience = _score_band_lower_better(
        metrics.get("debt_to_equity"),
        [(20, 10), (50, 8), (100, 6), (150, 4), (250, 2)],
    )

    parts = {
        "template_moat_strength": template_moat_strength,
        "return_stability": return_stability,
        "margin_stability": margin_stability,
        "balance_sheet_resilience": balance_sheet_resilience,
    }
    weights = {
        "template_moat_strength": 0.35,
        "return_stability": 0.25,
        "margin_stability": 0.20,
        "balance_sheet_resilience": 0.20,
    }

    return _weighted_average(parts, weights), parts


def long_term_label(score: Optional[float]) -> str:
    if score is None:
        return "N/A"
    if score >= 8.0:
        return "Strong long-term candidate"
    if score >= 7.0:
        return "Attractive long-term candidate"
    if score >= 6.0:
        return "Mixed / selective"
    if score >= 5.0:
        return "Speculative"
    return "Weak long-term setup"


def get_strategic_snapshot(
    ticker: str,
    financial_score: Optional[float] = None,
) -> Dict[str, Any]:
    client = FMPClient()
    symbol = ticker.upper()

    snapshot = client.get_fundamental_snapshot(symbol)
    profile = _get_profile(client, symbol)

    sector = str(profile.get("sector") or "")
    industry = str(profile.get("industry") or "")
    description = str(profile.get("description") or profile.get("companyName") or "")
    business_type = classify_business_type(sector, industry, description)
    template = BUSINESS_TYPE_TEMPLATES.get(
        business_type,
        BUSINESS_TYPE_TEMPLATES["asset_light_software"],
    )

    metrics = _extract_metrics(snapshot, profile)

    revenue_linkage_score, revenue_linkage_parts = score_revenue_linkage(metrics, template)
    infrastructure_score, infrastructure_parts = score_infrastructure_utilization(metrics)
    platform_control_score, platform_parts = score_platform_control(metrics, template)
    capex_risk_score, capex_parts = score_capex_risk(metrics, template)
    durability_score, durability_parts = score_strategic_durability(metrics, template)

    strategic_buckets = {
        "revenue_linkage": revenue_linkage_score,
        "infrastructure_utilization": infrastructure_score,
        "platform_control": platform_control_score,
        "capex_risk": capex_risk_score,
        "strategic_durability": durability_score,
    }

    strategic_score = _weighted_average(strategic_buckets, STRATEGIC_WEIGHTS)

    combined_long_term_score = None
    if financial_score is not None and strategic_score is not None:
        combined_long_term_score = round(financial_score * 0.60 + strategic_score * 0.40, 2)

    effective_score = combined_long_term_score if combined_long_term_score is not None else strategic_score

    return {
        "ticker": symbol,
        "business_type": business_type,
        "strategic_score": strategic_score,
        "combined_long_term_score": combined_long_term_score,
        "long_term_label": long_term_label(effective_score),
        "strategic_weights": STRATEGIC_WEIGHTS,
        "template_used": template,
        "profile_context": {
            "sector": sector,
            "industry": industry,
            "company_name": profile.get("companyName"),
        },
        "derived_metrics_used": metrics,
        "strategic_buckets": strategic_buckets,
        "bucket_breakdown": {
            "revenue_linkage": revenue_linkage_parts,
            "infrastructure_utilization": infrastructure_parts,
            "platform_control": platform_parts,
            "capex_risk": capex_parts,
            "strategic_durability": durability_parts,
        },
    }