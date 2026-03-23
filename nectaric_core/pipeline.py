import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.ensemble import RandomForestClassifier


# ---------------------------------------------------------------------
# 1. Data loading
# ---------------------------------------------------------------------


def load_price_data(ticker: str, start: str = "2015-01-01") -> pd.DataFrame:
    """
    Download daily OHLCV data from Yahoo Finance.

    Returns a DataFrame indexed by Date with at least:
    [Open, High, Low, Close, Volume]
    """
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data downloaded for {ticker}.")
    df.index.name = "Date"
    return df


# ---------------------------------------------------------------------
# 2. Feature engineering
# ---------------------------------------------------------------------


def build_ml_dataset(
    data: pd.DataFrame,
    horizon: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, list[str]]:
    """
    From raw OHLCV data build an ML-ready dataset for a
    'will the price be higher in N days?' classification.

    Features include moving averages, volatility, momentum, etc.
    Label = 1 if future return over `horizon` days > 0, else 0.
    """
    # Work on a copy
    df = data.copy()

    # 🔹 1) If yfinance returned a MultiIndex like ('Close','NVDA'),
    #      flatten it to simple names: 'Close', 'High', etc.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    # --- Price and simple return ---
    df["Price"] = df["Close"]
    df["Return"] = df["Price"].pct_change()

    # --- Moving averages ---
    df["MA20"] = df["Price"].rolling(window=20).mean()
    df["MA50"] = df["Price"].rolling(window=50).mean()
    df["MA200"] = df["Price"].rolling(window=200).mean()

    # --- Volatility (rolling std of daily returns) ---
    df["Volatility20"] = df["Return"].rolling(window=20).std()
    df["Volatility60"] = df["Return"].rolling(window=60).std()

    # --- Momentum: how much did price move over the last `horizon` days ---
    df["Mom10"] = df["Price"].pct_change(periods=horizon)

    # --- Relative position vs moving averages ---
    df["Price_over_MA20"] = df["Price"] / df["MA20"] - 1
    df["Price_over_MA50"] = df["Price"] / df["MA50"] - 1

    # --- Slope of MA20 over the last 5 days (simple trend indicator) ---
    df["MA20_slope5"] = df["MA20"].diff(periods=5)

    # --- Forward-looking label: 1 if price is higher in `horizon` days ---
    df["Future_Return"] = df["Price"].shift(-horizon) / df["Price"] - 1
    df["Label"] = (df["Future_Return"] > 0).astype(int)

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

    # Now these columns definitely exist, but we still remove NaN rows
    df = df.dropna(subset=features + ["Label"])

    X = df[features]
    y = df["Label"]

    return df, X, y, features


# ---------------------------------------------------------------------
# 3. Model training & backtest
# ---------------------------------------------------------------------


def train_model(X_train: pd.DataFrame, y_train: pd.Series) -> RandomForestClassifier:
    """
    Train a simple Random Forest classifier.
    """
    clf = RandomForestClassifier(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=50,
        class_weight="balanced",
        random_state=42,
    )
    clf.fit(X_train, y_train)
    return clf


def backtest_ml_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a DataFrame with columns:
        - Return (daily returns)
        - Proba (probability of positive N-day move)
        - ML_Signal (1 = buy, -1 = sell, 0 = flat)
    build a simple long-only equity curve.

    Logic:
        - Start flat (position = 0)
        - If ML_Signal == 1 and currently flat -> BUY (position = 1)
        - If ML_Signal == -1 and currently long -> SELL (position = 0)
        - Otherwise keep previous position
    """
    position = 0
    positions: list[int] = []

    for _, row in df.iterrows():
        sig = row["ML_Signal"]

        if sig == 1 and position == 0:
            position = 1
        elif sig == -1 and position == 1:
            position = 0

        positions.append(position)

    df = df.copy()
    df["Position"] = positions
    df["Strategy_Return"] = df["Position"].shift(1).fillna(0) * df["Return"]
    df["Equity"] = (1 + df["Strategy_Return"]).cumprod()

    # Simple buy-and-hold for comparison
    df["BuyHold"] = df["Price"] / df["Price"].iloc[0]

    return df


def performance_summary(strategy_returns: pd.Series) -> dict:
    """
    Compute annualised return, Sharpe ratio and cumulative return
    for a stream of daily strategy returns.
    """
    strategy_returns = strategy_returns.dropna()
    if strategy_returns.empty:
        return {"annual_return": 0.0, "sharpe": 0.0, "cum_return": 0.0}

    cumulative_return = (1 + strategy_returns).prod() - 1
    n_days = len(strategy_returns)
    annual_return = (1 + cumulative_return) ** (252 / n_days) - 1

    mean = strategy_returns.mean()
    std = strategy_returns.std()
    sharpe = float(mean / std * np.sqrt(252)) if std > 0 else 0.0

    return {
        "annual_return": float(annual_return),
        "sharpe": float(sharpe),
        "cum_return": float(cumulative_return * 100),  # in %
    }


def classify_decision(row: pd.Series) -> str:
    """
    Turn the last row's ML_Signal and Position into a plain-English action.
    """
    signal = row["ML_Signal"]
    position = row.get("Position", 0)

    if signal == 1 and position == 0:
        return "BUY"
    if signal == -1 and position == 1:
        return "SELL"
    if position == 1:
        return "HOLD"
    return "NO POSITION"


# ---------------------------------------------------------------------
# 4. Public helpers used by the API
# ---------------------------------------------------------------------


def run_pipeline_for_ticker(
    ticker: str,
    start: str = "2015-01-01",
    horizon: int = 10,
    buy_thresh: float = 0.6,
    sell_thresh: float = 0.4,
) -> dict:
    """
    End-to-end pipeline used by the API.

    Steps:
        * download data
        * build features / labels for `horizon`-day move
        * train RandomForest on first 70% of history
        * get probabilities on full history
        * convert probabilities -> ML_Signal using thresholds
        * backtest the strategy
        * return today's decision and performance stats
    """
    # 1. Load raw price data
    raw = load_price_data(ticker, start=start)

    # 2. Build ML dataset
    ml_df, X, y, features = build_ml_dataset(raw, horizon=horizon)

    if len(ml_df) < 300:
        raise ValueError(f"Not enough data for {ticker} after feature engineering.")

    # 3. Chronological train/test split (no shuffling!)
    split_point = int(len(X) * 0.7)
    X_train, y_train = X.iloc[:split_point], y.iloc[:split_point]

    # 4. Train model
    model = train_model(X_train, y_train)

    # 5. Predict probability of 'up' on the full set
    proba_up = model.predict_proba(X)[:, 1]
    ml_df = ml_df.copy()
    ml_df["Proba"] = proba_up

    # 6. Convert probabilities to trading signals
    ml_df["ML_Signal"] = 0
    ml_df.loc[ml_df["Proba"] >= buy_thresh, "ML_Signal"] = 1
    ml_df.loc[ml_df["Proba"] <= sell_thresh, "ML_Signal"] = -1

    # 7. Backtest
    bt_df = backtest_ml_signals(ml_df)
    perf = performance_summary(bt_df["Strategy_Return"])

    # 8. Today's row and decision
    today_row = bt_df.iloc[-1]
    decision = classify_decision(today_row)
    price_today = float(today_row["Price"])
    proba_today = float(today_row["Proba"])

    # 9. What actually happened over the LAST 10 days (for context only)
    if len(bt_df) > 10:
        price_10d_ago = bt_df["Price"].iloc[-11]
        last_10d_actual = float(price_today / price_10d_ago - 1)
    else:
        last_10d_actual = None

    return {
        "ticker": ticker,
        "decision_today": decision,
        "price_today": price_today,
        "proba_pos_move": proba_today,
        "last_10d_actual": last_10d_actual,
        "annual_return": perf["annual_return"],
        "sharpe": perf["sharpe"],
        "cum_return": perf["cum_return"],
    }


def run_compare_for_tickers(
    tickers: list[str],
    start: str = "2015-01-01",
    horizon: int = 10,
    buy_thresh: float = 0.6,
    sell_thresh: float = 0.4,
) -> list[dict]:
    """
    Run the full pipeline for several tickers and return a list
    of summary dicts – one per ticker.
    """
    results: list[dict] = []
    for t in tickers:
        try:
            out = run_pipeline_for_ticker(
                ticker=t,
                start=start,
                horizon=horizon,
                buy_thresh=buy_thresh,
                sell_thresh=sell_thresh,
            )
            results.append(out)
        except Exception as exc:  # we don't want one ticker to kill the whole call
            results.append(
                {
                    "ticker": t,
                    "error": str(exc),
                }
            )
    return results
