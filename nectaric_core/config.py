from datetime import date

# You can change these defaults in notebooks or API calls
DEFAULT_START_DATE = "2015-01-01"
DEFAULT_HORIZON = 10  # days

# Default buy / sell probability thresholds
DEFAULT_BUY_THRESH = 0.60
DEFAULT_SELL_THRESH = 0.40


def today_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return date.today().isoformat()
