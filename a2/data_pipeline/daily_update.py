import schedule
import time
import pandas as pd
import os
from datetime import datetime, timedelta
from data_ingestion import get_stockprice, get_stocknews, get_stock_reddit

# Configuration
TICKERS = [
    # "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "V", "UNH",
    # "JNJ", "XOM", "JPM", "WMT", "MA", "PG", "LLY", "CVX", "HD", "ABBV",
    # "MRK", "KO", "PEP", "AVGO", "ORCL", "TMO", "AZN", "COST", "MCD", "CSCO",
    # "ACN", "ABT", "DHR", "NEE", "LIN", "DIS", "TXN", "PM", "WFC", "AMD",
    # "UPS", "BMY", "RTX", "HON", "AMGN", "UNP", "INTU", "LOW", "COP", "IBM",
    # "SBUX", "BA", "GE", "MMM", "CAT", "GS", "MS", "BLK", "C", "SCHW",
    # "DE", "PLD", "EL", "LMT", "ADI", "MDT", "GILD", "ISRG", "TJX", "BKNG",
    # "T", "VZ", "CVS", "CI", "AMT", "SYK", "NOW", "ADP", "MO", "ZTS",
    # "TMUS", "CB", "MMC", "CIG", "SO", "DU", "SLB", "EOG", "BDX", "ITW",
    # "CL", "NOC", "REGN", "SHW", "USB", "PNC", "TGT", "FCX", "GM", "F"
    "AMZN"
]
API_KEY = "TFaAars11adlxu1WZPyGIstSSo3ySAqB"
DATA_DIR = "stock_data"

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
            get_stockprice(ticker, start_date="2020-01-01", end_date=tomorrow_str, save_db=True)
        except Exception as e:
            print(f"Error fetching price for {ticker}: {e}")
        
        # 2. News - Incremental (Fetch today's data and append)
        print(f"Updating News for {ticker}...")
        try:
            get_stocknews(ticker, start_date=today_str, end_date=tomorrow_str, api_key=API_KEY, save_db=True)
        except Exception as e:
            print(f"Error fetching news for {ticker}: {e}")
        
        # 3. Reddit - Incremental (Fetch today's data and append)
        print(f"Updating Reddit for {ticker}...")
        try:
            get_stock_reddit(ticker, start_date=today_str, end_date=tomorrow_str, tickername=ticker, save_db=True)
        except Exception as e:
            print(f"Error fetching reddit for {ticker}: {e}")
    
    print("=== Update Complete ===")

if __name__ == "__main__":
    job()
