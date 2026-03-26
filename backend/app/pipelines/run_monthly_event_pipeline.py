import argparse
import os

from .data_cleaning import DEFAULT_TICKERS as CLEANING_KEYWORDS, clean_stock_news
from .data_ingestion import DEFAULT_TICKERS as INGESTION_DEFAULT_TICKERS, get_stocknews, get_stockprice
from .run_s3_event_pipeline import run_pipeline_for_ticker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the monthly S3-backed event pipeline for a set of tickers.")
    parser.add_argument("--tickers", default=",".join(INGESTION_DEFAULT_TICKERS))
    parser.add_argument("--start-date", default=os.environ.get("PIPELINE_START_DATE", "2016-02-16"))
    parser.add_argument("--end-date", default=os.environ.get("PIPELINE_END_DATE", "2026-03-20"))
    parser.add_argument("--benchmark-ticker", default=os.environ.get("PIPELINE_BENCHMARK_TICKER", "^DJI"))
    parser.add_argument("--skip-ingestion", action="store_true")
    parser.add_argument("--skip-cleaning", action="store_true")
    parser.add_argument("--skip-event-pipeline", action="store_true")
    return parser.parse_args()


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"Missing required setting: {name}")
    return value


def main() -> None:
    args = parse_args()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    bucket = _require_env("PIPELINE_S3_BUCKET")
    polygon_api_key = _require_env("POLYGON_API_KEY")

    if not args.skip_ingestion:
        print(f"Refreshing benchmark {args.benchmark_ticker} price history...")
        get_stockprice(args.benchmark_ticker, args.start_date, args.end_date, save_db=False, save_local=True)

        for ticker in tickers:
            print(f"\n[monthly] Ingestion for {ticker}")
            get_stockprice(ticker, args.start_date, args.end_date, save_db=False, save_local=True)
            get_stocknews(ticker, args.start_date, args.end_date, api_key=polygon_api_key, save_db=False, save_local=True)

    if not args.skip_cleaning:
        for ticker in tickers:
            keywords = CLEANING_KEYWORDS.get(ticker)
            if not keywords:
                print(f"Skipping cleaning for {ticker}: no keyword config found.")
                continue
            print(f"\n[monthly] Cleaning for {ticker}")
            clean_stock_news(ticker, keywords, source="s3", output="s3")

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
                start_date=args.start_date,
                end_date=args.end_date,
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
