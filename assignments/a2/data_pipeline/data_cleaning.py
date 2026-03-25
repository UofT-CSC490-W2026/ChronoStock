import io
import os
import re
from difflib import SequenceMatcher

import boto3
import pandas as pd


RAW_NEWS_PREFIX = os.environ.get("PIPELINE_RAW_NEWS_PREFIX", "raw/stock_news")
CLEAN_NEWS_PREFIX = os.environ.get("PIPELINE_CLEAN_NEWS_PREFIX", "clean/stock_news_cleaned")


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


def _load_csv_from_s3(prefix: str, ticker: str) -> pd.DataFrame:
    bucket = _require_bucket()
    key = _s3_key(prefix, f"{ticker}.csv")
    response = _s3_client().get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(response["Body"].read()))


def save_cleaned_to_s3(df: pd.DataFrame, prefix: str, ticker_val: str) -> None:
    if df.empty:
        return

    bucket = _require_bucket()
    key = _s3_key(prefix, f"{ticker_val}.csv")
    _s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=df.to_csv(index=False).encode("utf-8"),
        ContentType="text/csv",
    )
    print(f"Saved {len(df)} cleaned rows to s3://{bucket}/{key}")


def clean_stock_news(ticker, ticker_keywords):
    """
    Cleans stock news data by:
    1. Filtering for relevance based on keywords.
    2. Deduplicating entries based on time (24h) and title similarity.
    3. Removing opinion/analysis pieces.
    """
    print(f"--- Cleaning News for {ticker} ---")
    try:
        df = _load_csv_from_s3(RAW_NEWS_PREFIX, ticker)
    except Exception as e:
        print(f"Error loading raw news from S3: {e}")
        return

    if df.empty:
        print(f"No news found for {ticker}.")
        return

    df["published_utc"] = pd.to_datetime(df["published_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["published_utc", "id"])
    df["description"] = df["description"].fillna("")
    df["title"] = df["title"].fillna("")

    print("Filtering for keywords")

    def is_relevant(row):
        text = (str(row["title"]) + " " + str(row["description"])).lower()
        return any(keyword in text for keyword in ticker_keywords)

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

    print("Removing opinion and analysis pieces...")
    noise_patterns = [
        r"^Why\b",
        r"^Is\b",
        r"^Should\b",
        r"Better Buy\b",
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

    save_cleaned_to_s3(df_final, CLEAN_NEWS_PREFIX, ticker)


if __name__ == "__main__":
    TICKERS = {
        "AMZN": ["amazon", "amzn", "aws", "jeff bezos", "andy jassy"],
        "AAPL": ["apple", "aapl", "iphone", "tim cook"],
        "GOOGL": ["google", "alphabet", "googl", "sundar pichai"],
        "MSFT": ["microsoft", "msft", "azure", "satya nadella"],
        "TSLA": ["tesla", "tsla", "elon musk"],
    }

    for ticker, keywords in TICKERS.items():
        print(f"\nCleaning data for {ticker}...")
        clean_stock_news(ticker, keywords)

    print("\nCleaning complete.")
