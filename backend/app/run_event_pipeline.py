import argparse
import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .database import PH, cursor, get_conn, init_db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_from_url(url: str) -> str:
    if "marketwatch.com" in url:
        return "MarketWatch"
    if "benzinga.com" in url:
        return "Benzinga"
    if "fool.com" in url:
        return "Motley Fool"
    if "globenewswire.com" in url:
        return "GlobeNewsWire"
    return "News"


def _parse_sentiment(row: dict[str, str]) -> tuple[str, str | None]:
    ticker = (row.get("ticker") or "").upper()
    raw = row.get("insights", "")
    if raw and raw != "[]":
        try:
            insights = json.loads(raw)
            for entry in insights:
                if entry.get("ticker", "").upper() == ticker:
                    sentiment = entry.get("sentiment", "").lower()
                    reasoning = entry.get("sentiment_reasoning") or None
                    if sentiment in ("positive", "negative", "neutral"):
                        return sentiment, reasoning
        except (json.JSONDecodeError, TypeError):
            pass

    try:
        car = float(row.get("car", 0) or 0)
    except (TypeError, ValueError):
        car = 0.0
    return ("positive" if car > 0 else "negative" if car < 0 else "neutral"), None


def _load_filtered_csv(path: Path, default_ticker: str | None = None) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    loaded: list[dict] = []
    for row in rows:
        ticker = (row.get("ticker") or default_ticker or "").strip().upper()
        event_date = (row.get("event_date") or "").strip()
        title = (row.get("title") or "").strip()
        if not ticker or not event_date or not title:
            continue

        sentiment, reasoning = _parse_sentiment(row)
        description = (row.get("description") or "").strip()
        summary = description[:500] if description else title
        url = (row.get("url") or "").strip() or None
        event_id = (row.get("id") or "").strip() or f"{ticker}-{event_date}-{uuid.uuid4().hex[:8]}"

        try:
            car = float(row.get("car", "") or 0)
        except (TypeError, ValueError):
            car = None
        try:
            abs_car = float(row.get("abs_car", "") or 0)
        except (TypeError, ValueError):
            abs_car = None

        loaded.append(
            {
                "ticker": ticker,
                "event_id": event_id,
                "event_date": event_date,
                "published_utc": (row.get("published_utc") or "").strip() or None,
                "title": title,
                "summary": summary,
                "sentiment": sentiment,
                "sentiment_reasoning": reasoning,
                "source": _source_from_url(url or ""),
                "url": url,
                "car": car,
                "abs_car": abs_car,
            }
        )
    return loaded


def _replace_ticker_events(conn, ticker: str, records: list[dict], pipeline_run_at: str) -> int:
    with cursor(conn) as cur:
        cur.execute(f"DELETE FROM stock_events WHERE ticker = {PH}", (ticker,))
        for record in records:
            cur.execute(
                f"""
                INSERT INTO stock_events (
                    ticker, event_id, event_date, published_utc, title, summary,
                    sentiment, sentiment_reasoning, source, url, car, abs_car,
                    pipeline_run_at
                ) VALUES (
                    {PH}, {PH}, {PH}, {PH}, {PH}, {PH},
                    {PH}, {PH}, {PH}, {PH}, {PH}, {PH},
                    {PH}
                )
                """,
                (
                    record["ticker"],
                    record["event_id"],
                    record["event_date"],
                    record["published_utc"],
                    record["title"],
                    record["summary"],
                    record["sentiment"],
                    record["sentiment_reasoning"],
                    record["source"],
                    record["url"],
                    record["car"],
                    record["abs_car"],
                    pipeline_run_at,
                ),
            )
    return len(records)


def _record_pipeline_run(conn, run_id: str, status: str, started_at: str, completed_at: str | None, details: str) -> None:
    with cursor(conn) as cur:
        cur.execute(
            f"""
            INSERT INTO pipeline_runs (
                run_id, pipeline_name, scope, started_at, completed_at, status, details
            ) VALUES ({PH}, {PH}, {PH}, {PH}, {PH}, {PH}, {PH})
            """,
            (
                run_id,
                "event_backfill",
                "manual",
                started_at,
                completed_at,
                status,
                details,
            ),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load filtered event CSV data into stock_events.")
    parser.add_argument(
        "--input-csv",
        action="append",
        default=[],
        help="Filtered event CSV file to import. Repeat for multiple files.",
    )
    parser.add_argument(
        "--demodata-dir",
        default=None,
        help="Optional directory of *_event_news_llm_filtered.csv files to import.",
    )
    parser.add_argument(
        "--ticker",
        default=None,
        help="Ticker override when the CSV does not contain a ticker column.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()

    input_paths: list[Path] = [Path(p) for p in args.input_csv]
    if args.demodata_dir:
        input_paths.extend(sorted(Path(args.demodata_dir).glob("*_event_news_llm_filtered.csv")))

    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in input_paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_paths.append(path)

    if not unique_paths:
        raise SystemExit("No input files provided. Use --input-csv or --demodata-dir.")

    grouped_records: dict[str, list[dict]] = {}
    for path in unique_paths:
        if not path.exists():
            raise SystemExit(f"Input file not found: {path}")
        records = _load_filtered_csv(path, default_ticker=args.ticker)
        for record in records:
            grouped_records.setdefault(record["ticker"], []).append(record)

    if not grouped_records:
        raise SystemExit("No valid event rows found in the provided input.")

    started_at = _now_iso()
    completed_at = None
    run_id = str(uuid.uuid4())
    pipeline_run_at = started_at

    conn = get_conn()
    try:
        summary: dict[str, int] = {}
        for ticker, records in grouped_records.items():
            summary[ticker] = _replace_ticker_events(conn, ticker, records, pipeline_run_at)

        completed_at = _now_iso()
        _record_pipeline_run(
            conn,
            run_id=run_id,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            details=json.dumps({"tickers": summary}),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        try:
            _record_pipeline_run(
                conn,
                run_id=run_id,
                status="failed",
                started_at=started_at,
                completed_at=_now_iso(),
                details=json.dumps({"error": str(exc)}),
            )
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        conn.close()

    print(f"Imported events for {len(grouped_records)} ticker(s).")
    for ticker, records in grouped_records.items():
        print(f"{ticker}: {len(records)} event row(s)")


if __name__ == "__main__":
    main()
