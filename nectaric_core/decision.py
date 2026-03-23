from typing import Literal
import pandas as pd


DecisionType = Literal["BUY", "HOLD", "NO POSITION"]


def classify_decision(row: pd.Series) -> DecisionType:
    """
    Classify a single row into BUY / HOLD / NO POSITION
    based on ML_Signal and Position.
    """
    sig = int(row["ML_Signal"])
    pos = int(row.get("Position", 0))

    if sig == 1 and pos == 0:
        return "BUY"
    if sig == -1 and pos == 1:
        return "NO POSITION"  # exit
    if pos == 1:
        return "HOLD"
    return "NO POSITION"


def explain_decision(
    row: pd.Series,
    buy_thresh: float,
    sell_thresh: float,
    horizon: int,
) -> str:
    """
    Human-readable explanation for the decision.
    """
    price = float(row["Price"])
    proba = float(row["Proba"])
    pos = int(row.get("Position", 0))
    sig = int(row["ML_Signal"])

    ma50 = float(row.get("MA50", price))
    ma200 = float(row.get("MA200", price))

    # Trend description
    if price > ma50 > ma200:
        trend = "a strong uptrend"
    elif price < ma50 < ma200:
        trend = "a downtrend"
    else:
        trend = "a mixed / sideways trend"

    if sig == 1 and pos == 0:
        return (
            f"BUY – The model estimates a {proba:.0%} chance of a positive "
            f"{horizon}-day move (above the {buy_thresh:.0%} buy threshold). "
            f"The stock is currently in {trend}, so Nectaric opens a long position."
        )

    if sig == -1 and pos == 1:
        return (
            f"NO POSITION – The model's probability ({proba:.0%}) fell below "
            f"the {sell_thresh:.0%} exit threshold. Even though the trend is {trend}, "
            "Nectaric closes the existing position to manage risk."
        )

    if pos == 1:
        return (
            f"HOLD – The model's probability ({proba:.0%}) remains between the "
            f"buy ({buy_thresh:.0%}) and sell ({sell_thresh:.0%}) thresholds. "
            "Nectaric recommends staying in the current position."
        )

    return (
        "NO POSITION – The model's probability of a positive move "
        f"({proba:.0%}) is below the buy threshold ({buy_thresh:.0%}). "
        f"With the price in {trend}, Nectaric prefers to wait for "
        "a stronger edge before entering."
    )
