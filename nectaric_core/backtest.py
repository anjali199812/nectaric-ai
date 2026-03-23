from typing import Dict
import pandas as pd
import numpy as np


def backtest_ml_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Turn ML_Signal into a trading position and compute strategy returns.
    """
    df = df.copy()

    position = 0
    positions = []

    for _, row in df.iterrows():
        sig = row["ML_Signal"]
        if sig == 1 and position == 0:
            position = 1
        elif sig == -1 and position == 1:
            position = 0
        positions.append(position)

    df["Position"] = positions
    df["Strategy_Return"] = df["Position"].shift(1) * df["Return"]
    df["Strategy_Return"] = df["Strategy_Return"].fillna(0.0)

    df["Equity"] = (1.0 + df["Strategy_Return"]).cumprod()
    df["BuyHold"] = (1.0 + df["Return"]).cumprod()

    return df


def performance_summary(
    returns: pd.Series,
    freq: int = 252,
) -> Dict[str, float]:
    """
    Simple performance metrics for a series of daily returns.
    """
    returns = returns.dropna()
    if returns.empty:
        return {
            "Annual Return": 0.0,
            "Volatility": 0.0,
            "Sharpe": 0.0,
            "Cumulative Return": 0.0,
            "Max Drawdown": 0.0,
        }

    avg_ret = returns.mean() * freq
    vol = returns.std() * (freq ** 0.5)
    sharpe = avg_ret / vol if vol > 0 else 0.0
    cum_ret = (1.0 + returns).prod() - 1.0

    equity = (1.0 + returns).cumprod()
    roll_max = equity.cummax()
    drawdown = (roll_max - equity) / roll_max
    max_dd = drawdown.max() if not drawdown.empty else 0.0

    return {
        "Annual Return": float(avg_ret),
        "Volatility": float(vol),
        "Sharpe": float(sharpe),
        "Cumulative Return": float(cum_ret),
        "Max Drawdown": float(max_dd),
    }
