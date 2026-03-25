from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import requests


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
    r.raise_for_status()
    return r.json()


class FinnhubClient:
    """
    Use Finnhub mainly for company-name / ticker search.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _get_env("FINNHUB_API_KEY")

    def search_symbols(self, query: str, limit: int = 8) -> List[ResolvedSymbol]:
        data = _http_get(
            f"{FINNHUB_BASE}/search",
            {
                "q": query,
                "token": self.api_key,
            },
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


class FMPClient:
    """
    Use FMP for quote, history, and fundamentals scoring inputs.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or _get_env("FMP_API_KEY")

    def _call(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        params["apikey"] = self.api_key
        return _http_get(f"{FMP_BASE}/{path}", params)

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        data = self._call("quote", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        raise ProviderError(f"No quote returned for {symbol}")

    def get_historical_eod(self, symbol: str) -> pd.DataFrame:
        data = self._call("historical-price-eod/full", {"symbol": symbol})
        rows = data if isinstance(data, list) else data.get("historical", [])

        if not rows:
            raise ProviderError(f"No historical EOD data returned for {symbol}")

        df = pd.DataFrame(rows)
        if "date" not in df.columns:
            raise ProviderError(f"Unexpected historical format for {symbol}")

        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        rename_map = {
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=rename_map)

        keep_cols = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        return df[keep_cols]

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
        Merge the main fields we need for scoring.
        """
        quote = self.get_quote(symbol)
        ratios = self.get_ratios_ttm(symbol)
        metrics = self.get_key_metrics_ttm(symbol)
        growth = self.get_income_statement_growth(symbol)
        scores = self.get_financial_scores(symbol)

        return {
            "symbol": symbol.upper(),
            "quote": quote,
            "ratios_ttm": ratios,
            "key_metrics_ttm": metrics,
            "income_statement_growth": growth,
            "financial_scores": scores,
        }
