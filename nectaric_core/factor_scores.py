# nectaric_core/factor_scores.py

from typing import Dict, Any

# Replace these with the exact values from your stock document
STOCK_SCORE_DB: Dict[str, Dict[str, float]] = {
    "AVGO": {"quality": 9.0, "growth": 8.5, "value": 7.5, "momentum": 8.0, "risk": 8.0},
    "MSFT": {"quality": 9.0, "growth": 8.0, "value": 7.0, "momentum": 7.5, "risk": 8.0},
    "NVDA": {"quality": 9.0, "growth": 9.0, "value": 5.5, "momentum": 8.5, "risk": 6.5},
    "AAPL": {"quality": 8.5, "growth": 6.5, "value": 6.5, "momentum": 7.0, "risk": 8.0},
    "AMZN": {"quality": 7.0, "growth": 7.5, "value": 5.5, "momentum": 6.0, "risk": 5.5},
    "MELI": {"quality": 6.0, "growth": 6.5, "value": 5.5, "momentum": 4.5, "risk": 5.0},
}

WEIGHTS = {
    "quality": 0.30,
    "growth": 0.20,
    "value": 0.20,
    "momentum": 0.20,
    "risk": 0.10,
}


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


def compute_final_score(factors: Dict[str, float]) -> float:
    return round(
        sum(factors[k] * WEIGHTS[k] for k in WEIGHTS),
        2,
    )


def get_factor_snapshot(ticker: str) -> Dict[str, Any]:
    t = ticker.upper()
    if t not in STOCK_SCORE_DB:
        raise ValueError(f"No factor-score data found for {t}")

    factors = STOCK_SCORE_DB[t]
    final_score = compute_final_score(factors)
    conviction = conviction_from_score(final_score)

    best_factor = max(factors, key=factors.get)
    weakest_factor = min(factors, key=factors.get)

    return {
        "ticker": t,
        "final_score": final_score,
        "conviction": conviction,
        "weights": WEIGHTS,
        "factors": factors,
        "best_factor": {"name": best_factor, "score": factors[best_factor]},
        "weakest_factor": {"name": weakest_factor, "score": factors[weakest_factor]},
    }