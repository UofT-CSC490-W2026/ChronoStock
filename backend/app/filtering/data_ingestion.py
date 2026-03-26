import argparse
import json
import os
import time
from datetime import datetime

import boto3
import pandas as pd
import requests
import yfinance as yf


RAW_STOCK_PREFIX = os.environ.get("PIPELINE_RAW_STOCK_PREFIX", "raw/stock_prices")
RAW_NEWS_PREFIX = os.environ.get("PIPELINE_RAW_NEWS_PREFIX", "raw/stock_news")
RAW_REDDIT_PREFIX = os.environ.get("PIPELINE_RAW_REDDIT_PREFIX", "raw/stock_reddit")
DEFAULT_TICKERS = [
    "AMZN",
    "TSLA",
    "GOOGL",
    "META",
    "JPM",
    "NVDA",
]


def _require_bucket() -> str:
    bucket = os.environ.get("PIPELINE_S3_BUCKET", "")
    if not bucket:
        raise ValueError("Missing PIPELINE_S3_BUCKET environment variable.")
    return bucket


def _s3_client():
    region = os.environ.get("AWS_REGION")
    if region:
        return boto3.client("s3", region_name=region)
    return boto3.client("s3")


def _s3_key(prefix: str, filename: str) -> str:
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{filename}" if clean_prefix else filename


def save_to_s3(df: pd.DataFrame, prefix: str, filename: str) -> None:
    if df.empty:
        return

    bucket = _require_bucket()
    payload = df.to_csv(index=False).encode("utf-8")
    key = _s3_key(prefix, filename)
    _s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=payload,
        ContentType="text/csv",
    )
    print(f"Saved {len(df)} rows to s3://{bucket}/{key}")


def get_stockprice(
    ticker,
    start_date=None,
    end_date=None,
    save_db=True,
    save_local=False,
    local_format="csv",
    local_csv_dir="data/stock_prices",
    local_db_path="data/stock_price.db",
):
    """
    Fetches historical stock data and uploads raw CSV to S3.

    Legacy save_db/save_local args are kept for compatibility. When either is true,
    the fetched data is uploaded to the raw stock S3 prefix.
    """
    print(f"--- Fetching data for {ticker} ---")

    if start_date is None and end_date is None:
        data = yf.download(ticker, period="max", auto_adjust=True)
    else:
        data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True)

    if data.empty:
        print(f"Error: No data found for {ticker}. Please check the symbol or date range.")
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()
    data["Date"] = pd.to_datetime(data["Date"]).dt.strftime("%Y-%m-%d")
    data["ticker"] = ticker

    if save_db or save_local:
        save_to_s3(data, RAW_STOCK_PREFIX, f"{ticker}.csv")

    return data


def get_stocknews(
    ticker: str,
    start_date: str,
    end_date: str,
    api_key: str,
    save_db=True,
    save_local=False,
    local_format="csv",
    local_csv_dir="data/stock_news",
    local_db_path="data/chronostock.db",
):
    """
    Fetches news from Polygon and uploads raw CSV to S3.

    Legacy save_db/save_local args are kept for compatibility. When either is true,
    the fetched data is uploaded to the raw news S3 prefix.
    """
    print(f"--- Starting News Extraction for {ticker} ---")

    base_url = "https://api.polygon.io/v2/reference/news"
    params = {
        "ticker": ticker,
        "published_utc.gte": start_date,
        "published_utc.lte": end_date,
        "limit": 1000,
        "sort": "published_utc",
        "order": "asc",
        "apiKey": api_key,
    }

    all_records = []
    next_url = base_url
    session = requests.Session()

    while next_url:
        try:
            if next_url == base_url:
                response = session.get(next_url, params=params, timeout=15)
            else:
                if "apiKey=" not in next_url:
                    sep = "&" if "?" in next_url else "?"
                    next_url += f"{sep}apiKey={api_key}"
                response = session.get(next_url, timeout=15)

            if response.status_code == 429:
                print("Rate limit hit. Sleeping 60s...")
                time.sleep(60)
                continue

            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                break

            for article in results:
                all_records.append(
                    {
                        "id": article.get("id"),
                        "tickers": "|".join(article.get("tickers", []) or []),
                        "title": article.get("title"),
                        "published_utc": article.get("published_utc"),
                        "author": article.get("author"),
                        "description": article.get("description"),
                        "keywords": "|".join(article.get("keywords", []) or []),
                        "insights": json.dumps(article.get("insights", [])),
                        "url": article.get("article_url"),
                    }
                )

            print(f"Collected {len(results)} articles. Total: {len(all_records)}")
            next_url = data.get("next_url")

            if next_url:
                print("Sleeping 13s to respect free tier limit...")
                time.sleep(13)

        except Exception as e:
            print(f"Error: {e}")
            break

    df = pd.DataFrame(all_records)
    if not df.empty:
        df["ticker"] = ticker
        if save_db or save_local:
            save_to_s3(df, RAW_NEWS_PREFIX, f"{ticker}.csv")

    return df


def get_stock_reddit(
    query,
    start_date,
    end_date,
    tickername,
    verbose=True,
    subreddit="ValueInvesting",
    save_db=True,
    save_local=False,
    local_format="csv",
    local_csv_dir="data/stock_reddit",
    local_db_path="data/chronostock.db",
):
    """
    Scrapes Reddit data and uploads raw CSV to S3.
    """

    def _get_unix_time(date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp())

    def _fetch_pullpush_data(endpoint, subreddit, query, start_ts, end_ts):
        url = f"https://api.pullpush.io/reddit/search/{endpoint}/"
        current_after = start_ts

        while True:
            params = {
                "q": query,
                "subreddit": subreddit,
                "after": current_after,
                "before": end_ts,
                "size": 100,
                "sort": "asc",
                "sort_type": "created_utc",
            }
            try:
                response = requests.get(url, params=params, timeout=10)
                data = response.json().get("data", [])
                if not data:
                    break
                yield data
                current_after = data[-1]["created_utc"] + 1
                time.sleep(0.5)
            except Exception as e:
                print(f"Error fetching {endpoint}: {e}")
                break

    start_ts = _get_unix_time(start_date)
    end_ts = _get_unix_time(end_date)
    all_data = []

    if verbose:
        print(f"--- Scraper Started: r/{subreddit} | Query: '{query}' ---")

    if verbose:
        print("> Fetching Submissions...")
    for batch in _fetch_pullpush_data("submission", subreddit, query, start_ts, end_ts):
        for post in batch:
            all_data.append(
                {
                    "Type": "Submission",
                    "Date": datetime.fromtimestamp(post["created_utc"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "Author": post.get("author", "[deleted]"),
                    "Score": post.get("score", 0),
                    "Title": post.get("title", ""),
                    "Body": post.get("selftext", ""),
                    "Permalink": post.get("full_link", f"https://reddit.com{post.get('permalink', '')}"),
                }
            )
        if verbose:
            print(f"  Total rows: {len(all_data)}", end="\r")

    if verbose:
        print("\n> Fetching Comments...")
    for batch in _fetch_pullpush_data("comment", subreddit, query, start_ts, end_ts):
        for comment in batch:
            link_id = comment.get("link_id", "").split("_")[-1]
            comm_id = comment.get("id", "")

            all_data.append(
                {
                    "Type": "Comment",
                    "Date": datetime.fromtimestamp(comment["created_utc"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "Author": comment.get("author", "[deleted]"),
                    "Score": comment.get("score", 0),
                    "Title": "",
                    "Body": comment.get("body", ""),
                    "Permalink": f"https://www.reddit.com/comments/{link_id}/_/{comm_id}/",
                }
            )
        if verbose:
            print(f"  Total rows: {len(all_data)}", end="\r")

    df = pd.DataFrame(all_data)
    if not df.empty:
        df["Body"] = df["Body"].fillna("").astype(str).str.replace("\n", " ")
        df["Title"] = df["Title"].fillna("").astype(str).str.replace("\n", " ")
        df["ticker"] = tickername

        if save_db or save_local:
            save_to_s3(df, RAW_REDDIT_PREFIX, f"{tickername}.csv")
    else:
        if verbose:
            print("\n\nNo data found.")

    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch raw stock/news/reddit inputs and upload them to S3.")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--start-date", default="2016-02-16")
    parser.add_argument("--end-date", default="2026-03-20")
    parser.add_argument("--with-reddit", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    api_key = os.environ.get("POLYGON_API_KEY", "")

    for ticker in tickers:
        print(f"\nProcessing {ticker}...")

        try:
            get_stockprice(ticker, args.start_date, args.end_date, save_db=False, save_local=True)
        except Exception as e:
            print(f"Price error for {ticker}: {e}")

        try:
            get_stocknews(ticker, args.start_date, args.end_date, api_key=api_key, save_db=False, save_local=True)
        except Exception as e:
            print(f"News error for {ticker}: {e}")

        if args.with_reddit:
            try:
                get_stock_reddit(
                    query=f"{ticker.lower()}",
                    start_date=args.start_date,
                    end_date=args.end_date,
                    tickername=ticker,
                    save_db=False,
                    save_local=True,
                )
            except Exception as e:
                print(f"Reddit error for {ticker}: {e}")

    print("\nIngestion complete.")
