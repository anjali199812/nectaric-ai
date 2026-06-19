import numpy as np
import pandas as pd
import yfinance as yf

from sklearn.ensemble import RandomForestClassifier


# ---------------------------------------------------------------------------
# 1. Data loading
# ---------------------------------------------------------------------------

def load_price_data(ticker: str, start: str = "2015-01-01") -> pd.DataFrame:
    df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data downloaded for {ticker}.")
    df.index.name = "Date"
    return df


# ---------------------------------------------------------------------------
# 2. Feature engineering
# ---------------------------------------------------------------------------

def build_ml_dataset(
    data: pd.DataFrame,
    horizon: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, list[str]]:
    df = data.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    df["Price"]           = df["Close"]
    df["Return"]          = df["Price"].pct_change()
    df["MA20"]            = df["Price"].rolling(window=20).mean()
    df["MA50"]            = df["Price"].rolling(window=50).mean()
    df["MA200"]           = df["Price"].rolling(window=200).mean()
    df["Volatility20"]    = df["Return"].rolling(window=20).std()
    df["Volatility60"]    = df["Return"].rolling(window=60).std()
    df["Mom10"]           = df["Price"].pct_change(periods=horizon)
    df["Price_over_MA20"] = df["Price"] / df["MA20"] - 1
    df["Price_over_MA50"] = df["Price"] / df["MA50"] - 1
    df["MA20_slope5"]     = df["MA20"].diff(periods=5)

    df["Future_Return"] = df["Price"].shift(-horizon) / df["Price"] - 1
    df["Label"]         = (df["Future_Return"] > 0).astype(int)

    features = [
        "Return", "MA20", "MA50", "MA200",
        "Volatility20", "Volatility60", "Mom10",
        "Price_over_MA20", "Price_over_MA50", "MA20_slope5",
    ]

    df = df.dropna(subset=features + ["Label"])
    X  = df[features]
    y  = df["Label"]

    return df, X, y, features


# ---------------------------------------------------------------------------
# 3. Model training and backtest
# ---------------------------------------------------------------------------

def train_model(X_train: pd.DataFrame, y_train: pd.Series) -> RandomForestClassifier:
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
    df["Position"]        = positions
    df["Strategy_Return"] = df["Position"].shift(1).fillna(0) * df["Return"]
    df["Equity"]          = (1 + df["Strategy_Return"]).cumprod()
    df["BuyHold"]         = df["Price"] / df["Price"].iloc[0]
    return df


def performance_summary(strategy_returns: pd.Series) -> dict:
    strategy_returns = strategy_returns.dropna()
    if strategy_returns.empty:
        return {"annual_return": 0.0, "sharpe": 0.0, "cum_return": 0.0}

    cumulative_return = (1 + strategy_returns).prod() - 1
    n_days            = len(strategy_returns)
    annual_return     = (1 + cumulative_return) ** (252 / n_days) - 1

    mean   = strategy_returns.mean()
    std    = strategy_returns.std()
    sharpe = float(mean / std * np.sqrt(252)) if std > 0 else 0.0

    return {
        "annual_return": float(annual_return),
        "sharpe":        float(sharpe),
        "cum_return":    float(cumulative_return * 100),
    }


def classify_decision(row: pd.Series) -> str:
    signal   = row["ML_Signal"]
    position = row.get("Position", 0)

    if signal == 1 and position == 0:
        return "BUY"
    if signal == -1 and position == 1:
        return "SELL"
    if position == 1:
        return "HOLD"
    return "NO POSITION"


# ---------------------------------------------------------------------------
# 4. ATR helper
# ---------------------------------------------------------------------------

def compute_atr(raw: pd.DataFrame, period: int = 14) -> float:
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    high       = df["High"]
    low        = df["Low"]
    prev_close = df["Close"].shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr_series = tr.rolling(window=period).mean().dropna()
    return float(atr_series.iloc[-1]) if not atr_series.empty else 0.0


# ---------------------------------------------------------------------------
# 5. Internal runner (accepts pre-loaded data, avoids double download)
# ---------------------------------------------------------------------------

def _run_pipeline_on_raw(
    raw:         pd.DataFrame,
    horizon:     int,
    buy_thresh:  float,
    sell_thresh: float,
    ticker:      str = "",
) -> dict:
    ml_df, X, y, features = build_ml_dataset(raw, horizon=horizon)

    if len(ml_df) < 300:
        raise ValueError(f"Not enough data for {ticker} after feature engineering.")

    split_point      = int(len(X) * 0.7)
    X_train, y_train = X.iloc[:split_point], y.iloc[:split_point]

    model    = train_model(X_train, y_train)
    proba_up = model.predict_proba(X)[:, 1]

    ml_df              = ml_df.copy()
    ml_df["Proba"]     = proba_up
    ml_df["ML_Signal"] = 0
    ml_df.loc[ml_df["Proba"] >= buy_thresh,  "ML_Signal"] =  1
    ml_df.loc[ml_df["Proba"] <= sell_thresh, "ML_Signal"] = -1

    bt_df = backtest_ml_signals(ml_df)
    perf  = performance_summary(bt_df["Strategy_Return"])

    today_row   = bt_df.iloc[-1]
    decision    = classify_decision(today_row)
    price_today = float(today_row["Price"])
    proba_today = float(today_row["Proba"])

    last_10d_actual = None
    if len(bt_df) > 10:
        price_10d_ago   = bt_df["Price"].iloc[-11]
        last_10d_actual = float(price_today / price_10d_ago - 1)

    return {
        "decision":        decision,
        "price_today":     price_today,
        "proba_today":     proba_today,
        "last_10d_actual": last_10d_actual,
        "annual_return":   perf["annual_return"],
        "sharpe":          perf["sharpe"],
        "cum_return":      perf["cum_return"],
    }


# ---------------------------------------------------------------------------
# 6. Trade signal calculator
# ---------------------------------------------------------------------------

def compute_trade_signals(
    price:    float,
    proba:    float,
    decision: str,
    atr:      float,
    horizon:  int,
    term:     str,
) -> dict:
    if term == "short":
        stop_mult   = 1.5
        reward_mult = 2.5
        cal_days    = round(horizon * 1.4)
        duration    = "Short-term (~" + str(horizon) + " trading days / ~" + str(cal_days) + " calendar days)"
    else:
        stop_mult   = 2.5
        reward_mult = 5.0
        cal_days    = round(horizon * 1.4)
        duration    = "Long-term (~" + str(horizon) + " trading days / ~" + str(cal_days) + " calendar days)"

    base = {
        "term":           term,
        "horizon_days":   horizon,
        "duration":       duration,
        "decision":       decision,
        "probability_up": round(proba * 100, 1),
        "atr_14":         round(atr, 4),
    }

    if decision in ("BUY", "HOLD"):
        entry  = round(price, 2)
        stop   = round(price - atr * stop_mult, 2)
        limit  = round(price + atr * reward_mult * proba, 2)
        risk   = price - stop
        reward = limit - price
        base.update({
            "entry_price":        entry,
            "stop_loss":          stop,
            "limit_price":        limit,
            "risk_reward_ratio":  round(reward / risk, 2) if risk > 0 else None,
            "potential_gain_pct": round((limit - entry) / entry * 100, 2),
            "max_loss_pct":       round((entry - stop)  / entry * 100, 2),
        })
    else:
        base.update({
            "entry_price":        None,
            "stop_loss":          None,
            "limit_price":        None,
            "risk_reward_ratio":  None,
            "potential_gain_pct": None,
            "max_loss_pct":       None,
        })

    return base


# ---------------------------------------------------------------------------
# 7. Dual-horizon pipeline (main new public function)
# ---------------------------------------------------------------------------

def run_dual_horizon_pipeline(
    ticker:            str,
    start:             str   = "2015-01-01",
    short_horizon:     int   = 10,
    long_horizon:      int   = 90,
    short_buy_thresh:  float = 0.60,
    short_sell_thresh: float = 0.40,
    long_buy_thresh:   float = 0.55,
    long_sell_thresh:  float = 0.45,
) -> dict:
    raw   = load_price_data(ticker, start=start)
    atr   = compute_atr(raw)

    short  = _run_pipeline_on_raw(raw, short_horizon, short_buy_thresh, short_sell_thresh, ticker)
    long_r = _run_pipeline_on_raw(raw, long_horizon,  long_buy_thresh,  long_sell_thresh,  ticker)

    price = short["price_today"]

    short_signals = compute_trade_signals(
        price, short["proba_today"], short["decision"], atr, short_horizon, "short"
    )
    long_signals = compute_trade_signals(
        price, long_r["proba_today"], long_r["decision"], atr, long_horizon, "long"
    )

    return {
        "ticker":          ticker,
        "price_today":     price,
        "last_10d_actual": short["last_10d_actual"],
        "short_term": {
            **short_signals,
            "annual_return": short["annual_return"],
            "sharpe":        short["sharpe"],
            "cum_return":    short["cum_return"],
        },
        "long_term": {
            **long_signals,
            "annual_return": long_r["annual_return"],
            "sharpe":        long_r["sharpe"],
            "cum_return":    long_r["cum_return"],
        },
    }


# ---------------------------------------------------------------------------
# 8. Public helpers used by existing API endpoints (interface unchanged)
# ---------------------------------------------------------------------------

def run_pipeline_for_ticker(
    ticker:      str,
    start:       str   = "2015-01-01",
    horizon:     int   = 10,
    buy_thresh:  float = 0.6,
    sell_thresh: float = 0.4,
) -> dict:
    raw  = load_price_data(ticker, start=start)
    core = _run_pipeline_on_raw(raw, horizon, buy_thresh, sell_thresh, ticker)
    return {
        "ticker":          ticker,
        "decision_today":  core["decision"],
        "price_today":     core["price_today"],
        "proba_pos_move":  core["proba_today"],
        "last_10d_actual": core["last_10d_actual"],
        "annual_return":   core["annual_return"],
        "sharpe":          core["sharpe"],
        "cum_return":      core["cum_return"],
    }


def run_compare_for_tickers(
    tickers:     list[str],
    start:       str   = "2015-01-01",
    horizon:     int   = 10,
    buy_thresh:  float = 0.6,
    sell_thresh: float = 0.4,
) -> list[dict]:
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
        except Exception as exc:
            results.append({"ticker": t, "error": str(exc)})
    return results
