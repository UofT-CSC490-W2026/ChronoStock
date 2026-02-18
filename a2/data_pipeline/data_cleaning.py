import pandas as pd
from difflib import SequenceMatcher
import re
from datetime import timedelta

def clean_stock_news(input_file, output_file, ticker_keywords):
    """
    Cleans stock news data by:
    1. Filtering for relevance based on keywords.
    2. Deduplicating entries based on time (24h) and title similarity.
    3. Removing opinion/analysis pieces.
    """
    print(f"Loading data from {input_file}...")
    try:
        df = pd.read_csv(input_file)
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    df['published_utc'] = pd.to_datetime(df['published_utc'], utc=True)
    df['description'] = df['description'].fillna('')
    df['title'] = df['title'].fillna('')

    # --- Step 1: Relevance Filtering ---
    print(f"Filtering for keywords")
    
    def is_relevant(row):
        text = (str(row['title']) + " " + str(row['description'])).lower()
        return any(keyword in text for keyword in ticker_keywords)

    df_relevant = df[df.apply(is_relevant, axis=1)].copy()
    print(f"Rows remaining after relevance filter: {len(df_relevant)}")

    # --- Step 2: Time-based Deduplication ---
    # Sort by date to compare sequential articles
    print("Deduplicating similar articles...")
    df_relevant = df_relevant.sort_values('published_utc')
    df_relevant = df_relevant.reset_index(drop=True)
    
    keep_mask = [True] * len(df_relevant)
    titles = df_relevant['title'].tolist()
    dates = df_relevant['published_utc'].tolist()

    for i in range(1, len(df_relevant)):
        # Calculate time difference in hours
        time_diff = (dates[i] - dates[i-1]).total_seconds() / 3600
        
        # If articles are within 24 hours of each other
        if time_diff < 24:
            # Check title similarity ratio (0.0 to 1.0)
            similarity_ratio = SequenceMatcher(None, titles[i], titles[i-1]).ratio()
            
            # If highly similar (>80%), mark the current one for removal
            # (Keeping the earlier one is usually safer for event detection)
            if similarity_ratio > 0.8: 
                keep_mask[i] = False
    
    df_deduped = df_relevant[keep_mask].copy()
    print(f"Rows remaining after deduplication: {len(df_deduped)}")

    # --- Step 3: Noise/Opinion Removal ---
    # Remove articles that are likely analysis rather than news events
    print("Removing opinion and analysis pieces...")
    
    noise_patterns = [
        r'^Why\b',                # "Why Amazon stock..."
        r'^Is\b',                 # "Is it time to buy..."
        r'^Should\b',             # "Should you buy..."
        r'Better Buy\b',          # "Better Buy: Amazon vs..."
        r'Top Analyst Reports\b', # "Top Analyst Reports for..."
        r'Stock Market Today\b',  # Generic market updates
        r'Earnings Preview\b',    # Pre-event speculation
        r'Price Over Earnings\b', # Technical analysis
        r'What\b',                # "What you need to know..."
        r'Here\'s Why\b',         # "Here's Why..."
        r'Prediction\b'           # "Price Prediction..."
    ]
    
    # Compile regex pattern (case-insensitive)
    noise_regex = re.compile('|'.join(noise_patterns), re.IGNORECASE)
    
    # Filter out rows matching the noise patterns
    df_final = df_deduped[~df_deduped['title'].str.contains(noise_regex)].copy()
    print(f"Final row count: {len(df_final)}")

    # --- Step 4: Save Output ---
    df_final.to_csv(output_file, index=False)
    print(f"Cleaned data saved to {output_file}")

if __name__ == "__main__":
    # Example usage for Amazon
    amzn_keywords = ['amazon', 'amzn', 'aws', 'jeff bezos', 'andy jassy']
    
    clean_stock_news(
        input_file='stock_data/AMZN_news.csv', 
        output_file='stock_data/AMZN_news_processed.csv', 
        ticker_keywords=amzn_keywords
    )