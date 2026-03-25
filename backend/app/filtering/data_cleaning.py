import os
import re
from difflib import SequenceMatcher

import pandas as pd
from sqlalchemy import create_engine, inspect, text

# from db import engine


def save_cleaned_to_rds(df, table_name, ticker_val):
    """Saves cleaned DataFrame to RDS, replacing existing cleaned data for this ticker."""
    if df.empty:
        return
    # try:
    #     with engine.begin() as conn:
    #         inspector = inspect(conn)
    #         table_exists = inspector.has_table(table_name)

    #         if table_exists:
    #             print(f"Cleaning existing data for {ticker_val} in {table_name}...")
    #             conn.execute(
    #                 text(f'DELETE FROM {table_name} WHERE ticker = :t'),
    #                 {"t": ticker_val}
    #             )
    #             df.to_sql(table_name, conn, if_exists='append', index=False)

    #         else:
    #             print(f"Table {table_name} does not exist. It will be created.")
    #             df.to_sql(table_name, conn, if_exists='replace', index=False)
    # except Exception as e:
    #     print(f"Error saving to RDS: {e}")


def save_cleaned_to_local_csv(df, ticker, output_dir="data/stock_news_cleaned"):
    """Saves cleaned stock news to a local CSV file for the ticker."""
    if df.empty:
        return

    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, f"{ticker}.csv")
    df.to_csv(csv_path, index=False)
    print(f"Saved {len(df)} cleaned rows locally to {csv_path}")


def save_cleaned_to_local_db(df, table_name, ticker_val, db_path="data/chronostock.db"):
    """Saves cleaned stock news to a local SQLite DB, replacing rows for the ticker."""
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

            if table_exists:
                print(f"Cleaning existing local data for {ticker_val} in {table_name}...")
                conn.execute(
                    text(f'DELETE FROM {table_name} WHERE ticker = :t'),
                    {"t": ticker_val}
                )
                df.to_sql(table_name, conn, if_exists='append', index=False)
            else:
                print(f"Local table {table_name} does not exist. It will be created.")
                df.to_sql(table_name, conn, if_exists='replace', index=False)
    except Exception as e:
        print(f"Error saving to local DB: {e}")


def load_stock_news(ticker, source="db", csv_dir="data/stock_news", db_path="data/chronostock.db"):
    """Loads stock news from either the primary DB or a local CSV/SQLite source."""
    if source == "db":
        query = text("SELECT * FROM stock_news WHERE ticker = :ticker")
        return pd.read_sql(query, engine, params={"ticker": ticker})

    if source == "csv":
        csv_path = os.path.join(csv_dir, f"{ticker}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Local CSV not found: {csv_path}")
        return pd.read_csv(csv_path)

    if source == "local_db":
        local_engine = create_engine(f"sqlite:///{db_path}")
        query = text("SELECT * FROM stock_news WHERE ticker = :ticker")
        return pd.read_sql(query, local_engine, params={"ticker": ticker})

    raise ValueError("source must be one of: 'db', 'csv', 'local_db'")


def clean_stock_news(
    ticker,
    ticker_keywords,
    source="db",
    output="db",
    input_csv_dir="data/stock_news",
    output_csv_dir="data/stock_news_cleaned",
    local_db_path="data/chronostock.db",
):
    """
    Cleans stock news data by:
    1. Filtering for relevance based on keywords.
    2. Deduplicating entries based on time (24h) and title similarity.
    3. Removing opinion/analysis pieces.
    """
    print(f"--- Cleaning News for {ticker} ---")
    try:
        df = load_stock_news(
            ticker,
            source=source,
            csv_dir=input_csv_dir,
            db_path=local_db_path,
        )
    except Exception as e:
        print(f"Error loading news data: {e}")
        return

    if df.empty:
        print(f"No news found for {ticker} in {source}.")
        return

    df['published_utc'] = pd.to_datetime(df['published_utc'], utc=True)
    df['description'] = df['description'].fillna('')
    df['title'] = df['title'].fillna('')

    print("Filtering for keywords")

    def is_relevant(row):
        combined_text = (str(row['title']) + " " + str(row['description'])).lower()
        return any(keyword in combined_text for keyword in ticker_keywords)

    df_relevant = df[df.apply(is_relevant, axis=1)].copy()
    print(f"Rows remaining after relevance filter: {len(df_relevant)}")

    print("Deduplicating similar articles...")
    df_relevant = df_relevant.sort_values('published_utc')
    df_relevant = df_relevant.reset_index(drop=True)

    keep_mask = [True] * len(df_relevant)
    titles = df_relevant['title'].tolist()
    dates = df_relevant['published_utc'].tolist()

    for i in range(1, len(df_relevant)):
        time_diff = (dates[i] - dates[i - 1]).total_seconds() / 3600

        if time_diff < 24:
            similarity_ratio = SequenceMatcher(None, titles[i], titles[i - 1]).ratio()
            if similarity_ratio > 0.8:
                keep_mask[i] = False

    df_deduped = df_relevant[keep_mask].copy()
    print(f"Rows remaining after deduplication: {len(df_deduped)}")

    print("Removing opinion and analysis pieces...")

    noise_patterns = [
        r'^Why\b',
        r'^Is\b',
        r'^Should\b',
        r'\bQ[1-4]\b',
        r'Top Analyst Reports\b',
        r'Stock Market Today\b',
        r'Earnings Preview\b',
        r'Price Over Earnings\b',
        r'What\b',
        r'Here\'s Why\b',
        r'Prediction\b'
    ]

    noise_regex = re.compile('|'.join(noise_patterns), re.IGNORECASE)
    df_final = df_deduped[~df_deduped['title'].str.contains(noise_regex)].copy()
    print(f"Final row count: {len(df_final)}")

    if output == "db":
        save_cleaned_to_rds(df_final, "stock_news_cleaned", ticker)
    elif output == "csv":
        save_cleaned_to_local_csv(df_final, ticker, output_dir=output_csv_dir)
    elif output == "local_db":
        save_cleaned_to_local_db(
            df_final,
            "stock_news_cleaned",
            ticker,
            db_path=local_db_path,
        )
    else:
        raise ValueError("output must be one of: 'db', 'csv', 'local_db'")


if __name__ == "__main__":

    TICKERS = {
        "AAPL": ["apple", "aapl", "iphone", "ipad", "mac", "tim cook"],
        "AMZN": ["amazon", "amzn", "aws", "prime", "andy jassy", "jeff bezos"],
        "BAC": ["bank of america", "bac", "bofa", "brian moynihan"],
        "BRK.B": ["berkshire hathaway", "brk.b", "brk b", "buffett", "warren buffett", "greg abel"],
        "CAT": ["caterpillar", "cat", "deere rival", "construction equipment", "jim umpleby"],
        "CVX": ["chevron", "cvx", "oil major", "mike wirth"],
        "GOOGL": ["google", "alphabet", "googl", "google cloud", "youtube", "sundar pichai"],
        "HD": ["home depot", "hd", "home improvement retailer", "ted decker"],
        "JNJ": ["johnson & johnson", "jnj", "janssen", "medtech", "joaquin duato"],
        "JPM": ["jpmorgan", "jpm", "jamie dimon", "chase bank", "jpmorgan chase"],
        "KO": ["coca-cola", "coke", "ko", "sprite", "fanta", "james quincey"],
        "LLY": ["eli lilly", "lly", "mounjaro", "zepbound", "tirzepatide", "david ricks"],
        "META": ["meta", "meta platforms", "facebook", "instagram", "whatsapp", "mark zuckerberg"],
        "MSFT": ["microsoft", "msft", "azure", "openai partner", "satya nadella", "xbox", "linkedin"],
        "NFLX": ["netflix", "nflx", "streaming giant", "reed hastings", "greg peters", "ted sarandos"],
        "NVDA": ["nvidia", "nvda", "ai chip", "gpu maker", "jensen huang", "blackwell"],
        "PG": ["procter & gamble", "p&g", "pg", "tide", "gillette", "jon moeller"],
        "TSLA": ["tesla", "tsla", "elon musk", "ev maker", "model 3", "model y"],
        "UNH": ["unitedhealth", "unitedhealth group", "unh", "optum", "andrew witty"],
        "XOM": ["exxon", "exxon mobil", "xom", "oil major", "darren woods"],
    }

    for ticker, keywords in TICKERS.items():
        print(f"\nCleaning data for {ticker}...")
        clean_stock_news(ticker, keywords, source="csv", output="csv")
        
    # clean_stock_news("NVDA", ["nvidia", "nvda", "jensen huang"], source="csv", output="csv")


    print("\nCleaning complete.")
