import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add price-based indicators: returns, moving averages, volatility, momentum.

    Input: price DataFrame with column 'Close'.
    Output: copy with additional columns.
    """
    df = df.copy()

    df["Price"] = df["Close"]
    df["Return"] = df["Price"].pct_change()

    # Moving averages
    df["MA20"] = df["Price"].rolling(window=20).mean()
    df["MA50"] = df["Price"].rolling(window=50).mean()
    df["MA200"] = df["Price"].rolling(window=200).mean()

    # Volatility (rolling std of returns)
    df["Volatility20"] = df["Return"].rolling(window=20).std()
    df["Volatility60"] = df["Return"].rolling(window=60).std()

    # 10-day momentum
    df["Mom10"] = df["Price"] / df["Price"].shift(10) - 1

    # Price relative to moving averages
    df["Price_over_MA20"] = df["Price"] / df["MA20"] - 1
    df["Price_over_MA50"] = df["Price"] / df["MA50"] - 1

    # Slope of MA20 (5-day change)
    df["MA20_slope5"] = df["MA20"] - df["MA20"].shift(5)

    return df
