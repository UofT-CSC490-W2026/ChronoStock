import argparse
import io
import os
import re
from difflib import SequenceMatcher

import boto3
import pandas as pd


RAW_NEWS_PREFIX = os.environ.get("PIPELINE_RAW_NEWS_PREFIX", "raw/stock_news")
CLEAN_NEWS_PREFIX = os.environ.get("PIPELINE_CLEAN_NEWS_PREFIX", "clean/stock_news_cleaned")
DEFAULT_TICKERS = {
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


def load_stock_news(ticker, source="s3", csv_dir="data/stock_news", db_path="data/chronostock.db"):
    """Loads stock news from S3 or local CSV for the ticker."""
    if source == "s3":
        bucket = _require_bucket()
        key = _s3_key(RAW_NEWS_PREFIX, f"{ticker}.csv")
        response = _s3_client().get_object(Bucket=bucket, Key=key)
        return pd.read_csv(io.BytesIO(response["Body"].read()))

    if source == "csv":
        csv_path = os.path.join(csv_dir, f"{ticker}.csv")
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Local CSV not found: {csv_path}")
        return pd.read_csv(csv_path)

    raise ValueError("source must be one of: 's3', 'csv'")


def save_cleaned_to_s3(df, ticker):
    if df.empty:
        return

    bucket = _require_bucket()
    key = _s3_key(CLEAN_NEWS_PREFIX, f"{ticker}.csv")
    _s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=df.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )
    print(f"Saved {len(df)} cleaned rows to s3://{bucket}/{key}")


def save_cleaned_to_local_csv(df, ticker, output_dir="data/stock_news_cleaned"):
    if df.empty:
        return

    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, f"{ticker}.csv")
    df.to_csv(csv_path, index=False)
    print(f"Saved {len(df)} cleaned rows locally to {csv_path}")


def clean_news_dataframe(df, ticker_keywords):
    if df.empty:
        return df.copy()

    df = df.copy()
    df["published_utc"] = pd.to_datetime(df["published_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_utc", "id"])
    df["description"] = df["description"].fillna("")
    df["title"] = df["title"].fillna("")

    print("Filtering for keywords")

    def is_relevant(row):
        combined_text = (str(row["title"]) + " " + str(row["description"])).lower()
        return any(keyword in combined_text for keyword in ticker_keywords)

    df_relevant = df[df.apply(is_relevant, axis=1)].copy()
    print(f"Rows remaining after relevance filter: {len(df_relevant)}")

    print("Deduplicating similar articles...")
    df_relevant = df_relevant.sort_values("published_utc").reset_index(drop=True)

    keep_mask = [True] * len(df_relevant)
    titles = df_relevant["title"].tolist()
    dates = df_relevant["published_utc"].tolist()

    for i in range(1, len(df_relevant)):
        time_diff = (dates[i] - dates[i - 1]).total_seconds() / 3600
        if time_diff < 24:
            similarity_ratio = SequenceMatcher(None, titles[i], titles[i - 1]).ratio()
            if similarity_ratio > 0.8:
                keep_mask[i] = False

    df_deduped = df_relevant[keep_mask].copy()
    print(f"Rows remaining after deduplication: {len(df_deduped)}")
    if df_deduped.empty:
        return df_deduped

    print("Removing opinion and analysis pieces...")
    noise_patterns = [
        r"^Why\b",
        r"^Is\b",
        r"^Should\b",
        r"\bQ[1-4]\b",
        r"Top Analyst Reports\b",
        r"Stock Market Today\b",
        r"Earnings Preview\b",
        r"Price Over Earnings\b",
        r"What\b",
        r"Here\'s Why\b",
        r"Prediction\b",
    ]

    noise_regex = re.compile("|".join(noise_patterns), re.IGNORECASE)
    df_final = df_deduped[~df_deduped["title"].str.contains(noise_regex, na=False)].copy()
    df_final["published_utc"] = df_final["published_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Final row count: {len(df_final)}")
    return df_final


def clean_stock_news(
    ticker,
    ticker_keywords,
    source="s3",
    output="s3",
    input_csv_dir="data/stock_news",
    output_csv_dir="data/stock_news_cleaned",
):
    """
    Cleans stock news data by:
    1. Filtering for relevance based on keywords.
    2. Deduplicating entries based on time (24h) and title similarity.
    3. Removing opinion/analysis pieces.
    """
    print(f"--- Cleaning News for {ticker} ---")
    try:
        df = load_stock_news(ticker, source=source, csv_dir=input_csv_dir)
    except Exception as e:
        print(f"Error loading news data: {e}")
        return

    if df.empty:
        print(f"No news found for {ticker} in {source}.")
        return

    df_final = clean_news_dataframe(df, ticker_keywords)

    if output == "s3":
        save_cleaned_to_s3(df_final, ticker)
    elif output == "csv":
        save_cleaned_to_local_csv(df_final, ticker, output_dir=output_csv_dir)
    else:
        raise ValueError("output must be one of: 's3', 'csv'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean raw stock news and upload cleaned CSVs to S3.")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS.keys()))
    parser.add_argument("--source", default="s3", choices=["s3", "csv"])
    parser.add_argument("--output", default="s3", choices=["s3", "csv"])
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]

    for ticker in tickers:
        keywords = DEFAULT_TICKERS.get(ticker)
        if not keywords:
            print(f"Skipping {ticker}: no keyword config found.")
            continue

        print(f"\nCleaning data for {ticker}...")
        clean_stock_news(ticker, keywords, source=args.source, output=args.output)

    print("\nCleaning complete.")
