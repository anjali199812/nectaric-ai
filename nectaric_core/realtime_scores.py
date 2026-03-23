# nectaric_core/realtime_scores.py

from typing import Dict, Any
import math

import numpy as np
import pandas as pd
import yfinance as yf


WEIGHTS = {
    "quality": 0.30,
    "growth": 0.20,
    "value": 0.20,
    "momentum": 0.20,
    "risk": 0.10,
}


def _safe_num(v):
    try:
        if v is None:
            return None
        if isinstance(v, float) and math.isnan(v):
            return None
        return float(v)
    except Exception:
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


def get_price_history(ticker: str, period: str = "2y") -> pd.DataFrame:
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No price data found for {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    return df


def get_info(ticker: str) -> Dict[str, Any]:
    t = yf.Ticker(ticker)
    try:
        return t.info or {}
    except Exception:
        return {}


def score_quality(info: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
    roe = _safe_num(info.get("returnOnEquity"))
    operating_margin = _safe_num(info.get("operatingMargins"))
    profit_margin = _safe_num(info.get("profitMargins"))
    debt_to_equity = _safe_num(info.get("debtToEquity"))

    roe_pct = roe * 100 if roe is not None and roe < 5 else roe
    op_margin_pct = operating_margin * 100 if operating_margin is not None and operating_margin < 5 else operating_margin
    profit_margin_pct = profit_margin * 100 if profit_margin is not None and profit_margin < 5 else profit_margin

    sub_scores = []

    if roe_pct is not None:
        sub_scores.append(scale_score(roe_pct, [
            (25, 10), (20, 9), (15, 8), (10, 7), (5, 5), (0, 3)
        ]))

    if op_margin_pct is not None:
        sub_scores.append(scale_score(op_margin_pct, [
            (30, 10), (20, 8), (10, 6), (5, 4), (0, 2)
        ]))

    if profit_margin_pct is not None:
        sub_scores.append(scale_score(profit_margin_pct, [
            (25, 10), (15, 8), (8, 6), (3, 4), (0, 2)
        ]))

    if debt_to_equity is not None:
        sub_scores.append(scale_reverse_score(debt_to_equity, [
            (20, 10), (50, 8), (100, 6), (150, 4), (250, 2)
        ]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else 0.0

    return score, {
        "roe_pct": roe_pct,
        "operating_margin_pct": op_margin_pct,
        "profit_margin_pct": profit_margin_pct,
        "debt_to_equity": debt_to_equity,
    }


def score_growth(info: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
    revenue_growth = _safe_num(info.get("revenueGrowth"))
    earnings_growth = _safe_num(info.get("earningsGrowth"))

    revenue_growth_pct = revenue_growth * 100 if revenue_growth is not None and revenue_growth < 5 else revenue_growth
    earnings_growth_pct = earnings_growth * 100 if earnings_growth is not None and earnings_growth < 5 else earnings_growth

    sub_scores = []

    if revenue_growth_pct is not None:
        sub_scores.append(scale_score(revenue_growth_pct, [
            (40, 10), (25, 8), (15, 6), (5, 4), (0, 2)
        ]))

    if earnings_growth_pct is not None:
        sub_scores.append(scale_score(earnings_growth_pct, [
            (40, 10), (25, 8), (15, 6), (5, 4), (0, 2)
        ]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else 0.0

    return score, {
        "revenue_growth_pct": revenue_growth_pct,
        "earnings_growth_pct": earnings_growth_pct,
    }


def score_value(info: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
    pe = _safe_num(info.get("trailingPE"))
    pb = _safe_num(info.get("priceToBook"))
    ps = _safe_num(info.get("priceToSalesTrailing12Months"))

    sub_scores = []

    if pe is not None:
        sub_scores.append(scale_reverse_score(pe, [
            (15, 10), (20, 8), (30, 6), (40, 4), (60, 2)
        ]))

    if pb is not None:
        sub_scores.append(scale_reverse_score(pb, [
            (2, 10), (4, 8), (8, 6), (15, 4), (30, 2)
        ]))

    if ps is not None:
        sub_scores.append(scale_reverse_score(ps, [
            (2, 10), (4, 8), (8, 6), (15, 4), (25, 2)
        ]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else 0.0

    return score, {
        "pe_ttm": pe,
        "pb_ttm": pb,
        "ps_ttm": ps,
    }


def score_momentum(price_df: pd.DataFrame) -> tuple[float, Dict[str, Any]]:
    price = price_df["Close"].copy()

    ret_6m = price.iloc[-1] / price.iloc[-126] - 1 if len(price) > 126 else None
    ret_12m = price.iloc[-1] / price.iloc[-252] - 1 if len(price) > 252 else None

    ma50 = price.rolling(50).mean().iloc[-1] if len(price) >= 50 else None
    ma200 = price.rolling(200).mean().iloc[-1] if len(price) >= 200 else None
    last_price = price.iloc[-1]

    sub_scores = []

    if ret_6m is not None:
        sub_scores.append(scale_score(ret_6m * 100, [
            (40, 10), (25, 8), (10, 6), (0, 4), (-10, 2)
        ]))

    if ret_12m is not None:
        sub_scores.append(scale_score(ret_12m * 100, [
            (60, 10), (35, 8), (15, 6), (0, 4), (-10, 2)
        ]))

    if ma50 is not None and ma200 is not None:
        if last_price > ma50 > ma200:
            sub_scores.append(10)
        elif last_price > ma50:
            sub_scores.append(7)
        elif last_price > ma200:
            sub_scores.append(5)
        else:
            sub_scores.append(2)

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else 0.0

    return score, {
        "return_6m": ret_6m,
        "return_12m": ret_12m,
        "ma50": ma50,
        "ma200": ma200,
        "last_price": float(last_price),
    }


def score_risk(price_df: pd.DataFrame, info: Dict[str, Any]) -> tuple[float, Dict[str, Any]]:
    price = price_df["Close"].copy()
    returns = price.pct_change().dropna()

    vol_30d = returns.tail(30).std() * np.sqrt(252) if len(returns) >= 30 else None

    rolling_max = price.cummax()
    drawdown = (price - rolling_max) / rolling_max
    max_dd_1y = drawdown.tail(252).min() if len(drawdown) >= 252 else drawdown.min()

    beta = _safe_num(info.get("beta"))
    debt_to_equity = _safe_num(info.get("debtToEquity"))

    sub_scores = []

    if vol_30d is not None:
        sub_scores.append(scale_reverse_score(vol_30d * 100, [
            (20, 10), (30, 8), (40, 6), (50, 4), (70, 2)
        ]))

    if max_dd_1y is not None:
        sub_scores.append(scale_reverse_score(abs(max_dd_1y) * 100, [
            (15, 10), (25, 8), (35, 6), (50, 4), (70, 2)
        ]))

    if beta is not None:
        sub_scores.append(scale_reverse_score(beta, [
            (0.8, 10), (1.0, 8), (1.2, 6), (1.5, 4), (2.0, 2)
        ]))

    if debt_to_equity is not None:
        sub_scores.append(scale_reverse_score(debt_to_equity, [
            (20, 10), (50, 8), (100, 6), (150, 4), (250, 2)
        ]))

    score = round(float(np.mean(sub_scores)), 2) if sub_scores else 0.0

    return score, {
        "volatility_30d_annualised": vol_30d,
        "max_drawdown_1y": max_dd_1y,
        "beta": beta,
        "debt_to_equity": debt_to_equity,
    }

def classify_risk_level(
    final_score: float,
    quality_score: float,
    risk_score: float,
    value_score: float,
    momentum_score: float,
) -> str:
    """
    Classify the stock into Low / Medium / High risk.
    This is NOT market truth, just a practical rules-based interpretation.
    """

    # Low risk: strong quality + strong risk + decent total score
    if final_score >= 7.5 and quality_score >= 8 and risk_score >= 7:
        return "Low"

    # High risk: weak risk profile or weak total score
    if final_score < 6 or risk_score < 5 or quality_score < 6:
        return "High"

    # Everything in between
    return "Medium"

def build_interpretation_from_factors(
    final_score: float,
    quality_score: float,
    growth_score: float,
    value_score: float,
    momentum_score: float,
    risk_score: float,
    conviction: str | None = None,
) -> str:
    reasons = []
    positives = []
    warnings = []

    # Positives
    if quality_score >= 8:
        positives.append("business quality looks strong")
    elif quality_score >= 6:
        positives.append("business quality looks reasonable")
    else:
        warnings.append("business quality is weak")

    if growth_score >= 8:
        positives.append("growth is very strong")
    elif growth_score >= 6:
        positives.append("growth is moderate")
    elif growth_score > 0:
        warnings.append("growth is not especially strong")

    if value_score >= 8:
        positives.append("valuation looks attractive")
    elif value_score >= 6:
        positives.append("valuation looks acceptable")
    elif value_score > 0:
        warnings.append("valuation looks expensive")

    if momentum_score >= 8:
        positives.append("price momentum is strong")
    elif momentum_score >= 6:
        positives.append("momentum is supportive")
    elif momentum_score > 0:
        warnings.append("momentum is only moderate")

    if risk_score >= 8:
        positives.append("risk profile looks relatively stable")
    elif risk_score >= 6:
        positives.append("risk profile looks manageable")
    elif risk_score > 0:
        warnings.append("risk profile looks elevated")

    # Build sentence 1: overall
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

    # Build sentence 2: positives
    if positives:
        reasons.append("On the positive side, " + ", ".join(positives[:2]) + ".")

    # Build sentence 3: warnings
    if warnings:
        reasons.append("Main concern: " + ", ".join(warnings[:3]) + ".")

    # Optional closing from score band
    if final_score >= 7 and value_score < 5:
        reasons.append("This may be a good business, but not necessarily a good entry price.")
    elif final_score < 6 and quality_score >= 7:
        reasons.append("The company may be decent fundamentally, but the overall setup is not strong enough yet.")
    elif final_score >= 7 and risk_score >= 7:
        reasons.append("It appears more suitable for disciplined, lower-risk consideration.")
    elif final_score < 6 and risk_score < 6:
        reasons.append("This setup does not currently support a conservative buy decision.")

    return " ".join([opening] + reasons)

def classify_buy_safety(
    final_score: float,
    quality_score: float,
    risk_score: float,
    value_score: float,
    conviction: str,
) -> str:
    """
    Safety of buying NOW, not just company quality.
    Uses a mix of factor quality, risk and conviction.
    """

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

def get_realtime_factor_snapshot(ticker: str) -> Dict[str, Any]:
    t = ticker.upper()
    info = get_info(t)
    price_df = get_price_history(t)

    quality_score, quality_metrics = score_quality(info)
    growth_score, growth_metrics = score_growth(info)
    value_score, value_metrics = score_value(info)
    momentum_score, momentum_metrics = score_momentum(price_df)
    risk_score, risk_metrics = score_risk(price_df, info)

    factors = {
        "quality": quality_score,
        "growth": growth_score,
        "value": value_score,
        "momentum": momentum_score,
        "risk": risk_score,
    }

    final_score = round(
        quality_score * WEIGHTS["quality"] +
        growth_score * WEIGHTS["growth"] +
        value_score * WEIGHTS["value"] +
        momentum_score * WEIGHTS["momentum"] +
        risk_score * WEIGHTS["risk"],
        2,
    )

    conviction = conviction_from_score(final_score)

    best_factor = max(factors, key=factors.get)
    weakest_factor = min(factors, key=factors.get)
    
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
    conviction=conviction,
)

    return {
        "ticker": t,
        "final_score": final_score,
        "conviction": conviction,
        "risk_level": risk_level,
        "buy_safety": buy_safety,
          "interpretation": interpretation,
        "weights": WEIGHTS,
        "factors": factors,
        "best_factor": {"name": best_factor, "score": factors[best_factor]},
        "weakest_factor": {"name": weakest_factor, "score": factors[weakest_factor]},
        "raw_metrics": {
            "quality": quality_metrics,
            "growth": growth_metrics,
            "value": value_metrics,
            "momentum": momentum_metrics,
            "risk": risk_metrics,
        },
    }