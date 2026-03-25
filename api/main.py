# api/main.py

from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from nectaric_core.symbol_resolver import resolve_symbol, resolve_many
from fastapi.middleware.cors import CORSMiddleware
from nectaric_core.pipeline import (
    run_pipeline_for_ticker,
)
from nectaric_core.realtime_scores import get_realtime_factor_snapshot
from nectaric_core.symbol_resolver import resolve_symbol, resolve_many, search_symbol_suggestions

app = FastAPI(
    title="Nectaric AI API",
    version="0.1.0",
    description="Nectaric AI – all-in-one Quant / Valuation / News prototype",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later to your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend files
# app.mount("/static", StaticFiles(directory="frontend"), name="static")


# @app.get("/", include_in_schema=False)
# async def serve_frontend():
#     return FileResponse("frontend/index.html")


@app.get("/health", tags=["meta"])
async def health_check():
    return {"status": "ok", "message": "Nectaric AI is running."}


@app.get("/api/factor_scores", tags=["factor"])
async def factor_scores(
    ticker: str = Query(..., description="Ticker symbol, e.g. NVDA"),
):
    try:
        return get_realtime_factor_snapshot(ticker)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stock_summary", tags=["snapshot"])
async def stock_summary(
    ticker: str = Query(..., description="Ticker symbol or company name"),
    start: str = Query("2015-01-01"),
    horizon: int = Query(10),
    buy_thresh: float = Query(0.6),
    sell_thresh: float = Query(0.4),
):
    try:
        resolved = resolve_symbol(ticker)
        symbol = resolved["symbol"]

        core = run_pipeline_for_ticker(
            ticker=symbol,
            start=start,
            horizon=horizon,
            buy_thresh=buy_thresh,
            sell_thresh=sell_thresh,
        )
        factor = get_realtime_factor_snapshot(symbol)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "ticker": symbol,
        "input_query": ticker,
        "resolved_name": resolved.get("name"),
        "resolved_exchange": resolved.get("exchange"),
        "price": core["price_today"],
        "trading_ml": {
            "decision_today": core["decision_today"],
            "probability_positive_move": core["proba_pos_move"],
            "horizon_days": horizon,
            "last_10d_actual_return": core["last_10d_actual"],
        },
        "strategy_performance": {
            "annual_return": core["annual_return"],
            "sharpe": core["sharpe"],
            "cum_return": core["cum_return"],
        },
        "factor_model": factor,
        "valuation": {
            "ticker": symbol,
            "valuation_status": factor["conviction"],
            "nectaric_score": factor["final_score"],
            "raw_ratios": factor["raw_metrics"]["value"],
        },
        "news": {
            "ticker": symbol,
            "overall_sentiment": "unknown",
            "headlines": [],
        },
    }


@app.get("/api/compare", tags=["snapshot"])
async def compare_tickers(
    tickers: str = Query(..., description="Comma-separated ticker list or company names"),
    start: str = Query("2015-01-01"),
    horizon: int = Query(10),
    buy_thresh: float = Query(0.6),
    sell_thresh: float = Query(0.4),
):
    raw_queries = [t.strip() for t in tickers.split(",") if t.strip()]
    if not raw_queries:
        raise HTTPException(status_code=400, detail="No valid tickers provided.")

    resolved_items = resolve_many(raw_queries)
    results = []

    for item in resolved_items:
        if item.get("error"):
            results.append({
                "ticker": item["input"],
                "error": item["error"],
            })
            continue

        t = item["symbol"]

        try:
            core = run_pipeline_for_ticker(
                ticker=t,
                start=start,
                horizon=horizon,
                buy_thresh=buy_thresh,
                sell_thresh=sell_thresh,
            )
            factor = get_realtime_factor_snapshot(t)

            results.append({
                "ticker": t,
                "input_query": item["input"],
                "resolved_name": item.get("name"),
                "resolved_exchange": item.get("exchange"),
                "decision_today": core["decision_today"],
                "price_today": core["price_today"],
                "proba_pos_move": core["proba_pos_move"],
                "last_10d_actual": core["last_10d_actual"],
                "annual_return": core["annual_return"],
                "sharpe": core["sharpe"],
                "cum_return": core["cum_return"],
                "valuation_status": factor["conviction"],
                "nectaric_score": factor["final_score"],
                "risk_level": factor["risk_level"],
                "buy_safety": factor["buy_safety"],
                "factor_model": factor,
            })
        except Exception as exc:
            results.append({
                "ticker": t,
                "input_query": item["input"],
                "resolved_name": item.get("name"),
                "error": str(exc),
            })

    return {
        "queries": raw_queries,
        "resolved": resolved_items,
        "horizon_days": horizon,
        "buy_thresh": buy_thresh,
        "sell_thresh": sell_thresh,
        "results": results,
    }
            
@app.get("/api/resolve_symbol", tags=["symbol"])
async def resolve_symbol_api(
    query: str = Query(..., description="Ticker or company name, e.g. NVDA or NVIDIA"),
):
    try:
        return resolve_symbol(query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
    
@app.get("/api/search_symbols", tags=["symbol"])
async def search_symbols_api(
    query: str = Query(..., description="Company name or partial stock name"),
    max_results: int = Query(8, ge=1, le=15),
):
    try:
        return {
            "query": query,
            "results": search_symbol_suggestions(query, max_results=max_results)
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
