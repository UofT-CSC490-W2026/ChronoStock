import argparse
import io
import os
from datetime import datetime, timedelta, timezone

import boto3
import pandas as pd

from .data_cleaning import (
    CLEAN_NEWS_PREFIX,
    DEFAULT_TICKERS as CLEANING_KEYWORDS,
    clean_news_dataframe,
    save_cleaned_to_s3,
)
from .data_ingestion import (
    DEFAULT_TICKERS as INGESTION_DEFAULT_TICKERS,
    RAW_NEWS_PREFIX,
    RAW_STOCK_PREFIX,
    get_stocknews,
    get_stockprice,
    save_to_s3,
)
from .run_s3_event_pipeline import run_pipeline_for_ticker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the monthly S3-backed event pipeline for a set of tickers.")
    parser.add_argument("--tickers", default=",".join(INGESTION_DEFAULT_TICKERS))
    parser.add_argument("--start-date", default=os.environ.get("PIPELINE_START_DATE"))
    parser.add_argument("--end-date", default=os.environ.get("PIPELINE_END_DATE"))
    parser.add_argument("--benchmark-ticker", default=os.environ.get("PIPELINE_BENCHMARK_TICKER", "^DJI"))
    parser.add_argument(
        "--incremental-days",
        type=int,
        default=int(os.environ.get("PIPELINE_INCREMENTAL_DAYS", "30")),
        help="Recent news window to ingest and clean incrementally before full event rerun.",
    )
    parser.add_argument("--skip-ingestion", action="store_true")
    parser.add_argument("--skip-cleaning", action="store_true")
    parser.add_argument("--skip-event-pipeline", action="store_true")
    return parser.parse_args()


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"Missing required setting: {name}")
    return value


def _s3_client():
    region = os.environ.get("AWS_REGION")
    if region:
        return boto3.client("s3", region_name=region)
    return boto3.client("s3")


def _read_s3_csv_or_empty(bucket: str, key: str) -> pd.DataFrame:
    try:
        response = _s3_client().get_object(Bucket=bucket, Key=key)
    except _s3_client().exceptions.NoSuchKey:
        return pd.DataFrame()
    except Exception as exc:
        code = getattr(getattr(exc, "response", {}), "get", lambda _k, _d=None: _d)("Error", {}).get("Code")
        if code in {"NoSuchKey", "404"}:
            return pd.DataFrame()
        raise
    return pd.read_csv(io.BytesIO(response["Body"].read()))


def _date_range_for_incremental(end_date: str, incremental_days: int) -> tuple[str, str]:
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_dt = end_dt - timedelta(days=max(1, incremental_days))
    return start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")


def _rolling_five_year_start(end_date: str) -> str:
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start_dt = end_dt - timedelta(days=365 * 5)
    return start_dt.strftime("%Y-%m-%d")


def _merge_raw_news(existing: pd.DataFrame, fresh: pd.DataFrame, ticker: str) -> pd.DataFrame:
    frames = []
    if not existing.empty:
        frames.append(existing)
    if not fresh.empty:
        frames.append(fresh)
    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    if "ticker" not in merged.columns:
        merged["ticker"] = ticker
    else:
        merged["ticker"] = merged["ticker"].fillna(ticker)

    if "published_utc" in merged.columns:
        merged["published_utc"] = pd.to_datetime(merged["published_utc"], utc=True, errors="coerce")
        merged = merged.sort_values(["published_utc", "id"], ascending=[True, True], na_position="last")

    if "id" in merged.columns:
        merged = merged.drop_duplicates(subset=["id"], keep="last")
    else:
        merged = merged.drop_duplicates()

    if "published_utc" in merged.columns:
        merged["published_utc"] = merged["published_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return merged.reset_index(drop=True)


def _merge_clean_news(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    frames = []
    if not existing.empty:
        frames.append(existing)
    if not fresh.empty:
        frames.append(fresh)
    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    if "published_utc" in merged.columns:
        merged["published_utc"] = pd.to_datetime(merged["published_utc"], utc=True, errors="coerce")
        merged = merged.sort_values(["published_utc", "id"], ascending=[True, True], na_position="last")

    if "id" in merged.columns:
        merged = merged.drop_duplicates(subset=["id"], keep="last")
    else:
        merged = merged.drop_duplicates()

    if "published_utc" in merged.columns:
        merged["published_utc"] = merged["published_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return merged.reset_index(drop=True)


def main() -> None:
    args = parse_args()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    bucket = _require_env("PIPELINE_S3_BUCKET")
    polygon_api_key = _require_env("POLYGON_API_KEY")
    end_date = args.end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = args.start_date or _rolling_five_year_start(end_date)
    incremental_start, incremental_end = _date_range_for_incremental(end_date, args.incremental_days)

    if not args.skip_ingestion:
        print(f"Refreshing benchmark {args.benchmark_ticker} price history...")
        get_stockprice(args.benchmark_ticker, start_date, end_date, save_db=False, save_local=True)

        for ticker in tickers:
            print(f"\n[monthly] Price refresh for {ticker}")
            get_stockprice(ticker, start_date, end_date, save_db=False, save_local=True)

            print(f"\n[monthly] Incremental news ingestion for {ticker}: {incremental_start} -> {incremental_end}")
            existing_raw = _read_s3_csv_or_empty(bucket, f"{RAW_NEWS_PREFIX}/{ticker}.csv")
            fresh_raw = get_stocknews(
                ticker,
                incremental_start,
                incremental_end,
                api_key=polygon_api_key,
                save_db=False,
                save_local=False,
            )
            merged_raw = _merge_raw_news(existing_raw, fresh_raw, ticker)
            if not merged_raw.empty:
                save_to_s3(merged_raw, RAW_NEWS_PREFIX, f"{ticker}.csv")

    if not args.skip_cleaning:
        for ticker in tickers:
            keywords = CLEANING_KEYWORDS.get(ticker)
            if not keywords:
                print(f"Skipping cleaning for {ticker}: no keyword config found.")
                continue

            print(f"\n[monthly] Incremental cleaning merge for {ticker}")
            raw_df = _read_s3_csv_or_empty(bucket, f"{RAW_NEWS_PREFIX}/{ticker}.csv")
            if raw_df.empty:
                print(f"Skipping cleaning for {ticker}: no raw news found.")
                continue

            raw_df["published_utc"] = pd.to_datetime(raw_df["published_utc"], utc=True, errors="coerce")
            cutoff = pd.Timestamp(incremental_start, tz="UTC")
            incremental_raw = raw_df[raw_df["published_utc"] >= cutoff].copy()
            if incremental_raw.empty:
                print(f"No incremental raw news to clean for {ticker}.")
                continue

            incremental_raw["published_utc"] = incremental_raw["published_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            fresh_clean = clean_news_dataframe(incremental_raw, keywords)
            existing_clean = _read_s3_csv_or_empty(bucket, f"{CLEAN_NEWS_PREFIX}/{ticker}.csv")
            merged_clean = _merge_clean_news(existing_clean, fresh_clean)
            if not merged_clean.empty:
                save_cleaned_to_s3(merged_clean, ticker)

    if not args.skip_event_pipeline:
        llm_api_key = _require_env("LLM_API_KEY")
        llm_model = os.environ.get("LLM_MODEL")
        llm_base_url = os.environ.get("LLM_BASE_URL")

        for ticker in tickers:
            print(f"\n[monthly] Event pipeline for {ticker}")
            run_pipeline_for_ticker(
                ticker=ticker,
                bucket=bucket,
                stock_prefix=os.environ.get("PIPELINE_STOCK_PREFIX", "raw/stock_prices"),
                market_prefix=os.environ.get("PIPELINE_MARKET_PREFIX", "raw/stock_prices"),
                news_prefix=os.environ.get("PIPELINE_NEWS_PREFIX", "clean/stock_news_cleaned"),
                events_prefix=os.environ.get("PIPELINE_EVENTS_PREFIX", "events/raw"),
                filtered_prefix=os.environ.get("PIPELINE_FILTERED_PREFIX", "events/filtered"),
                benchmark_ticker=args.benchmark_ticker,
                start_date=start_date,
                end_date=end_date,
                news_window_days=int(os.environ.get("PIPELINE_NEWS_WINDOW_DAYS", "2")),
                pen=int(os.environ.get("PIPELINE_PEN", "4")),
                window_left=int(os.environ.get("PIPELINE_WINDOW_LEFT", "3")),
                window_right=int(os.environ.get("PIPELINE_WINDOW_RIGHT", "3")),
                top_k_events=int(os.environ.get("PIPELINE_TOP_K_EVENTS", "25")),
                llm_model=llm_model,
                llm_base_url=llm_base_url,
                llm_api_key=llm_api_key,
                llm_batch_size=int(os.environ.get("PIPELINE_LLM_BATCH_SIZE", "30")),
                llm_max_tokens=int(os.environ.get("PIPELINE_LLM_MAX_TOKENS", "256")),
                llm_temperature=float(os.environ.get("PIPELINE_LLM_TEMPERATURE", "0.0")),
            )

    print(f"\nMonthly event pipeline complete for {len(tickers)} ticker(s).")


if __name__ == "__main__":
    main()
