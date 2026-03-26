import argparse
import csv
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3

from ..database import PH, cursor, get_conn, init_db


def _require_env(name: str, current: str | None) -> str:
    value = current or os.environ.get(name, "")
    if not value:
        raise ValueError(f"Missing required setting: {name}")
    return value


def _s3_client():
    region = os.environ.get("AWS_REGION")
    if region:
        return boto3.client("s3", region_name=region)
    return boto3.client("s3")


def _download_file(bucket: str, key: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _s3_client().download_file(bucket, key, str(destination))


def _upload_file(source: Path, bucket: str, key: str) -> None:
    _s3_client().upload_file(str(source), bucket, key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run event detection + LLM filtering for one ticker using S3-backed inputs and outputs."
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol, for example NVDA")
    parser.add_argument("--bucket", default=os.environ.get("PIPELINE_S3_BUCKET"))
    parser.add_argument(
        "--stock-prefix",
        default=os.environ.get("PIPELINE_STOCK_PREFIX", "raw/stock_prices"),
        help="S3 prefix containing per-ticker stock CSVs.",
    )
    parser.add_argument(
        "--market-prefix",
        default=os.environ.get("PIPELINE_MARKET_PREFIX", "raw/stock_prices"),
        help="S3 prefix containing benchmark CSVs.",
    )
    parser.add_argument(
        "--news-prefix",
        default=os.environ.get("PIPELINE_NEWS_PREFIX", "clean/stock_news_cleaned"),
        help="S3 prefix containing cleaned news CSVs.",
    )
    parser.add_argument(
        "--events-prefix",
        default=os.environ.get("PIPELINE_EVENTS_PREFIX", "events/raw"),
        help="S3 prefix where raw event-news matches are uploaded.",
    )
    parser.add_argument(
        "--filtered-prefix",
        default=os.environ.get("PIPELINE_FILTERED_PREFIX", "events/filtered"),
        help="S3 prefix where LLM-filtered event CSVs are uploaded.",
    )
    parser.add_argument(
        "--benchmark-ticker",
        default=os.environ.get("PIPELINE_BENCHMARK_TICKER", "^DJI"),
        help="Benchmark ticker CSV used by CAR.",
    )
    parser.add_argument("--start-date", default=os.environ.get("PIPELINE_START_DATE"))
    parser.add_argument("--end-date", default=os.environ.get("PIPELINE_END_DATE"))
    parser.add_argument("--news-window-days", type=int, default=int(os.environ.get("PIPELINE_NEWS_WINDOW_DAYS", "2")))
    parser.add_argument("--pen", type=int, default=int(os.environ.get("PIPELINE_PEN", "4")))
    parser.add_argument("--window-left", type=int, default=int(os.environ.get("PIPELINE_WINDOW_LEFT", "3")))
    parser.add_argument("--window-right", type=int, default=int(os.environ.get("PIPELINE_WINDOW_RIGHT", "3")))
    parser.add_argument("--top-k-events", type=int, default=int(os.environ.get("PIPELINE_TOP_K_EVENTS", "25")))
    parser.add_argument("--llm-model", default=os.environ.get("LLM_MODEL"))
    parser.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL"))
    parser.add_argument("--llm-api-key", default=os.environ.get("LLM_API_KEY"))
    parser.add_argument("--llm-batch-size", type=int, default=int(os.environ.get("PIPELINE_LLM_BATCH_SIZE", "30")))
    parser.add_argument("--llm-max-tokens", type=int, default=int(os.environ.get("PIPELINE_LLM_MAX_TOKENS", "256")))
    parser.add_argument("--llm-temperature", type=float, default=float(os.environ.get("PIPELINE_LLM_TEMPERATURE", "0.0")))
    return parser.parse_args()


def _build_s3_key(prefix: str, filename: str) -> str:
    clean_prefix = prefix.strip("/")
    if not clean_prefix:
        return filename
    return f"{clean_prefix}/{filename}"


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


def _load_filtered_csv(path: Path, default_ticker: str) -> list[dict]:
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
                "s3_event_pipeline",
                "single_ticker",
                started_at,
                completed_at,
                status,
                details,
            ),
        )


def _write_filtered_results_to_db(filtered_csv_path: Path, ticker: str) -> int:
    init_db()
    records = _load_filtered_csv(filtered_csv_path, default_ticker=ticker)
    started_at = _now_iso()
    run_id = str(uuid.uuid4())
    conn = get_conn()
    try:
        inserted = _replace_ticker_events(conn, ticker, records, started_at)
        _record_pipeline_run(
            conn,
            run_id=run_id,
            status="completed",
            started_at=started_at,
            completed_at=_now_iso(),
            details=json.dumps({"ticker": ticker, "rows": inserted}),
        )
        conn.commit()
        return inserted
    except Exception as exc:
        conn.rollback()
        try:
            _record_pipeline_run(
                conn,
                run_id=run_id,
                status="failed",
                started_at=started_at,
                completed_at=_now_iso(),
                details=json.dumps({"ticker": ticker, "error": str(exc)}),
            )
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def run_pipeline_for_ticker(
    *,
    ticker: str,
    bucket: str,
    stock_prefix: str = "raw/stock_prices",
    market_prefix: str = "raw/stock_prices",
    news_prefix: str = "clean/stock_news_cleaned",
    events_prefix: str = "events/raw",
    filtered_prefix: str = "events/filtered",
    benchmark_ticker: str = "^DJI",
    start_date: str | None = None,
    end_date: str | None = None,
    news_window_days: int = 2,
    pen: int = 4,
    window_left: int = 3,
    window_right: int = 3,
    top_k_events: int = 25,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_batch_size: int = 30,
    llm_max_tokens: int = 256,
    llm_temperature: float = 0.0,
) -> int:
    ticker = ticker.upper()
    benchmark = benchmark_ticker

    stock_key = _build_s3_key(stock_prefix, f"{ticker}.csv")
    market_key = _build_s3_key(market_prefix, f"{benchmark}.csv")
    news_key = _build_s3_key(news_prefix, f"{ticker}.csv")
    raw_output_key = _build_s3_key(events_prefix, f"{ticker}.csv")
    filtered_output_key = _build_s3_key(filtered_prefix, f"{ticker}_event_news_llm_filtered.csv")

    try:
        from ..event_detection import EventDetector
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Event pipeline dependency is missing. "
            "backend/app/event_detection.py imports CARCalculator from car.py, "
            "but that module is not present in this repo."
        ) from exc

    from ..llm import ChatCompletionsLLM, NewsLLMFilter, load_events

    llm_api_key = _require_env("LLM_API_KEY", llm_api_key)
    llm_model = _require_env("LLM_MODEL", llm_model)

    temp_root = Path(tempfile.mkdtemp(prefix=f"event-pipeline-{ticker.lower()}-"))
    try:
        stock_path = temp_root / "inputs" / "stock_prices" / f"{ticker}.csv"
        market_path = temp_root / "inputs" / "stock_prices" / f"{benchmark}.csv"
        news_path = temp_root / "inputs" / "stock_news_cleaned" / f"{ticker}.csv"
        results_dir = temp_root / "outputs" / "events"
        filtered_dir = temp_root / "outputs" / "filtered"

        print(f"Downloading s3://{bucket}/{stock_key}")
        _download_file(bucket, stock_key, stock_path)
        print(f"Downloading s3://{bucket}/{market_key}")
        _download_file(bucket, market_key, market_path)
        print(f"Downloading s3://{bucket}/{news_key}")
        _download_file(bucket, news_key, news_path)

        detector = EventDetector(
            ticker=ticker,
            stock_path=str(stock_path),
            market_path=str(market_path),
            news_path=str(news_path),
            results_dir=str(results_dir),
            start_time=start_date,
            end_time=end_date,
            news_window_days=news_window_days,
            pen=pen,
            window_left=window_left,
            window_right=window_right,
            top_k_events=top_k_events,
        )

        _, raw_results_df = detector.run()
        raw_output_path = results_dir / f"{ticker}.csv"
        if not raw_output_path.exists():
            raise RuntimeError(f"Expected raw output was not created: {raw_output_path}")

        llm = ChatCompletionsLLM(
            api_key=llm_api_key,
            model=llm_model,
            base_url=llm_base_url,
            max_tokens=llm_max_tokens,
            temperature=llm_temperature,
        )
        filter_pipeline = NewsLLMFilter(llm, batch_size=llm_batch_size)

        events_df = load_events(str(raw_output_path))
        selected_ids = filter_pipeline.run(
            events_df,
            start_date=start_date,
            end_date=end_date,
        )
        filtered_df = events_df[events_df["id"].isin(selected_ids)].copy()
        filtered_df.sort_values("event_date", inplace=True)

        filtered_dir.mkdir(parents=True, exist_ok=True)
        filtered_output_path = filtered_dir / f"{ticker}_event_news_llm_filtered.csv"
        filtered_df.to_csv(filtered_output_path, index=False)

        print(f"Uploading raw results to s3://{bucket}/{raw_output_key}")
        _upload_file(raw_output_path, bucket, raw_output_key)
        print(f"Uploading filtered results to s3://{bucket}/{filtered_output_key}")
        _upload_file(filtered_output_path, bucket, filtered_output_key)
        inserted = _write_filtered_results_to_db(filtered_output_path, ticker)

        print(f"Completed pipeline for {ticker}.")
        print(f"Raw matched rows: {len(raw_results_df)}")
        print(f"Filtered rows: {len(filtered_df)}")
        print(f"Rows written to database: {inserted}")
        return inserted
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> None:
    args = parse_args()
    bucket = _require_env("PIPELINE_S3_BUCKET", args.bucket)
    run_pipeline_for_ticker(
        ticker=args.ticker,
        bucket=bucket,
        stock_prefix=args.stock_prefix,
        market_prefix=args.market_prefix,
        news_prefix=args.news_prefix,
        events_prefix=args.events_prefix,
        filtered_prefix=args.filtered_prefix,
        benchmark_ticker=args.benchmark_ticker,
        start_date=args.start_date,
        end_date=args.end_date,
        news_window_days=args.news_window_days,
        pen=args.pen,
        window_left=args.window_left,
        window_right=args.window_right,
        top_k_events=args.top_k_events,
        llm_model=args.llm_model,
        llm_base_url=args.llm_base_url,
        llm_api_key=args.llm_api_key,
        llm_batch_size=args.llm_batch_size,
        llm_max_tokens=args.llm_max_tokens,
        llm_temperature=args.llm_temperature,
    )


if __name__ == "__main__":
    main()
