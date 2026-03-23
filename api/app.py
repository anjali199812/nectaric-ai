# app.py  --- Nectaric AI one-page dashboard

import streamlit as st
import requests
import pandas as pd

API_BASE = "http://127.0.0.1:8000"


def fetch_snapshot(ticker, start="2015-01-01", horizon=10, buy_thresh=0.6, sell_thresh=0.4):
    params = {
        "ticker": ticker,
        "start": start,
        "horizon": horizon,
        "buy_thresh": buy_thresh,
        "sell_thresh": sell_thresh,
    }
    r = requests.get(f"{API_BASE}/api/nectaric_snapshot", params=params)
    r.raise_for_status()
    return r.json()


st.set_page_config(page_title="Nectaric AI – All-in-One", layout="wide")

st.title("📈 Nectaric AI – All-in-One Snapshot")

st.caption(
    "Valuation (Morningstar-style) • Trading/Quant (CMC/QuantConnect-style) "
    "• News (SeekingAlpha/Motley Fool-style) – in one place."
)

# --- Controls ---
tickers_input = st.text_input(
    "Tickers (comma-separated)",
    value="NVDA, AAPL, MSFT, AMZN",
    help="Example: NVDA, AAPL, MSFT, AMZN",
)

col_h1, col_h2, col_h3 = st.columns(3)
with col_h1:
    start = st.text_input("History start date", value="2015-01-01")
with col_h2:
    horizon = st.number_input("Forecast horizon (days)", value=10, min_value=5, max_value=60, step=5)
with col_h3:
    buy_thresh = st.slider("Buy threshold (P(up))", 0.5, 0.9, 0.6, 0.01)
sell_thresh = st.slider("Sell threshold (P(up))", 0.1, 0.5, 0.4, 0.01)

if st.button("Run Nectaric Snapshot"):
    raw_tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    snapshots = []
    errors = []

    for t in raw_tickers:
        try:
            data = fetch_snapshot(
                t,
                start=start,
                horizon=int(horizon),
                buy_thresh=float(buy_thresh),
                sell_thresh=float(sell_thresh),
            )
            snapshots.append(data)
        except Exception as e:
            errors.append((t, str(e)))

    if errors:
        with st.expander("⚠ Errors fetching some tickers", expanded=False):
            for t, msg in errors:
                st.write(f"**{t}**: {msg}")

    if snapshots:
        # --- Comparison table (like your screenshot) ---
        rows = []
        for s in snapshots:
            rows.append(
                {
                    "Ticker": s["ticker"],
                    "Decision": s["trading_ml"]["decision_today"],
                    "P(Up in next N days)": round(s["trading_ml"]["probability_positive_move"], 3),
                    "Last 10d actual %": None if s["trading_ml"]["last_10d_actual_return"] is None
                    else round(100 * s["trading_ml"]["last_10d_actual_return"], 2),
                    "Annual Return %": round(100 * s["strategy_performance"]["annual_return"], 2),
                    "Sharpe": round(s["strategy_performance"]["sharpe"], 2),
                    "Cum Return %": round(100 * s["strategy_performance"]["cum_return"], 2),
                    "Valuation Status": s["valuation"]["valuation_status"],
                    "Nectaric Score (1-5)": s["valuation"]["nectaric_score"],
                }
            )

        df = pd.DataFrame(rows).set_index("Ticker")
        st.subheader("🔍 Comparison – Who Does What (Nectaric View)")
        st.dataframe(df, use_container_width=True)

        st.markdown("---")

        # --- Detail cards per ticker ---
        st.subheader("📊 Ticker Details")
        for s in snapshots:
            with st.expander(f"{s['ticker']} – details", expanded=False):
                c1, c2 = st.columns(2)

                with c1:
                    st.markdown("**Trading / Quant (CMC, QuantConnect-style)**")
                    st.write(f"Current price: **${s['price']:.2f}**")
                    st.write(f"Decision today: **{s['trading_ml']['decision_today']}**")
                    st.write(
                        f"P(Up in next {s['trading_ml']['horizon_days']} days): "
                        f"**{100*s['trading_ml']['probability_positive_move']:.1f}%**"
                    )
                    if s["trading_ml"]["last_10d_actual_return"] is not None:
                        st.write(
                            f"Last 10d actual move: "
                            f"**{100*s['trading_ml']['last_10d_actual_return']:.2f}%**"
                        )

                    st.markdown("**Strategy performance (backtest)**")
                    st.write(
                        f"Annual return: **{100*s['strategy_performance']['annual_return']:.2f}%**"
                    )
                    st.write(f"Sharpe: **{s['strategy_performance']['sharpe']:.2f}**")
                    st.write(
                        f"Cumulative return: **{100*s['strategy_performance']['cum_return']:.2f}%**"
                    )

                with c2:
                    st.markdown("**Valuation (Morningstar-style)**")
                    val = s["valuation"]
                    rr = val["raw_ratios"]
                    st.write(f"Status: **{val['valuation_status']}**")
                    st.write(f"Nectaric score: **{val['nectaric_score']} / 5**")
                    st.write(f"P/E (TTM): {rr['pe_ttm']}")
                    st.write(f"P/S (TTM): {rr['ps_ttm']}")
                    st.write(f"P/B (TTM): {rr['pb_ttm']}")
                    st.write(f"ROE: {rr['roe']}")
                    st.write(f"Debt/Equity: {rr['debt_to_equity']}")

                    st.markdown("**News (Seeking Alpha / Motley Fool-style)**")
                    news = s["news"]
                    for item in news.get("headlines", []):
                        st.write(f"- [{item['title']}]({item['link']}) – {item['publisher']}")
                        if item["published_at"]:
                            st.caption(item["published_at"])
