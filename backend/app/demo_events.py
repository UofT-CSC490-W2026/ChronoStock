"""
Load pre-generated key-event CSVs from backend/demodata/ and convert them
to NewsEvent objects that the stock endpoint can include in its response.
"""

import csv
import json
from pathlib import Path
from .models import NewsEvent

DEMO_DIR = Path(__file__).resolve().parent.parent / "demodata"

# Map ticker → list[NewsEvent], loaded once at import time
_cache: dict[str, list[NewsEvent]] = {}


def _parse_sentiment(row: dict) -> tuple[str, str | None]:
    """Extract NVDA-specific sentiment + reasoning from the insights JSON, fall back to CAR sign."""
    ticker = row.get("ticker", "")
    raw = row.get("insights", "")
    if raw and raw != "[]":
        try:
            insights = json.loads(raw)
            for entry in insights:
                if entry.get("ticker", "").upper() == ticker.upper():
                    s = entry.get("sentiment", "").lower()
                    reasoning = entry.get("sentiment_reasoning") or None
                    if s in ("positive", "negative", "neutral"):
                        return s, reasoning
        except (json.JSONDecodeError, TypeError):
            pass
    # Fall back to CAR direction
    try:
        car = float(row.get("car", 0))
        return ("positive" if car > 0 else "negative" if car < 0 else "neutral"), None
    except (ValueError, TypeError):
        return "neutral", None


def _source_from_url(url: str) -> str:
    """Extract a human-readable publisher name from the article URL."""
    if "marketwatch.com" in url:
        return "MarketWatch"
    if "benzinga.com" in url:
        return "Benzinga"
    if "fool.com" in url:
        return "Motley Fool"
    if "globenewswire.com" in url:
        return "GlobeNewsWire"
    return "News"


def _load_csv(ticker: str) -> list[NewsEvent]:
    """Scan demodata/ for a CSV matching the ticker and parse it."""
    pattern = f"{ticker.upper()}_event_news_llm_filtered.csv"
    csv_path = DEMO_DIR / pattern
    if not csv_path.exists():
        return []

    events: list[NewsEvent] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            event_date = row.get("event_date", "").strip()
            title = row.get("title", "").strip()
            if not event_date or not title:
                continue

            description = row.get("description", "").strip()
            # Truncate very long descriptions for the summary field
            summary = description[:500] if description else title

            sentiment, reasoning = _parse_sentiment(row)
            events.append(NewsEvent(
                id=row.get("id", event_date),
                time=event_date,
                title=title,
                summary=summary,
                sentiment=sentiment,
                sentimentReasoning=reasoning,
                source=_source_from_url(row.get("url", "")),
                url=row.get("url") or None,
            ))

    # Sort chronologically
    events.sort(key=lambda e: e.time)
    return events


def get_demo_events(ticker: str) -> list[NewsEvent]:
    """Return demo events for a ticker (cached after first load)."""
    key = ticker.upper()
    if key not in _cache:
        _cache[key] = _load_csv(key)
    return _cache[key]
