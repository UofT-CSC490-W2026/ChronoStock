import schedule
import time
import pandas as pd
import os
from datetime import datetime, timedelta
from data_ingestion import get_stockprice, get_stocknews, get_stock_reddit

# Configuration
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "V", "UNH",
    "JNJ", "XOM", "JPM", "WMT", "MA", "PG", "LLY", "CVX", "HD", "ABBV",
    "MRK", "KO", "PEP", "AVGO", "ORCL", "TMO", "AZN", "COST", "MCD", "CSCO",
    "ACN", "ABT", "DHR", "NEE", "LIN", "DIS", "TXN", "PM", "WFC", "AMD",
    "UPS", "BMY", "RTX", "HON", "AMGN", "UNP", "INTU", "LOW", "COP", "IBM",
    "SBUX", "BA", "GE", "MMM", "CAT", "GS", "MS", "BLK", "C", "SCHW",
    "DE", "PLD", "EL", "LMT", "ADI", "MDT", "GILD", "ISRG", "TJX", "BKNG",
    "T", "VZ", "CVS", "CI", "AMT", "SYK", "NOW", "ADP", "MO", "ZTS",
    "TMUS", "CB", "MMC", "CIG", "SO", "DU", "SLB", "EOG", "BDX", "ITW",
    "CL", "NOC", "REGN", "SHW", "USB", "PNC", "TGT", "FCX", "GM", "F"
]
API_KEY = "TFaAars11adlxu1WZPyGIstSSo3ySAqB"
DATA_DIR = "stock_data"

def update_csv(new_df, filename, id_col=None, sort_col=None):
    """Helper to append new data to existing CSV with deduplication."""
    if new_df.empty:
        print(f"No new data for {filename}")
        return

    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        old_df = pd.read_csv(path)
        combined = pd.concat([old_df, new_df])
        
        # Deduplicate
        if id_col and id_col in combined.columns:
            combined = combined.drop_duplicates(subset=[id_col])
        else:
            combined = combined.drop_duplicates()
            
        # Sort
        if sort_col and sort_col in combined.columns:
            combined = combined.sort_values(by=sort_col)
            
        combined.to_csv(path, index=False)
        print(f"Updated {filename}: {len(old_df)} -> {len(combined)} rows")
    else:
        new_df.to_csv(path, index=False)
        print(f"Created {filename} with {len(new_df)} rows")

def job():
    print(f"\n=== Starting Daily Update: {datetime.now()} ===")
    
    # Calculate dates: Today and Tomorrow (to ensure we cover the full current day)
    today_str = datetime.now().strftime('%Y-%m-%d')
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    for ticker in TICKERS:
        print(f"\n--- Processing {ticker} ---")
        
        # 1. Stock Price 
        # We fetch the full history (from 2020) every day to ensure split adjustments are correct.
        # yfinance is fast enough for this.
        print(f"Updating Stock Price for {ticker}...")
        try:
            get_stockprice(ticker, start_date="2020-01-01", end_date=tomorrow_str, output_folder=DATA_DIR)
        except Exception as e:
            print(f"Error fetching price for {ticker}: {e}")
        
        # 2. News - Incremental (Fetch today's data and append)
        print(f"Updating News for {ticker}...")
        try:
            news_df = get_stocknews(ticker, start_date=today_str, end_date=tomorrow_str, api_key=API_KEY, save_csv=False)
            update_csv(news_df, f"{ticker}_news.csv", id_col="url", sort_col="published_utc")
        except Exception as e:
            print(f"Error fetching news for {ticker}: {e}")
        
        # 3. Reddit - Incremental (Fetch today's data and append)
        print(f"Updating Reddit for {ticker}...")
        try:
            reddit_df = get_stock_reddit(ticker, start_date=today_str, end_date=tomorrow_str, tickername=ticker, save_csv=False)
            # 'Permalink' is a good unique ID for Reddit posts/comments
            update_csv(reddit_df, f"{ticker}_reddit.csv", id_col="Permalink", sort_col="Date")
        except Exception as e:
            print(f"Error fetching reddit for {ticker}: {e}")
    
    print("=== Update Complete ===")

# Schedule for 5:00 PM
schedule.every().day.at("17:00").do(job)

print("Scheduler running... (Press Ctrl+C to stop)")
while True:
    schedule.run_pending()
    time.sleep(60)