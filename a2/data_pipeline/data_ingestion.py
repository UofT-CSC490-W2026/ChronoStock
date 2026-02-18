import yfinance as yf
import time
from datetime import datetime
from typing import Optional
import pandas as pd
import os
import requests
from sqlalchemy import create_engine, text

# --- Database Configuration ---
DB_USER = os.getenv("RDS_USER", "postgres")
DB_PASS = os.getenv("RDS_PASS", "password")
DB_HOST = os.getenv("RDS_HOST", "localhost")
DB_PORT = os.getenv("RDS_PORT", "5432")
DB_NAME = os.getenv("RDS_DB", "stock_data")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

def save_to_rds(df, table_name, ticker_col=None, ticker_val=None):
    """Saves DataFrame to RDS. Optionally deletes existing ticker data first."""
    if df.empty: return
    try:
        with engine.begin() as conn:
            # If replacing data for a specific ticker (e.g. full price history)
            if ticker_col and ticker_val:
                print(f"Cleaning existing data for {ticker_val} in {table_name}...")
                conn.execute(text(f"DELETE FROM {table_name} WHERE \"{ticker_col}\" = :t"), {"t": ticker_val})
            
            df.to_sql(table_name, conn, if_exists='append', index=False)
            print(f"Saved {len(df)} rows to RDS table: {table_name}")
    except Exception as e:
        print(f"Error saving to RDS: {e}")

def get_stockprice(ticker, start_date, end_date, save_db=True):
    """
    Fetches historical stock data, saves it to CSV
    """
    print(f"--- Fetching data for {ticker} ---")
    
    data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True)

    if data.empty:
        print(f"Error: No data found for {ticker}. Please check the symbol or date range.")
        return
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Prepare for DB
    data = data.reset_index()  # Make Date a column
    data['ticker'] = ticker    # Add ticker column
    
    if save_db:
        save_to_rds(data, "stock_prices", ticker_col="ticker", ticker_val=ticker)

def get_stocknews(ticker: str, start_date: str, end_date: str, api_key: str, save_db=True):
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
            # 1. Fetch Data
            if next_url == base_url:
                response = session.get(next_url, params=params, timeout=15)
            else:
                # Ensure API Key is attached to pagination links
                if "apiKey=" not in next_url:
                    sep = "&" if "?" in next_url else "?"
                    next_url += f"{sep}apiKey={api_key}"
                response = session.get(next_url, timeout=15)

            # 2. Handle Rate Limits (429) gracefully
            if response.status_code == 429:
                print("Rate limit hit. Sleeping 60s...")
                time.sleep(60)
                continue # Retry the same URL
            
            response.raise_for_status()
            data = response.json()
            
            # 3. Process Results
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
                    "insights": article.get('insights',''),
                    "url": article.get('article_url')
                })
            
            print(f"Collected {len(results)} articles. Total: {len(all_records)}")
            
            # 4. Prepare Next Page
            next_url = data.get("next_url")
            
            # 5. Sleep 12+ seconds to stay under 5 req/min
            if next_url:
                print("Sleeping 13s to respect free tier limit...")
                time.sleep(13)

        except Exception as e:
            print(f"Error: {e}")
            break

    # Save Data
    df = pd.DataFrame(all_records)
    if not df.empty:
        df['ticker'] = ticker
        if save_db:
            save_to_rds(df, "stock_news")
        
    return df
    
def get_stock_reddit(query, start_date, end_date,tickername,verbose=True, subreddit="ValueInvesting", save_db=True):
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
                if not data: break
                yield data
                current_after = data[-1]['created_utc'] + 1
                time.sleep(0.5)
            except Exception as e:
                print(f"Error fetching {endpoint}: {e}")
                break

    start_ts = _get_unix_time(start_date)
    end_ts = _get_unix_time(end_date)
    all_data = [] # List to store rows

    if verbose:
        print(f"--- Scraper Started: r/{subreddit} | Query: '{query}' ---")

    # 1. Fetch Submissions
    if verbose: print("> Fetching Submissions...")
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
        if verbose: print(f"  Total rows: {len(all_data)}", end='\r')

    # 2. Fetch Comments
    if verbose: print("\n> Fetching Comments...")
    for batch in _fetch_pullpush_data("comment", subreddit, query, start_ts, end_ts):
        for comment in batch:
            link_id = comment.get('link_id', '').split('_')[-1]
            comm_id = comment.get('id', '')
            
            all_data.append({
                "Type": "Comment",
                "Date": datetime.fromtimestamp(comment['created_utc']).strftime('%Y-%m-%d %H:%M:%S'),
                "Author": comment.get('author', '[deleted]'),
                "Score": comment.get('score', 0),
                "Title": "", # Comments don't have titles
                "Body": comment.get('body', ''),
                "Permalink": f"https://www.reddit.com/comments/{link_id}/_/{comm_id}/"
            })
        if verbose: print(f"  Total rows: {len(all_data)}", end='\r')

    # --- Convert to DataFrame and Save ---
    df = pd.DataFrame(all_data)
    
    if not df.empty:
        # Optional: Clean up text columns
        df['Body'] = df['Body'].fillna('').astype(str).str.replace('\n', ' ')
        df['Title'] = df['Title'].fillna('').astype(str).str.replace('\n', ' ')
        
        df['ticker'] = tickername # Ensure ticker is associated with the data
        
        if save_db:
            save_to_rds(df, "stock_reddit")
    else:
        if verbose: print("\n\nNo data found.")

    return df


if __name__ == "__main__":
    # example usage
    TICKER = "AMZN"
    START = "2020-02-16"
    END = "2022-02-16"
    
    get_stockprice(TICKER, START, END)
    get_stocknews(TICKER,START,END,api_key='TFaAars11adlxu1WZPyGIstSSo3ySAqB')
    get_stock_reddit("amzn|amazon",START,END,TICKER)