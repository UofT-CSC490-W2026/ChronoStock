"""
Load stored key events from the database and convert them to NewsEvent objects.
"""

from .database import PH, cursor, get_conn
from .models import NewsEvent


def get_demo_events(ticker: str) -> list[NewsEvent]:
    conn = get_conn()
    try:
        with cursor(conn) as cur:
            cur.execute(
                f"""
                SELECT event_id, event_date, title, summary, sentiment,
                       sentiment_reasoning, source, url
                FROM stock_events
                WHERE ticker = {PH}
                ORDER BY event_date ASC, abs_car DESC, published_utc DESC
                """,
                (ticker.upper(),),
            )
            rows = cur.fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    events: list[NewsEvent] = []
    for row in rows:
        data = row if isinstance(row, dict) else dict(row)
        events.append(
            NewsEvent(
                id=data.get("event_id") or data.get("event_date", ""),
                time=data.get("event_date", ""),
                title=data.get("title", ""),
                summary=data.get("summary") or data.get("title") or "",
                sentiment=data.get("sentiment") or "neutral",
                sentimentReasoning=data.get("sentiment_reasoning"),
                source=data.get("source") or "News",
                url=data.get("url"),
            )
        )
    return events
