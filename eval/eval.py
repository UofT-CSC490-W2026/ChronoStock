import os

import pandas as pd

TICKERS = ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"]
SOURCE_CSV = "data/results"
GROUND_TRUTH_DIR = "data/ground_truth"
ID_COLUMN = "id"


def resolve_source_path(ticker):
    if SOURCE_CSV.lower().endswith(".csv"):
        return SOURCE_CSV
    return os.path.join(SOURCE_CSV, f"{ticker}.csv")


def resolve_ground_truth_path(ticker):
    return os.path.join(GROUND_TRUTH_DIR, f"{ticker}.csv")


def load_ids(path):
    df = pd.read_csv(path, usecols=[ID_COLUMN])
    return set(df[ID_COLUMN].dropna().astype(str))


def compute_metrics(predicted_ids, ground_truth_ids):
    true_positives = len(predicted_ids & ground_truth_ids)
    false_positives = len(predicted_ids - ground_truth_ids)
    false_negatives = len(ground_truth_ids - predicted_ids)

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "tp": true_positives,
        "fp": false_positives,
        "fn": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def main():
    rows = []
    all_predicted_ids = set()
    all_ground_truth_ids = set()

    for ticker in TICKERS:
        source_path = resolve_source_path(ticker)
        ground_truth_path = resolve_ground_truth_path(ticker)

        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Missing source CSV for {ticker}: {source_path}")
        if not os.path.exists(ground_truth_path):
            raise FileNotFoundError(f"Missing ground truth CSV for {ticker}: {ground_truth_path}")

        predicted_ids = load_ids(source_path)
        ground_truth_ids = load_ids(ground_truth_path)
        metrics = compute_metrics(predicted_ids, ground_truth_ids)

        rows.append(
            {
                "ticker": ticker,
                "predicted_count": len(predicted_ids),
                "ground_truth_count": len(ground_truth_ids),
                **metrics,
            }
        )

        all_predicted_ids.update(f"{ticker}:{news_id}" for news_id in predicted_ids)
        all_ground_truth_ids.update(f"{ticker}:{news_id}" for news_id in ground_truth_ids)

    results_df = pd.DataFrame(rows)
    overall = compute_metrics(all_predicted_ids, all_ground_truth_ids)

    print(results_df.to_string(index=False))
    print()
    print("Overall")
    print(f"Precision: {overall['precision']:.4f}")
    print(f"Recall:    {overall['recall']:.4f}")
    print(f"F1 score:  {overall['f1']:.4f}")


if __name__ == "__main__":
    main()
