from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

import csv
import io
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from nectaric_core.pipeline import run_pipeline_for_ticker, run_dual_horizon_pipeline
from nectaric_core.realtime_scores import get_realtime_factor_snapshot
from nectaric_core.market_providers import FinnhubClient, ProviderError


app = FastAPI(
    title="Nectaric AI API",
    version="0.3.0",
    description="Nectaric AI - ML signals, actionable trade signals, and factor scoring",
)

origins = [
    "https://nectaric-ai-venture.onrender.com",
    "https://nectaric-ai-frontend.onrender.com",
    "https://nectaric-ai.onrender.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse("frontend/index.html")


@app.get("/health", tags=["meta"])
async def health_check():
    return {"status": "ok", "message": "Nectaric AI is running."}


@app.get("/api/search_symbols", tags=["symbol"])
async def search_symbols_api(
    query: str = Query(..., description="Company name or partial stock name"),
    max_results: int = Query(8, ge=1, le=15),
):
    try:
        client  = FinnhubClient()
        matches = client.search_symbols(query, limit=max_results)
        return {
            "query":   query,
            "results": [
                {
                    "symbol":   m.symbol,
                    "name":     m.name,
                    "exchange": m.exchange,
                    "source":   m.source,
                }
                for m in matches
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/resolve_symbol", tags=["symbol"])
async def resolve_symbol_api(
    query: str = Query(..., description="Ticker or company name, e.g. NVDA or NVIDIA"),
):
    try:
        client   = FinnhubClient()
        resolved = client.resolve_symbol(query)
        return {
            "input":    resolved.input_query,
            "symbol":   resolved.symbol,
            "name":     resolved.name,
            "exchange": resolved.exchange,
            "source":   resolved.source,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/factor_scores", tags=["factor"])
async def factor_scores(
    ticker: str = Query(..., description="Ticker symbol or company name, e.g. NVDA or NVIDIA"),
):
    try:
        client   = FinnhubClient()
        resolved = client.resolve_symbol(ticker)
        factor   = get_realtime_factor_snapshot(resolved.symbol)
        return {
            "input_query":       ticker,
            "ticker":            resolved.symbol,
            "resolved_name":     resolved.name,
            "resolved_exchange": resolved.exchange,
            **factor,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stock_summary", tags=["snapshot"])
async def stock_summary(
    ticker:      str   = Query(..., description="Ticker symbol or company name, e.g. NVDA or NVIDIA"),
    start:       str   = Query("2015-01-01", description="History start date (YYYY-MM-DD)"),
    horizon:     int   = Query(10, description="Forecast horizon in trading days"),
    buy_thresh:  float = Query(0.6, description="Probability threshold to BUY"),
    sell_thresh: float = Query(0.4, description="Probability threshold to SELL"),
):
    try:
        client   = FinnhubClient()
        resolved = client.resolve_symbol(ticker)
        symbol   = resolved.symbol

        core   = run_pipeline_for_ticker(
            ticker=symbol, start=start, horizon=horizon,
            buy_thresh=buy_thresh, sell_thresh=sell_thresh,
        )
        factor = get_realtime_factor_snapshot(symbol)

        return {
            "ticker":            symbol,
            "input_query":       ticker,
            "resolved_name":     resolved.name,
            "resolved_exchange": resolved.exchange,
            "price":             core["price_today"],
            "trading_ml": {
                "decision_today":            core["decision_today"],
                "probability_positive_move": core["proba_pos_move"],
                "horizon_days":              horizon,
                "last_10d_actual_return":    core["last_10d_actual"],
            },
            "strategy_performance": {
                "annual_return": core["annual_return"],
                "sharpe":        core["sharpe"],
                "cum_return":    core["cum_return"],
            },
            "factor_model": factor,
            "valuation": {
                "ticker":           symbol,
                "valuation_status": factor["conviction"],
                "nectaric_score":   factor["final_score"],
                "raw_ratios":       factor["raw_metrics"]["value"],
            },
            "news": {
                "ticker":            symbol,
                "overall_sentiment": "unknown",
                "headlines":         [],
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/actionable_signals", tags=["signals"])
async def actionable_signals(
    ticker:            str   = Query(..., description="Ticker symbol or company name, e.g. NVDA or Apple"),
    start:             str   = Query("2015-01-01", description="History start date (YYYY-MM-DD)"),
    short_horizon:     int   = Query(10, description="Short-term horizon in trading days"),
    long_horizon:      int   = Query(90, description="Long-term horizon in trading days"),
    short_buy_thresh:  float = Query(0.60),
    short_sell_thresh: float = Query(0.40),
    long_buy_thresh:   float = Query(0.55),
    long_sell_thresh:  float = Query(0.45),
):
    try:
        client   = FinnhubClient()
        resolved = client.resolve_symbol(ticker)
        symbol   = resolved.symbol

        signals = run_dual_horizon_pipeline(
            ticker            = symbol,
            start             = start,
            short_horizon     = short_horizon,
            long_horizon      = long_horizon,
            short_buy_thresh  = short_buy_thresh,
            short_sell_thresh = short_sell_thresh,
            long_buy_thresh   = long_buy_thresh,
            long_sell_thresh  = long_sell_thresh,
        )

        return {
            "ticker":            symbol,
            "input_query":       ticker,
            "resolved_name":     resolved.name,
            "resolved_exchange": resolved.exchange,
            **signals,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/compare", tags=["snapshot"])
async def compare_tickers(
    tickers:     str   = Query(..., description="Comma-separated ticker list or company names"),
    start:       str   = Query("2015-01-01"),
    horizon:     int   = Query(10),
    buy_thresh:  float = Query(0.6),
    sell_thresh: float = Query(0.4),
):
    raw_queries = [t.strip() for t in tickers.split(",") if t.strip()]
    if not raw_queries:
        raise HTTPException(status_code=400, detail="No valid tickers provided.")

    client  = FinnhubClient()
    results = []
    resolved_items = []

    for q in raw_queries:
        try:
            resolved = client.resolve_symbol(q)
            resolved_items.append({
                "input":    resolved.input_query,
                "symbol":   resolved.symbol,
                "name":     resolved.name,
                "exchange": resolved.exchange,
                "source":   resolved.source,
            })

            core   = run_pipeline_for_ticker(
                ticker=resolved.symbol, start=start, horizon=horizon,
                buy_thresh=buy_thresh, sell_thresh=sell_thresh,
            )
            factor = get_realtime_factor_snapshot(resolved.symbol)

            results.append({
                "ticker":            resolved.symbol,
                "input_query":       resolved.input_query,
                "resolved_name":     resolved.name,
                "resolved_exchange": resolved.exchange,
                "decision_today":    core["decision_today"],
                "price_today":       core["price_today"],
                "proba_pos_move":    core["proba_pos_move"],
                "last_10d_actual":   core["last_10d_actual"],
                "annual_return":     core["annual_return"],
                "sharpe":            core["sharpe"],
                "cum_return":        core["cum_return"],
                "valuation_status":  factor["conviction"],
                "nectaric_score":    factor["final_score"],
                "risk_level":        factor["risk_level"],
                "buy_safety":        factor["buy_safety"],
                "factor_model":      factor,
            })

        except Exception as exc:
            resolved_items.append({"input": q, "error": str(exc)})
            results.append({"ticker": q, "input_query": q, "error": str(exc)})

    return {
        "queries":      raw_queries,
        "resolved":     resolved_items,
        "horizon_days": horizon,
        "buy_thresh":   buy_thresh,
        "sell_thresh":  sell_thresh,
        "results":      results,
    }


# ---------------------------------------------------------------------------
# Watchlist — 25 curated US stocks for Power BI / Tableau live connection
# ---------------------------------------------------------------------------

WATCHLIST = [
    "NVDA", "AMD", "MSFT", "GOOGL", "META", "AVGO", "QCOM",
    "ORCL", "CSCO", "CRM", "TSM", "ARM", "MU", "INTC", "PLTR",
    "NOW", "NVO", "PFE", "FCX", "DVN", "IONQ", "SOUN", "RKLB",
    "HIMS", "SNAP",
]


@app.get("/api/watchlist", tags=["export"])
async def get_watchlist():
    return {"tickers": WATCHLIST, "count": len(WATCHLIST)}


@app.get("/api/export/csv", tags=["export"])
async def export_csv(
    tickers: str = Query(
        ",".join(WATCHLIST),
        description="Comma-separated tickers. Defaults to full Nectaric watchlist.",
    ),
    start:       str   = Query("2015-01-01"),
    horizon:     int   = Query(10),
    buy_thresh:  float = Query(0.6),
    sell_thresh: float = Query(0.4),
):
    """
    Export signal + factor data as a flat CSV table.

    Use this URL as a live data source in Power BI or Tableau:
      Power BI  : Get Data -> Web -> paste this URL
      Tableau   : Connect -> Web Data Connector -> paste this URL
      Excel     : Data -> From Web -> paste this URL

    The CSV refreshes with live data every time Power BI / Tableau refreshes.
    """
    raw_queries = [t.strip() for t in tickers.split(",") if t.strip()]
    if not raw_queries:
        raise HTTPException(status_code=400, detail="No valid tickers provided.")

    client = FinnhubClient()
    rows   = []

    for q in raw_queries:
        try:
            resolved = client.resolve_symbol(q)
            symbol   = resolved.symbol

            core   = run_pipeline_for_ticker(
                ticker=symbol, start=start, horizon=horizon,
                buy_thresh=buy_thresh, sell_thresh=sell_thresh,
            )
            factor  = get_realtime_factor_snapshot(symbol)
            factors = factor.get("factors", {})

            rows.append({
                "Ticker":             symbol,
                "Name":               resolved.name or symbol,
                "Decision":           core["decision_today"],
                "Price_USD":          round(core["price_today"], 2),
                "P_Up_Pct":           round((core["proba_pos_move"] or 0) * 100, 2),
                "Last_10d_Actual_Pct": round((core["last_10d_actual"] or 0) * 100, 2),
                "Annual_Return_Pct":  round((core["annual_return"] or 0) * 100, 2),
                "Sharpe_Ratio":       round(core["sharpe"] or 0, 3),
                "Cum_Return_Pct":     round(core["cum_return"] or 0, 2),
                "Nectaric_Score":     factor.get("final_score", ""),
                "Conviction":         factor.get("conviction", ""),
                "Risk_Level":         factor.get("risk_level", ""),
                "Buy_Safety":         factor.get("buy_safety", ""),
                "Quality_Score":      factors.get("quality", ""),
                "Growth_Score":       factors.get("growth", ""),
                "Value_Score":        factors.get("value", ""),
                "Momentum_Score":     factors.get("momentum", ""),
                "Risk_Score":         factors.get("risk", ""),
                "Horizon_Days":       horizon,
            })
        except Exception:
            pass

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nectaric_signals.csv"},
    )
