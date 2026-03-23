from typing import Dict, List, Any
import re
import yfinance as yf


NASDAQ_HINTS = {"nms", "nasdaq", "nasdaqgs", "nasdaqgm", "nasdaqcm"}
GOOD_TYPES = {"equity", "stock"}

EXCHANGE_LABELS = {
    "NMS": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "NASDAQGS": "NASDAQ",
    "NASDAQGM": "NASDAQ",
    "NASDAQCM": "NASDAQ",
    "NYQ": "NYSE",
    "NYSE": "NYSE",
    "ASE": "NYSE American",
    "PCX": "NYSE Arca",
}


def normalize_query(q: str) -> str:
    return " ".join(q.strip().split())


def normalize_exchange_label(exchange: str | None) -> str | None:
    if not exchange:
        return exchange
    ex = str(exchange).upper()
    return EXCHANGE_LABELS.get(ex, exchange)


def looks_like_ticker(text: str) -> bool:
    """
    Treat as ticker only if the user entered something that already
    looks like a market symbol, e.g. AMZN, NVDA, BRK.B, RIO.AX

    This avoids misclassifying normal company names like 'Amazon'
    as ticker 'AMAZON'.
    """
    raw = text.strip()

    if not raw:
        return False

    if " " in raw:
        return False

    if raw != raw.upper():
        return False

    return bool(re.fullmatch(r"[A-Z.\-]{1,8}", raw))


def build_search_queries(query: str) -> List[str]:
    """
    Build a few search variants so broad names like 'Amazon'
    are easier to resolve correctly.
    """
    q = normalize_query(query)
    variants = [q]

    if "stock" not in q.lower():
        variants.append(f"{q} stock")
    if "inc" not in q.lower():
        variants.append(f"{q} inc")
    if "corporation" not in q.lower():
        variants.append(f"{q} corporation")
    if "company" not in q.lower() and "co" not in q.lower():
        variants.append(f"{q} company")

    seen = set()
    out = []
    for v in variants:
        key = v.lower()
        if key not in seen:
            out.append(v)
            seen.add(key)
    return out


def score_quote_match(item: Dict[str, Any], query: str) -> float:
    """
    Rank search results. Higher score = better match.
    """
    symbol = (item.get("symbol") or "").upper()
    shortname = (item.get("shortname") or "").lower()
    longname = (item.get("longname") or "").lower()
    quote_type = (item.get("quoteType") or "").lower()
    exchange = (item.get("exchange") or item.get("fullExchangeName") or "").lower()

    q = query.lower().strip()
    score = 0.0

    if quote_type in GOOD_TYPES:
        score += 4.0
    elif quote_type == "etf":
        score -= 1.0
    else:
        score -= 2.0

    if exchange in NASDAQ_HINTS or "nasdaq" in exchange:
        score += 3.0

    if q.upper() == symbol:
        score += 12.0

    if q == shortname:
        score += 12.0
    if q == longname:
        score += 12.0

    if shortname.startswith(q):
        score += 8.0
    if longname.startswith(q):
        score += 8.0

    if q in shortname:
        score += 5.0
    if q in longname:
        score += 5.0

    q_words = set(q.split())
    name_words = set((shortname + " " + longname).split())
    overlap = len(q_words.intersection(name_words))
    score += overlap * 1.5

    if q in name_words:
        score += 4.0

    if not shortname and not longname:
        score -= 1.0

    return score


def search_quotes_once(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    try:
        search = yf.Search(query, max_results=max_results)
        return search.quotes or []
    except Exception:
        return []


def gather_ranked_candidates(query: str) -> List[Dict[str, Any]]:
    """
    Search using several query variants, merge unique symbols,
    and rank them together.
    """
    ranked: List[Dict[str, Any]] = []
    seen_symbols = set()

    for variant in build_search_queries(query):
        quotes = search_quotes_once(variant, max_results=10)

        for item in quotes:
            symbol = item.get("symbol")
            if not symbol:
                continue

            symbol_u = symbol.upper()
            if symbol_u in seen_symbols:
                continue
            seen_symbols.add(symbol_u)

            ranked.append(
                {
                    "input": query,
                    "symbol": symbol_u,
                    "name": item.get("shortname") or item.get("longname") or symbol_u,
                    "quote_type": item.get("quoteType"),
                    "exchange": normalize_exchange_label(
                        item.get("exchange") or item.get("fullExchangeName")
                    ),
                    "source": "search",
                    "_score": score_quote_match(item, normalize_query(query)),
                }
            )

    ranked.sort(key=lambda x: x["_score"], reverse=True)
    return ranked


def resolve_symbol(query: str) -> Dict[str, Any]:
    """
    Resolve a user input to the most likely ticker.
    """
    q = normalize_query(query)
    if not q:
        raise ValueError("Empty ticker/company name provided.")

    if looks_like_ticker(q):
        return {
            "input": query,
            "symbol": q.upper(),
            "name": q.upper(),
            "exchange": None,
            "source": "direct",
        }

    ranked = gather_ranked_candidates(q)
    if not ranked:
        raise ValueError(f"Could not resolve '{query}' to a ticker symbol.")

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
            out.append(
                {
                    "input": q,
                    "error": str(exc),
                }
            )

    return out


def search_symbol_suggestions(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """
    Return ranked suggestions for autocomplete.
    """
    q = normalize_query(query)
    if not q or len(q) < 2:
        return []

    ranked = gather_ranked_candidates(q)
    out = []

    for item in ranked[:max_results]:
        out.append(
            {
                "symbol": item["symbol"],
                "name": item.get("name"),
                "exchange": item.get("exchange"),
                "source": item.get("source", "search"),
            }
        )

    return out
