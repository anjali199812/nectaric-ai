from typing import List, Tuple
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler


def train_logistic_model(
    X: pd.DataFrame,
    y: pd.Series,
) -> Tuple[LogisticRegression, StandardScaler]:
    """
    Train a simple logistic regression classifier with standard scaling.
    Chronological split should already be handled outside.
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LogisticRegression(max_iter=1000)
    model.fit(X_scaled, y)

    return model, scaler


def apply_model_to_df(
    df: pd.DataFrame,
    model: LogisticRegression,
    scaler: StandardScaler,
    features: List[str],
    buy_thresh: float,
    sell_thresh: float,
) -> pd.DataFrame:
    """
    Apply trained model to full DataFrame and create:
    - Proba       : probability of positive future move
    - ML_Signal   : 1=buy, -1=exit/avoid, 0=hold
    """

    out = df.copy()
    X_all = out[features]
    X_all_scaled = scaler.transform(X_all)

    proba_pos = model.predict_proba(X_all_scaled)[:, 1]
    out["Proba"] = proba_pos

    # Signals
    signals = np.zeros(len(out), dtype=int)
    signals[proba_pos >= buy_thresh] = 1
    signals[proba_pos < sell_thresh] = -1
    out["ML_Signal"] = signals

    return out
