from typing import Optional
import pandas as pd
import yfinance as yf

from .config import DEFAULT_START_DATE, today_str


def get_price_data(
    ticker: str,
    start: str = DEFAULT_START_DATE,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Download daily OHLCV data from Yahoo Finance.

    Always hits Yahoo so you always get the latest data.
    """
    if end is None:
        end = today_str()

    data = yf.download(ticker, start=start, end=end)
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")

    # Keep a simple, clean DataFrame
    df = data[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index.name = "Date"
    return df
