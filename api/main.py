from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
from typing import List

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from nectaric_core.pipeline import run_pipeline_for_ticker
from nectaric_core.realtime_scores import get_realtime_factor_snapshot
from nectaric_core.market_providers import FinnhubClient, ProviderError


app = FastAPI(
    title="Nectaric AI API",
    version="0.2.0",
    description="Nectaric AI – ML signals, autocomplete, and provider-based factor scoring",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nectaric-ai-frontend.onrender.com",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend assets
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
        client = FinnhubClient()
        matches = client.search_symbols(query, limit=max_results)

        return {
            "query": query,
            "results": [
                {
                    "symbol": m.symbol,
                    "name": m.name,
                    "exchange": m.exchange,
                    "source": m.source,
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
        client = FinnhubClient()
        resolved = client.resolve_symbol(query)
        return {
            "input": resolved.input_query,
            "symbol": resolved.symbol,
            "name": resolved.name,
            "exchange": resolved.exchange,
            "source": resolved.source,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/factor_scores", tags=["factor"])
async def factor_scores(
    ticker: str = Query(..., description="Ticker symbol or company name, e.g. NVDA or NVIDIA"),
):
    try:
        client = FinnhubClient()
        resolved = client.resolve_symbol(ticker)
        factor = get_realtime_factor_snapshot(resolved.symbol)

        return {
            "input_query": ticker,
            "ticker": resolved.symbol,
            "resolved_name": resolved.name,
            "resolved_exchange": resolved.exchange,
            **factor,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stock_summary", tags=["snapshot"])
async def stock_summary(
    ticker: str = Query(..., description="Ticker symbol or company name, e.g. NVDA or NVIDIA"),
    start: str = Query("2015-01-01", description="History start date (YYYY-MM-DD)"),
    horizon: int = Query(10, description="Forecast horizon in trading days"),
    buy_thresh: float = Query(0.6, description="Probability threshold to BUY"),
    sell_thresh: float = Query(0.4, description="Probability threshold to SELL"),
):
    try:
        client = FinnhubClient()
        resolved = client.resolve_symbol(ticker)
        symbol = resolved.symbol

        # ML/trading side still uses your existing pipeline
        core = run_pipeline_for_ticker(
            ticker=symbol,
            start=start,
            horizon=horizon,
            buy_thresh=buy_thresh,
            sell_thresh=sell_thresh,
        )

        # Factor scoring now uses provider-based data layer
        factor = get_realtime_factor_snapshot(symbol)

        return {
            "ticker": symbol,
            "input_query": ticker,
            "resolved_name": resolved.name,
            "resolved_exchange": resolved.exchange,
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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

    client = FinnhubClient()
    results = []
    resolved_items = []

    for q in raw_queries:
        try:
            resolved = client.resolve_symbol(q)
            resolved_items.append(
                {
                    "input": resolved.input_query,
                    "symbol": resolved.symbol,
                    "name": resolved.name,
                    "exchange": resolved.exchange,
                    "source": resolved.source,
                }
            )

            core = run_pipeline_for_ticker(
                ticker=resolved.symbol,
                start=start,
                horizon=horizon,
                buy_thresh=buy_thresh,
                sell_thresh=sell_thresh,
            )
            factor = get_realtime_factor_snapshot(resolved.symbol)

            results.append(
                {
                    "ticker": resolved.symbol,
                    "input_query": resolved.input_query,
                    "resolved_name": resolved.name,
                    "resolved_exchange": resolved.exchange,
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
                }
            )
        except Exception as exc:
            resolved_items.append(
                {
                    "input": q,
                    "error": str(exc),
                }
            )
            results.append(
                {
                    "ticker": q,
                    "input_query": q,
                    "error": str(exc),
                }
            )

    return {
        "queries": raw_queries,
        "resolved": resolved_items,
        "horizon_days": horizon,
        "buy_thresh": buy_thresh,
        "sell_thresh": sell_thresh,
        "results": results,
    }
