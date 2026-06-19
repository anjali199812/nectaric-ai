from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yfinance as yf


FMP_BASE = "https://financialmodelingprep.com/stable"
FINNHUB_BASE = "https://finnhub.io/api/v1"


class ProviderError(RuntimeError):
    pass


@dataclass
class ResolvedSymbol:
    input_query: str
    symbol: str
    name: str
    exchange: Optional[str] = None
    source: str = "unknown"


def _get_env(name: str, required: bool = True) -> Optional[str]:
    value = os.getenv(name)
    if required and not value:
        raise ProviderError(f"Missing environment variable: {name}")
    return value


def _http_get(url: str, params: Dict[str, Any], timeout: int = 20) -> Any:
    r = requests.get(url, params=params, timeout=timeout)
    if r.status_code in (402, 403, 429):
        return {}
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# yfinance fundamental snapshot (free, no API key, any US ticker)
# ---------------------------------------------------------------------------

def _yfinance_snapshot(symbol: str) -> Dict[str, Any]:
    """
    Build a fundamental snapshot from yfinance .info so realtime_scores.py
    can score any ticker without needing a paid FMP plan.

    yfinance returns most values as ratios (0.12 = 12%).
    realtime_scores._pct_or_number() converts them automatically.
    """
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}

    quote = {
        "beta":              info.get("beta"),
        "pe":                info.get("trailingPE"),
        "priceToBookRatio":  info.get("priceToBook"),
        "priceToSalesRatio": info.get("priceToSalesTrailing12Months"),
    }

    ratios_ttm = {
        "peRatioTTM":                info.get("trailingPE"),
        "priceToBookRatioTTM":       info.get("priceToBook"),
        "priceToSalesRatioTTM":      info.get("priceToSalesTrailing12Months"),
        "netProfitMarginTTM":        info.get("profitMargins"),
        "operatingProfitMarginTTM":  info.get("operatingMargins"),
        "debtEquityRatioTTM":        info.get("debtToEquity"),
    }

    key_metrics_ttm = {
        "roeTTM":         info.get("returnOnEquity"),
        "pbRatioTTM":     info.get("priceToBook"),
        "psRatioTTM":     info.get("priceToSalesTrailing12Months"),
        "debtToEquityTTM": info.get("debtToEquity"),
    }

    income_growth = {
        "growthRevenue":    info.get("revenueGrowth"),
        "growthNetIncome":  info.get("earningsGrowth"),
    }

    financial_scores = {
        "debtToEquity": info.get("debtToEquity"),
    }

    return {
        "symbol":                  symbol.upper(),
        "quote":                   quote,
        "ratios_ttm":              ratios_ttm,
        "key_metrics_ttm":         key_metrics_ttm,
        "income_statement_growth": income_growth,
        "financial_scores":        financial_scores,
        "source":                  "yfinance",
    }


def _yfinance_price_history(symbol: str) -> pd.DataFrame:
    """Download price history from yfinance as a fallback for FMP EOD data."""
    try:
        df = yf.download(symbol, start="2015-01-01", auto_adjust=True, progress=False)
        if df.empty:
            return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        df = df.reset_index()
        df = df.rename(columns={"index": "Date"})
        keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        return df[keep]
    except Exception:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])


# ---------------------------------------------------------------------------
# Finnhub client
# ---------------------------------------------------------------------------

class FinnhubClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _get_env("FINNHUB_API_KEY")

    def search_symbols(self, query: str, limit: int = 8) -> List[ResolvedSymbol]:
        data = _http_get(
            f"{FINNHUB_BASE}/search",
            {"q": query, "token": self.api_key},
        )
        results = data.get("result", [])[:limit]
        out: List[ResolvedSymbol] = []
        for item in results:
            symbol = item.get("symbol")
            description = item.get("description") or symbol
            if not symbol:
                continue
            out.append(
                ResolvedSymbol(
                    input_query=query,
                    symbol=symbol.upper(),
                    name=description,
                    exchange=item.get("displaySymbol"),
                    source="finnhub",
                )
            )
        return out

    def resolve_symbol(self, query: str) -> ResolvedSymbol:
        query = query.strip()
        if not query:
            raise ProviderError("Empty query provided.")

        if query.upper() == query and " " not in query and len(query) <= 8:
            return ResolvedSymbol(
                input_query=query,
                symbol=query.upper(),
                name=query.upper(),
                exchange=None,
                source="direct",
            )

        matches = self.search_symbols(query, limit=8)
        if not matches:
            raise ProviderError(f"Could not resolve '{query}' to a ticker.")
        return matches[0]


# ---------------------------------------------------------------------------
# FMP client — with yfinance fallback on every call
# ---------------------------------------------------------------------------

class FMPClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _get_env("FMP_API_KEY")

    def _call(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        params["apikey"] = self.api_key
        try:
            return _http_get(f"{FMP_BASE}/{path}", params)
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (402, 403, 429):
                return {}
            raise

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        data = self._call("quote", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def get_historical_eod(self, symbol: str) -> pd.DataFrame:
        data = self._call("historical-price-eod/full", {"symbol": symbol})
        rows = data if isinstance(data, list) else data.get("historical", [])

        if not rows:
            return _yfinance_price_history(symbol)

        df = pd.DataFrame(rows)
        if "date" not in df.columns:
            return _yfinance_price_history(symbol)

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        rename_map = {
            "date": "Date", "open": "Open", "high": "High",
            "low": "Low", "close": "Close", "volume": "Volume",
        }
        df = df.rename(columns=rename_map)
        keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        return df[keep]

    def get_ratios_ttm(self, symbol: str) -> Dict[str, Any]:
        data = self._call("ratios-ttm", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def get_key_metrics_ttm(self, symbol: str) -> Dict[str, Any]:
        data = self._call("key-metrics-ttm", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def get_income_statement_growth(self, symbol: str) -> Dict[str, Any]:
        data = self._call("income-statement-growth", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def get_financial_scores(self, symbol: str) -> Dict[str, Any]:
        data = self._call("financial-scores", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        return {}

    def get_fundamental_snapshot(self, symbol: str) -> Dict[str, Any]:
        """
        Try FMP first. If FMP returns empty data (402 / rate limit),
        fall back to yfinance which is free and covers all US stocks.
        """
        quote   = self.get_quote(symbol)
        ratios  = self.get_ratios_ttm(symbol)
        metrics = self.get_key_metrics_ttm(symbol)
        growth  = self.get_income_statement_growth(symbol)
        scores  = self.get_financial_scores(symbol)

        fmp_has_data = any([quote, ratios, metrics, growth, scores])

        if not fmp_has_data:
            return _yfinance_snapshot(symbol)

        return {
            "symbol":                  symbol.upper(),
            "quote":                   quote,
            "ratios_ttm":              ratios,
            "key_metrics_ttm":         metrics,
            "income_statement_growth": growth,
            "financial_scores":        scores,
            "source":                  "fmp",
        }
