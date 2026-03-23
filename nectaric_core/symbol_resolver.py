# nectaric_core/symbol_resolver.py

from typing import Dict, List, Any
import re
import yfinance as yf


NASDAQ_HINTS = {"nms", "nasdaq", "nasdaqgs", "nasdaqgm", "nasdaqcm"}
GOOD_TYPES = {"equity", "stock"}


def normalize_query(q: str) -> str:
    return " ".join(q.strip().split())


def looks_like_ticker(text: str) -> bool:
    raw = text.strip()

    if not raw or " " in raw:
        return False

    # If it's alphabetic and longer than 5, it's probably a company name
    # e.g. amazon, microsoft
    if raw.isalpha() and len(raw) > 5:
        return False

    # Accept short ticker-like strings
    return bool(re.fullmatch(r"[A-Za-z.\-]{1,8}", raw))


def score_quote_match(item: Dict[str, Any], query: str) -> float:
    """
    Rank search results. Higher score = better match.
    Prefers:
    - common stocks/equities
    - NASDAQ listings
    - exact/close symbol match
    - exact/close company-name match
    """
    symbol = (item.get("symbol") or "").upper()
    shortname = (item.get("shortname") or "").lower()
    longname = (item.get("longname") or "").lower()
    quote_type = (item.get("quoteType") or "").lower()
    exchange = (item.get("exchange") or item.get("fullExchangeName") or "").lower()

    q = query.lower().strip()
    score = 0.0

    # Prefer common stocks
    if quote_type in GOOD_TYPES:
        score += 4.0
    elif quote_type == "etf":
        score -= 1.0
    else:
        score -= 2.0

    # Prefer NASDAQ when ambiguous
    if exchange in NASDAQ_HINTS or "nasdaq" in exchange:
        score += 3.0

    # Exact symbol match
    if q.upper() == symbol:
        score += 12.0

    # Exact company-name match
    if q == shortname:
        score += 10.0
    if q == longname:
        score += 10.0

    # Partial name match
    if q in shortname:
        score += 6.0
    if q in longname:
        score += 6.0

    # Word overlap bonus
    q_words = set(q.split())
    name_words = set((shortname + " " + longname).split())
    overlap = len(q_words.intersection(name_words))
    score += overlap * 1.5

    # Small penalty if names are missing
    if not shortname and not longname:
        score -= 1.0

    return score


def search_quotes(query: str, max_results: int = 15) -> List[Dict[str, Any]]:
    try:
        search = yf.Search(query, max_results=max_results)
        return search.quotes or []
    except Exception:
        return []


def resolve_symbol(query: str) -> Dict[str, Any]:
    """
    Resolve a user input to the most likely ticker.
    Supports:
    - ticker symbols
    - organization/company names
    - partial names

    No aliases used.
    """
    q = normalize_query(query)
    if not q:
        raise ValueError("Empty ticker/company name provided.")

    # 1. Direct ticker path
    if looks_like_ticker(q):
        return {
            "input": query,
            "symbol": q.upper(),
            "name": q.upper(),
            "source": "direct",
        }

    # 2. Search path
    quotes = search_quotes(q, max_results=15)
    if not quotes:
        raise ValueError(f"Could not resolve '{query}' to a ticker symbol.")

    ranked = []
    for item in quotes:
        symbol = item.get("symbol")
        if not symbol:
            continue

        ranked.append({
            "input": query,
            "symbol": symbol.upper(),
            "name": item.get("shortname") or item.get("longname") or symbol.upper(),
            "quote_type": item.get("quoteType"),
            "exchange": item.get("exchange") or item.get("fullExchangeName"),
            "source": "search",
            "_score": score_quote_match(item, q),
        })

    if not ranked:
        raise ValueError(f"Could not resolve '{query}' to a ticker symbol.")

    ranked.sort(key=lambda x: x["_score"], reverse=True)
    best = ranked[0].copy()
    best.pop("_score", None)
    return best


def resolve_many(query_list: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for q in query_list:
        if not q.strip():
            continue
        try:
            out.append(resolve_symbol(q))
        except Exception as exc:
            out.append({
                "input": q,
                "error": str(exc),
            })
    return out