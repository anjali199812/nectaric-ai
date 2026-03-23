# nectaric_core/valuation.py

from typing import Dict, Any
import math
import yfinance as yf


def _safe(info: Dict[str, Any], key: str):
    """Helper to pull a value or None if missing/NaN."""
    v = info.get(key)
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    return v


def get_basic_valuation(ticker: str) -> Dict[str, Any]:
    """
    Morningstar-style valuation snapshot for a single ticker.

    Uses yfinance fundamentals and returns:
      - raw ratios
      - a simple cheap/fair/expensive style label
      - a 1–5 'Nectaric score' combining value + quality + leverage
    """
    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}

    pe = _safe(info, "trailingPE")
    ps = _safe(info, "priceToSalesTrailing12Months")
    pb = _safe(info, "priceToBook")
    roe = _safe(info, "returnOnEquity")      # often a fraction (0.33 = 33%)
    debt_to_equity = _safe(info, "debtToEquity")

    # ---- Value block ----
    value_score = 0
    value_label = "unknown"

    if pe is not None:
        if pe < 15:
            value_score += 2
            value_label = "cheap"
        elif pe < 25:
            value_score += 1
            value_label = "fair"
        else:
            value_label = "expensive"

    if pb is not None:
        if pb < 2:
            value_score += 1
        elif pb > 5:
            value_score -= 1

    # ---- Quality block ----
    quality_score = 0
    if roe is not None:
        roe_pct = roe * 100 if roe < 1 else roe
        if roe_pct > 20:
            quality_score += 2
        elif roe_pct > 10:
            quality_score += 1
        else:
            quality_score -= 1

    # ---- Balance sheet (leverage) ----
    balance_score = 0
    if debt_to_equity is not None:
        if debt_to_equity < 50:
            balance_score += 2
        elif debt_to_equity < 100:
            balance_score += 1
        elif debt_to_equity > 200:
            balance_score -= 1

    total = value_score + quality_score + balance_score
    nectaric_score = max(1, min(5, 3 + total // 2))

    status = value_label
    if value_label == "cheap" and quality_score > 0:
        status = "undervalued high-quality"
    elif value_label == "expensive" and quality_score <= 0:
        status = "expensive low-quality"

    return {
        "ticker": ticker.upper(),
        "valuation_status": status,
        "nectaric_score": nectaric_score,
        "raw_ratios": {
            "pe_ttm": pe,
            "ps_ttm": ps,
            "pb_ttm": pb,
            "roe": roe,
            "debt_to_equity": debt_to_equity,
        },
    }
