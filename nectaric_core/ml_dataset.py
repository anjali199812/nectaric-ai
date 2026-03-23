from typing import List, Tuple
import pandas as pd

from .features import add_indicators


def build_ml_dataset(
    prices: pd.DataFrame,
    horizon: int = 10,
    threshold: float = 0.05,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, List[str]]:
    """
    Build ML dataset for classification:
    Label = 1 if future return over `horizon` days > `threshold`, else 0.
    """
    df = add_indicators(prices)

    # Future horizon return
    df["Future_Return"] = df["Price"].shift(-horizon) / df["Price"] - 1.0
    df["Label"] = (df["Future_Return"] > threshold).astype(int)

    features = [
        "Return",
        "MA20",
        "MA50",
        "MA200",
        "Volatility20",
        "Volatility60",
        "Mom10",
        "Price_over_MA20",
        "Price_over_MA50",
        "MA20_slope5",
    ]

    df = df.dropna(subset=features + ["Label"])
    X = df[features]
    y = df["Label"]

    return df, X, y, features
