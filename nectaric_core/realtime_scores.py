from __future__ import annotations

from typing import Any, Dict, Optional
import math

import numpy as np
import pandas as pd

from nectaric_core.market_providers import FMPClient


WEIGHTS = {
    "quality": 0.30,
    "growth": 0.20,
    "value": 0.20,
    "momentum": 0.20,
    "risk": 0.10,
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


def scale_score(value: float, bands: list[tuple[float, float]]) -> float:
    for threshold, score in bands:
        if value >= threshold:
            return score
    return 0.0


def scale_reverse_score(value: float, bands: list[tuple[float, float]]) -> float:
    for threshold, score in bands:
        if value <= threshold:
            return score
    return 0.0


def conviction_from_score(score: float) -> str:
    if score >= 8.0:
        return "Strong Buy"
    if score >= 7.0:
        return "Buy"
    if score >= 6.0:
        return "Watch"
    if score >= 5.0:
        return "Speculative"
    return "Avoid"


def classify_risk_level(
    final_score: float,
    quality_score: Optional[float],
    risk_score: Optional[float],
    value_score: Optional[float],
    momentum_score: Optional[float],
) -> str:
    quality_score = quality_score if quality_score is not None else 0.0
    risk_score = risk_score if risk_score is not None else 0.0

    if final_score >= 7.5 and quality_score >= 8 and risk_score >= 7:
        return "Low"

    if final_score < 6 or risk_score < 5 or quality_score < 6:
        return "High"

    return "Medium"


def classify_buy_safety(
    final_score: float,
    quality_score: Optional[float],
    risk_score: Optional[float],
    value_score: Optional[float],
    conviction: str,
) -> str:
    quality_score = quality_score if quality_score is not None else 0.0
    risk_score = risk_score if risk_score is not None else 0.0
    value_score = value_score if value_score is not None else 0.0

    if (
        final_score >= 7.5
        and quality_score >= 8
        and risk_score >= 7
        and value_score >= 5
        and conviction in ["Buy", "Strong Buy"]
    ):
        return "Safe"

    if (
        final_score < 6
        or risk_score < 5
        or quality_score < 6
        or conviction in ["Speculative", "Avoid"]
    ):
        return "Unsafe"

    return "Cautious"


def build_interpretation_from_factors(
    final_score: float,
    quality_score: Optional[float],
    growth_score: Optional[float],
    value_score: Optional[float],
    momentum_score: Optional[float],
    risk_score: Optional[float],
) -> str:
    positives = []
    warnings = []
    missing = []

    def _classify_factor(name: str, score: Optional[float], good_label: str, mid_label: str, weak_label: str):
        if score is None:
            missing.append(name)
            return
        if score >= 8:
            positives.append(good_label)
        elif score >= 6:
            positives.append(mid_label)
        elif score > 0:
            warnings.append(weak_label)

    _classify_factor("quality", quality_score, "business quality looks strong", "business quality looks reasonable", "business quality is weak")
    _classify_factor("growth", growth_score, "growth is very strong", "growth is moderate", "growth is not especially strong")
    _classify_factor("value", value_score, "valuation looks attractive", "valuation looks acceptable", "valuation looks expensive")
    _classify_factor("momentum", momentum_score, "price momentum is strong", "momentum is supportive", "momentum is only moderate")
    _classify_factor("risk", risk_score, "risk profile looks relatively stable", "risk profile looks manageable", "risk profile looks elevated")

    if final_score >= 8:
        opening = "Overall, this looks like a strong candidate."
    elif final_score >= 7:
        opening = "Overall, this looks like a fairly solid candidate."
    elif final_score >= 6:
        opening = "Overall, this looks mixed rather than clearly attractive."
    elif final_score >= 5:
        opening = "Overall, this looks speculative rather than strong."
    else:
        opening = "Overall, this looks weak on the current factor model."

    parts = [opening]

    if positives:
        parts.append("On the positive side, " + ", ".join(positives[:2]) + ".")
    if warnings:
        parts.append("Main concern: " + ", ".join(warnings[:3]) + ".")
    if missing:
        parts.append("Some factors are unavailable from the data provider and were excluded from the score: " + ", ".join(missing) + ".")

    if final_score >= 7 and (value_score is not None and value_score < 5):
        parts.append("This may be a good business, but not necessarily a good entry price.")
    elif final_score < 6 and (quality_score is not None and quality_score >= 7):
        parts.append("The company may be decent fundamentally, but the overall setup is not strong enough yet.")
    elif final_score >= 7 and (risk_score is not None and risk_score >= 7):
        parts.append("It appears more suitable for disciplined, lower-risk consideration.")
    elif final_score < 6 and (risk_score is not None and risk_score < 6):
        parts.append("This setup does not currently support a conservative buy decision.")

    return " ".join(parts)


def _pct_or_number(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value * 100 if abs(value) <= 1.5 else value


def score_quality(snapshot: Dict[str, Any]) -> tuple[Optional[float], Dict[str, Any]]:
    ratios = snapshot.get("ratios_ttm", {})
    metrics = snapshot.get("key_metrics_ttm", {})
    scores = snapshot.get("financial_scores", {})

    roe = _pick_first(
        metrics,
        "roeTTM", "roe", "returnOnEquityTTM", "returnOnEquity",
    )
    operating_margin = _pick_first(
        ratios,
        "operatingProfitMarginTTM", "operatingMarginTTM", "operatingMargin", "operatingProfitMargin",
    )
    profit_margin = _pick_first(
        ratios,
        "netProfitMarginTTM", "netMarginTTM", "netProfitMargin", "netMargin",
    )
    debt_to_equity = _pick_first(
        ratios,
        "debtEquityRatioTTM", "debtToEquityTTM", "debtToEquity", "debtEquityRatio",
    )
    if debt_to_equity is None:
        debt_to_equity = _pick_first(scores, "debtToEquity")

    roe_pct = _pct_or_number(roe)
    op_margin_pct = _pct_or_number(operating_margin)
    profit_margin_pct = _pct_or_number(profit_margin)

    sub_scores = []

    if roe_pct is not None:
        sub_scores.append(scale_score(roe_pct, [(25, 10), (20, 9), (15, 8), (10, 7), (5, 5), (0, 3)]))
    if op_margin_pct is not None:
        sub_scores.append(scale_score(op_margin_pct, [(30, 10), (20, 8), (10, 6), (5, 4), (0, 2)]))
    if profit_margin_pct is not None:
        sub_scores.append(scale_score(profit_margin_pct, [(25, 10), (15, 8), (8, 6), (3, 4), (0, 2)]))
    if debt_to_equity is not None:
        sub_scores.append(scale_reverse_score(debt_to_equity, [(20, 10), (50, 8), (100, 6), (150, 4), (250, 2)]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else None
    return score, {
        "roe_pct": roe_pct,
        "operating_margin_pct": op_margin_pct,
        "profit_margin_pct": profit_margin_pct,
        "debt_to_equity": debt_to_equity,
    }


def score_growth(snapshot: Dict[str, Any]) -> tuple[Optional[float], Dict[str, Any]]:
    growth = snapshot.get("income_statement_growth", {})
    quote = snapshot.get("quote", {})

    revenue_growth = _pick_first(
        growth,
        "growthRevenue", "revenueGrowth", "revenueGrowthTTM",
    )
    earnings_growth = _pick_first(
        growth,
        "growthNetIncome", "growthEPS", "epsgrowth", "earningsGrowth",
    )

    # optional soft fallback from quote provider if exposed there
    if revenue_growth is None:
        revenue_growth = _pick_first(quote, "revenueGrowth")
    if earnings_growth is None:
        earnings_growth = _pick_first(quote, "earningsGrowth", "epsGrowth")

    revenue_growth_pct = _pct_or_number(revenue_growth)
    earnings_growth_pct = _pct_or_number(earnings_growth)

    sub_scores = []

    if revenue_growth_pct is not None:
        sub_scores.append(scale_score(revenue_growth_pct, [(40, 10), (25, 8), (15, 6), (5, 4), (0, 2)]))
    if earnings_growth_pct is not None:
        sub_scores.append(scale_score(earnings_growth_pct, [(40, 10), (25, 8), (15, 6), (5, 4), (0, 2)]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else None
    return score, {
        "revenue_growth_pct": revenue_growth_pct,
        "earnings_growth_pct": earnings_growth_pct,
    }


def score_value(snapshot: Dict[str, Any]) -> tuple[Optional[float], Dict[str, Any]]:
    ratios = snapshot.get("ratios_ttm", {})
    metrics = snapshot.get("key_metrics_ttm", {})
    quote = snapshot.get("quote", {})

    pe = _pick_first(
        ratios,
        "peRatioTTM", "priceEarningsRatioTTM", "peRatio", "priceToEarningsRatio",
    )
    if pe is None:
        pe = _pick_first(quote, "pe", "peRatio")

    pb = _pick_first(
        ratios,
        "priceToBookRatioTTM", "pbRatioTTM", "pbRatio", "priceToBookRatio",
    )
    if pb is None:
        pb = _pick_first(metrics, "pbRatioTTM", "pbRatio")
    if pb is None:
        pb = _pick_first(quote, "priceToBookRatio")

    ps = _pick_first(
        ratios,
        "priceToSalesRatioTTM", "psRatioTTM", "priceToSalesRatio", "psRatio",
    )
    if ps is None:
        ps = _pick_first(metrics, "psRatioTTM", "psRatio")
    if ps is None:
        ps = _pick_first(quote, "priceToSalesRatio")

    sub_scores = []

    if pe is not None:
        sub_scores.append(scale_reverse_score(pe, [(15, 10), (20, 8), (30, 6), (40, 4), (60, 2)]))
    if pb is not None:
        sub_scores.append(scale_reverse_score(pb, [(2, 10), (4, 8), (8, 6), (15, 4), (30, 2)]))
    if ps is not None:
        sub_scores.append(scale_reverse_score(ps, [(2, 10), (4, 8), (8, 6), (15, 4), (25, 2)]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else None
    return score, {
        "pe_ttm": pe,
        "pb_ttm": pb,
        "ps_ttm": ps,
    }


def score_momentum(price_df: pd.DataFrame) -> tuple[Optional[float], Dict[str, Any]]:
    price = price_df["Close"].astype(float).copy()

    ret_6m = price.iloc[-1] / price.iloc[-126] - 1 if len(price) > 126 else None
    ret_12m = price.iloc[-1] / price.iloc[-252] - 1 if len(price) > 252 else None

    ma50 = price.rolling(50).mean().iloc[-1] if len(price) >= 50 else None
    ma200 = price.rolling(200).mean().iloc[-1] if len(price) >= 200 else None
    last_price = float(price.iloc[-1])

    sub_scores = []

    if ret_6m is not None:
        sub_scores.append(scale_score(ret_6m * 100, [(40, 10), (25, 8), (10, 6), (0, 4), (-10, 2)]))
    if ret_12m is not None:
        sub_scores.append(scale_score(ret_12m * 100, [(60, 10), (35, 8), (15, 6), (0, 4), (-10, 2)]))

    if ma50 is not None and ma200 is not None:
        if last_price > ma50 > ma200:
            sub_scores.append(10)
        elif last_price > ma50:
            sub_scores.append(7)
        elif last_price > ma200:
            sub_scores.append(5)
        else:
            sub_scores.append(2)

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else None
    return score, {
        "return_6m": ret_6m,
        "return_12m": ret_12m,
        "ma50": float(ma50) if ma50 is not None else None,
        "ma200": float(ma200) if ma200 is not None else None,
        "last_price": last_price,
    }


def score_risk(price_df: pd.DataFrame, snapshot: Dict[str, Any]) -> tuple[Optional[float], Dict[str, Any]]:
    price = price_df["Close"].astype(float).copy()
    returns = price.pct_change().dropna()

    vol_30d = returns.tail(30).std() * np.sqrt(252) if len(returns) >= 30 else None

    rolling_max = price.cummax()
    drawdown = (price - rolling_max) / rolling_max
    max_dd_1y = drawdown.tail(252).min() if len(drawdown) >= 252 else drawdown.min()

    quote = snapshot.get("quote", {})
    ratios = snapshot.get("ratios_ttm", {})
    scores = snapshot.get("financial_scores", {})

    beta = _pick_first(quote, "beta")
    debt_to_equity = _pick_first(
        ratios,
        "debtEquityRatioTTM", "debtToEquityTTM", "debtToEquity", "debtEquityRatio",
    )
    if debt_to_equity is None:
        debt_to_equity = _pick_first(scores, "debtToEquity")

    sub_scores = []

    if vol_30d is not None:
        sub_scores.append(scale_reverse_score(vol_30d * 100, [(20, 10), (30, 8), (40, 6), (50, 4), (70, 2)]))
    if max_dd_1y is not None:
        sub_scores.append(scale_reverse_score(abs(max_dd_1y) * 100, [(15, 10), (25, 8), (35, 6), (50, 4), (70, 2)]))
    if beta is not None:
        sub_scores.append(scale_reverse_score(beta, [(0.8, 10), (1.0, 8), (1.2, 6), (1.5, 4), (2.0, 2)]))
    if debt_to_equity is not None:
        sub_scores.append(scale_reverse_score(debt_to_equity, [(20, 10), (50, 8), (100, 6), (150, 4), (250, 2)]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else None
    return score, {
        "volatility_30d_annualised": float(vol_30d) if vol_30d is not None else None,
        "max_drawdown_1y": float(max_dd_1y) if max_dd_1y is not None else None,
        "beta": beta,
        "debt_to_equity": debt_to_equity,
    }


def _weighted_average_from_available(factors: Dict[str, Optional[float]]) -> float:
    weighted_sum = 0.0
    used_weight = 0.0

    for key, weight in WEIGHTS.items():
        value = factors.get(key)
        if value is None:
            continue
        weighted_sum += value * weight
        used_weight += weight

    if used_weight == 0:
        return 0.0

    return round(weighted_sum / used_weight, 2)


def get_realtime_factor_snapshot(ticker: str) -> Dict[str, Any]:
    client = FMPClient()
    symbol = ticker.upper()

    snapshot = client.get_fundamental_snapshot(symbol)
    price_df = client.get_historical_eod(symbol)

    quality_score, quality_metrics = score_quality(snapshot)
    growth_score, growth_metrics = score_growth(snapshot)
    value_score, value_metrics = score_value(snapshot)
    momentum_score, momentum_metrics = score_momentum(price_df)
    risk_score, risk_metrics = score_risk(price_df, snapshot)

    factors = {
        "quality": quality_score,
        "growth": growth_score,
        "value": value_score,
        "momentum": momentum_score,
        "risk": risk_score,
    }

    final_score = _weighted_average_from_available(factors)
    conviction = conviction_from_score(final_score)

    risk_level = classify_risk_level(
        final_score=final_score,
        quality_score=quality_score,
        risk_score=risk_score,
        value_score=value_score,
        momentum_score=momentum_score,
    )

    buy_safety = classify_buy_safety(
        final_score=final_score,
        quality_score=quality_score,
        risk_score=risk_score,
        value_score=value_score,
        conviction=conviction,
    )

    interpretation = build_interpretation_from_factors(
        final_score=final_score,
        quality_score=quality_score,
        growth_score=growth_score,
        value_score=value_score,
        momentum_score=momentum_score,
        risk_score=risk_score,
    )

    available_factors = {k: v for k, v in factors.items() if v is not None}
    if available_factors:
        best_factor = max(available_factors, key=available_factors.get)
        weakest_factor = min(available_factors, key=available_factors.get)
        best_factor_payload = {"name": best_factor, "score": available_factors[best_factor]}
        weakest_factor_payload = {"name": weakest_factor, "score": available_factors[weakest_factor]}
    else:
        best_factor_payload = {"name": None, "score": None}
        weakest_factor_payload = {"name": None, "score": None}

    return {
        "ticker": symbol,
        "final_score": final_score,
        "conviction": conviction,
        "risk_level": risk_level,
        "buy_safety": buy_safety,
        "interpretation": interpretation,
        "weights": WEIGHTS,
        "factors": factors,
        "best_factor": best_factor_payload,
        "weakest_factor": weakest_factor_payload,
        "raw_metrics": {
            "quality": quality_metrics,
            "growth": growth_metrics,
            "value": value_metrics,
            "momentum": momentum_metrics,
            "risk": risk_metrics,
        },
    }
