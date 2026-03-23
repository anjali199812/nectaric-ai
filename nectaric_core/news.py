# nectaric_core/news.py

from typing import List, Dict, Any
from datetime import datetime
import yfinance as yf


def get_simple_news(ticker: str, limit: int = 5) -> Dict[str, Any]:
    """
    Simple news snapshot from yfinance (Seeking-Alpha/Motley-Fool style).

    For each item we return:
      - title
      - publisher
      - link
      - time
      - placeholder 'sentiment' (can be wired to an NLP model later)
    """
    t = yf.Ticker(ticker)
    try:
        raw_news = t.news or []
    except Exception:
        raw_news = []

    items: List[Dict[str, Any]] = []
    for item in raw_news[:limit]:
        ts = item.get("providerPublishTime")
        try:
            published_at = (
                datetime.utcfromtimestamp(ts).isoformat() + "Z" if ts else None
            )
        except Exception:
            published_at = None

        items.append(
            {
                "title": item.get("title"),
                "publisher": item.get("publisher"),
                "link": item.get("link"),
                "published_at": published_at,
                "sentiment": "unknown",  # placeholder
            }
        )

    return {
        "ticker": ticker.upper(),
        "overall_sentiment": "unknown",  # future: aggregate from headline sentiments
        "headlines": items,
    }
