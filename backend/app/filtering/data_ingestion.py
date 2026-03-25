import json

import yfinance as yf
import time
from datetime import datetime
from typing import Optional
import pandas as pd
import os
import requests
from sqlalchemy import create_engine, text
# from db import engine

from sqlalchemy import inspect, text


def save_to_local_csv(df, output_dir="data/stock_prices", filename=None):
    """Saves a DataFrame to a local CSV file."""

    if df.empty:
        return

    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, filename) if filename else os.path.join(output_dir, "stock_prices.csv")
    df.to_csv(csv_path, index=False)
    print(f"Saved {len(df)} rows locally to {csv_path}")


def append_to_local_csv(df, output_dir, filename, dedupe_subset=None):
    """Appends rows to a local CSV, optionally dropping duplicates."""

    if df.empty:
        return

    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, filename)

    if os.path.exists(csv_path):
        existing_df = pd.read_csv(csv_path)
        combined_df = pd.concat([existing_df, df], ignore_index=True)
    else:
        combined_df = df.copy()

    if dedupe_subset:
        combined_df = combined_df.drop_duplicates(subset=dedupe_subset, keep="last")

    combined_df.to_csv(csv_path, index=False)
    print(f"Saved {len(combined_df)} total rows locally to {csv_path}")


def save_to_local_db(df, table_name, db_path="data/chronostock.db", ticker_col=None, ticker_val=None):
    """Saves a DataFrame to a local SQLite database."""

    if df.empty:
        return

    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    local_engine = create_engine(f"sqlite:///{db_path}")

    try:
        with local_engine.begin() as conn:
            inspector = inspect(conn)
            table_exists = inspector.has_table(table_name)

            if table_exists and ticker_col and ticker_val:
                print(f"Cleaning existing local data for {ticker_val} in {table_name}...")
                conn.execute(
                    text(f'DELETE FROM {table_name} WHERE "{ticker_col}" = :t'),
                    {"t": ticker_val}
                )

            df.to_sql(table_name, conn, if_exists="append", index=False)
            print(f"Saved {len(df)} rows to local DB table {table_name} at {db_path}")

    except Exception as e:
        print(f"Error saving to local DB: {e}")


def save_to_rds(df, table_name, ticker_col=None, ticker_val=None):
    """Saves DataFrame to RDS. Automatically creates table if not exists."""

    if df.empty:
        return

    # try:
    #     with engine.begin() as conn:
    #         inspector = inspect(conn)
    #         table_exists = inspector.has_table(table_name)

    #         if table_exists:
    #             if ticker_col and ticker_val:
    #                 print(f"Cleaning existing data for {ticker_val} in {table_name}...")
    #                 conn.execute(
    #                     text(f'DELETE FROM {table_name} WHERE "{ticker_col}" = :t'),
    #                     {"t": ticker_val}
    #                 )
    #         else:
    #             print(f"Table {table_name} does not exist. It will be created.")

    #         df.to_sql(table_name, conn, if_exists='append', index=False)
    #         print(f"Saved {len(df)} rows to RDS table: {table_name}")

    # except Exception as e:
    #     print(f"Error saving to RDS: {e}")


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
    Fetches historical stock data.

    If both start_date and end_date are omitted, fetches the full history
    available from Yahoo Finance for the ticker.

    When save_local is enabled, data is stored as CSV by default.
    Set local_format="db" to save into a local SQLite database instead.
    """
    print(f"--- Fetching data for {ticker} ---")

    if start_date is None and end_date is None:
        data = yf.download(ticker, period="max", auto_adjust=True)
    else:
        data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True)

    if data.empty:
        print(f"Error: No data found for {ticker}. Please check the symbol or date range.")
        return

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.reset_index()
    data["ticker"] = ticker

    if save_db:
        save_to_rds(data, "stock_prices", ticker_col="ticker", ticker_val=ticker)

    if save_local:
        if local_format == "csv":
            save_to_local_csv(data, output_dir=local_csv_dir, filename=f"{ticker}.csv")
        elif local_format == "db":
            save_to_local_db(
                data,
                "stock_prices",
                db_path=local_db_path,
                ticker_col="ticker",
                ticker_val=ticker,
            )
        else:
            raise ValueError("local_format must be either 'csv' or 'db'")

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
    Fetches news from Massive/Polygon API with strict rate limiting for Free Tier.
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
        "apiKey": api_key
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

            results = data.get('results', [])
            if not results:
                break

            for article in results:
                all_records.append({
                    "id": article.get('id'),
                    "tickers": "|".join(article.get('tickers', []) or []),
                    "title": article.get('title'),
                    "published_utc": article.get('published_utc'),
                    "author": article.get('author'),
                    "description": article.get('description'),
                    "keywords": "|".join(article.get('keywords', []) or []),
                    "insights": json.dumps(article.get('insights', [])),
                    "url": article.get('article_url')
                })

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
        df['ticker'] = ticker
        if save_db:
            save_to_rds(df, "stock_news")
        if save_local:
            if local_format == "csv":
                append_to_local_csv(
                    df,
                    output_dir=local_csv_dir,
                    filename=f"{ticker}.csv",
                    dedupe_subset=["id"],
                )
            elif local_format == "db":
                save_to_local_db(
                    df,
                    "stock_news",
                    db_path=local_db_path,
                )
            else:
                raise ValueError("local_format must be either 'csv' or 'db'")

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
    Scrapes Reddit data into a Pandas DataFrame and saves to CSV.

    Returns:
        pd.DataFrame: The scraped data containing posts and comments.
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
                "sort_type": "created_utc"
            }
            try:
                response = requests.get(url, params=params, timeout=10)
                data = response.json().get('data', [])
                if not data:
                    break
                yield data
                current_after = data[-1]['created_utc'] + 1
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
            all_data.append({
                "Type": "Submission",
                "Date": datetime.fromtimestamp(post['created_utc']).strftime('%Y-%m-%d %H:%M:%S'),
                "Author": post.get('author', '[deleted]'),
                "Score": post.get('score', 0),
                "Title": post.get('title', ''),
                "Body": post.get('selftext', ''),
                "Permalink": post.get('full_link', f"https://reddit.com{post.get('permalink', '')}")
            })
        if verbose:
            print(f"  Total rows: {len(all_data)}", end='\r')

    if verbose:
        print("\n> Fetching Comments...")
    for batch in _fetch_pullpush_data("comment", subreddit, query, start_ts, end_ts):
        for comment in batch:
            link_id = comment.get('link_id', '').split('_')[-1]
            comm_id = comment.get('id', '')

            all_data.append({
                "Type": "Comment",
                "Date": datetime.fromtimestamp(comment['created_utc']).strftime('%Y-%m-%d %H:%M:%S'),
                "Author": comment.get('author', '[deleted]'),
                "Score": comment.get('score', 0),
                "Title": "",
                "Body": comment.get('body', ''),
                "Permalink": f"https://www.reddit.com/comments/{link_id}/_/{comm_id}/"
            })
        if verbose:
            print(f"  Total rows: {len(all_data)}", end='\r')

    df = pd.DataFrame(all_data)

    if not df.empty:
        df['Body'] = df['Body'].fillna('').astype(str).str.replace('\n', ' ')
        df['Title'] = df['Title'].fillna('').astype(str).str.replace('\n', ' ')

        df['ticker'] = tickername

        if save_db:
            save_to_rds(df, "stock_reddit")
        if save_local:
            if local_format == "csv":
                append_to_local_csv(
                    df,
                    output_dir=local_csv_dir,
                    filename=f"{tickername}.csv",
                    dedupe_subset=["ticker", "Type", "Date", "Author", "Title", "Body", "Permalink"],
                )
            elif local_format == "db":
                save_to_local_db(
                    df,
                    "stock_reddit",
                    db_path=local_db_path,
                )
            else:
                raise ValueError("local_format must be either 'csv' or 'db'")
    else:
        if verbose:
            print("\n\nNo data found.")

    return df


if __name__ == "__main__":

    TICKERS = [
    # "AAPL",  # Apple
    # "MSFT",  # Microsoft
    # "NVDA",  # Nvidia
    "AMZN",  # Amazon
    "TSLA",  # Tesla
    "HD",    # Home Depot
    "GOOGL", # Alphabet
    "META",  # Meta Platforms
    "NFLX",  # Netflix
    "JPM",   # JPMorgan Chase
    "BAC",   # Bank of America
    "BRK.B", # Berkshire Hathaway
    "UNH",   # UnitedHealth Group
    "JNJ",   # Johnson & Johnson
    "LLY",   # Eli Lilly
    "XOM",   # Exxon Mobil
    "CVX",   # Chevron
    "CAT",   # Caterpillar
    "PG",    # Procter & Gamble
    "KO"     # Coca-Cola
]

    START = "2016-02-16"
    END = "2026-03-20"

    API_KEY = "TFaAars11adlxu1WZPyGIstSSo3ySAqB"

    for ticker in TICKERS:
        print(f"\nProcessing {ticker}...")

        try:
            # get_stockprice(ticker, START, END)
            data = get_stockprice(ticker, save_db=False, save_local=True)
        except Exception as e:
            print(f"Price error for {ticker}: {e}")

        try:
            get_stocknews(ticker, START, END, api_key=API_KEY, save_db=False, save_local=True)
        except Exception as e:
            print(f"News error for {ticker}: {e}")

        # try:
        #     get_stock_reddit(
        #         query=f"{ticker.lower()}",
        #         start_date=START,
        #         end_date=END,
        #         tickername=ticker
        #     )
        # except Exception as e:
        #     print(f"Reddit error for {ticker}: {e}")

    print("\nIngestion complete.")
