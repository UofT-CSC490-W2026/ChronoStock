"""
ChronoStock Evaluation & Ablation Framework

PRIMARY metrics (fully independent of CAR — no circularity):
  1. Hit Rate @k   – fraction of detected events near a top-k extreme return day
  2. Coverage @k   – fraction of extreme return days captured by detected events
  3. F1 @k         – harmonic mean of hit rate and coverage
  4. Volume Ratio  – avg trading volume at event dates / overall avg volume
  5. News Density  – avg news articles around events vs around random dates
  6. Redundancy    – fraction of top-k events within 3 days of another (lower = better)

SECONDARY metrics (uses CAR — partially circular, reported as sanity check):
  7. Mean |CAR|       – avg absolute CAR at detected events
  8. Random |Return|  – avg absolute return at random dates (baseline)
  9. t-test p-value   – statistical significance of (7) vs (8)

Note on circularity: The pipeline ranks events by CAR, so Mean |CAR| is biased
in favor of CAR-using configs. The primary metrics above use raw daily returns
and trading volume — signals never used by the pipeline — so they are fair
comparisons across all ablation configs including "No CAR".
"""

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

# Allow imports from the backend package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.pipelines.core.car import CARCalculator
from app.pipelines.core.event_detection import EventDetector


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def fetch_prices(ticker: str, market: str, start: str, end: str, cache_dir: str):
    """Download stock + market prices via yfinance, cache as CSV."""
    os.makedirs(cache_dir, exist_ok=True)

    def _download(symbol, path):
        if os.path.exists(path):
            return
        df = yf.download(symbol, start=start, end=end, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        df.to_csv(path, index=False)

    stock_path = os.path.join(cache_dir, f"{ticker}.csv")
    market_path = os.path.join(cache_dir, f"{market.replace('^', '')}.csv")

    _download(ticker, stock_path)
    _download(market, market_path)

    return stock_path, market_path


def load_price_df(stock_path: str, market_path: str) -> pd.DataFrame:
    """Merge stock + market CSVs into a single DataFrame with returns & volume."""
    stock = pd.read_csv(stock_path, parse_dates=["Date"])
    market = pd.read_csv(market_path, parse_dates=["Date"])

    stock_cols = ["Date", "Close"]
    if "Volume" in stock.columns:
        stock_cols.append("Volume")

    stock = stock[stock_cols].rename(columns={"Close": "stock_price"})
    market = market[["Date", "Close"]].rename(columns={"Close": "market_price"})

    df = pd.merge(stock, market, on="Date", how="inner").sort_values("Date").reset_index(drop=True)
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    df["stock_return"] = df["stock_price"].pct_change()
    df["market_return"] = df["market_price"].pct_change()
    df = df.dropna().reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

_EMPTY_METRICS = {
    # Primary
    "n_events": 0,
    "hit_rate": 0.0, "coverage": 0.0, "f1": 0.0,
    "volume_ratio": 0.0,
    "news_density_event": 0.0, "news_density_random": 0.0,
    "redundancy_rate": 0.0,
    # Secondary (CAR-based — circularity caveat)
    "mean_abs_car": 0.0, "random_mean_abs_return": 0.0, "car_ttest_pvalue": 1.0,
}


def compute_metrics(
    events_df: pd.DataFrame,
    price_df: pd.DataFrame,
    news_df: pd.DataFrame,
    top_k: int = 20,
    match_window: int = 3,
    n_random_samples: int = 500,
    seed: int = 42,
) -> dict:
    """
    Compute all evaluation metrics for a set of detected events.

    Primary metrics use only raw returns and volume (never touched by pipeline).
    Secondary metrics use CAR (used by pipeline — partially circular).
    """
    rng = np.random.RandomState(seed)
    results = {}

    if events_df.empty or "event_date" not in events_df.columns:
        return dict(_EMPTY_METRICS)

    event_dates = pd.to_datetime(events_df["event_date"]).dt.tz_localize(None).values
    all_dates = price_df["Date"].values
    n_events = len(event_dates)
    results["n_events"] = int(n_events)

    # Random date sample (reused across metrics)
    random_indices = rng.choice(len(all_dates), size=n_random_samples, replace=True)
    random_dates = all_dates[random_indices]

    # ===================================================================
    # PRIMARY METRICS (independent of CAR)
    # ===================================================================

    # --- 1. Hit Rate / Coverage / F1 vs extreme raw-return days ---
    # Proxy ground truth: top-k days by |daily return| (raw, not CAR-adjusted).
    # This is fully independent of the pipeline's CAR scoring.
    abs_returns = price_df["stock_return"].abs()
    extreme_indices = abs_returns.nlargest(top_k).index
    extreme_dates = price_df.loc[extreme_indices, "Date"].values

    def dates_match(d1, d2_set, window):
        d1 = pd.Timestamp(d1)
        for d2 in d2_set:
            if abs((d1 - pd.Timestamp(d2)).days) <= window:
                return True
        return False

    hits = sum(1 for d in event_dates if dates_match(d, extreme_dates, match_window))
    covered = sum(1 for d in extreme_dates if dates_match(d, event_dates, match_window))

    results["hit_rate"] = hits / n_events if n_events > 0 else 0.0
    results["coverage"] = covered / len(extreme_dates) if len(extreme_dates) > 0 else 0.0
    if results["hit_rate"] + results["coverage"] > 0:
        results["f1"] = 2 * results["hit_rate"] * results["coverage"] / (results["hit_rate"] + results["coverage"])
    else:
        results["f1"] = 0.0

    # --- 2. Volume spike ratio ---
    # Volume is never used by the pipeline — fully independent signal.
    if "Volume" in price_df.columns:
        avg_vol_all = price_df["Volume"].mean()
        event_mask = price_df["Date"].isin(pd.to_datetime(event_dates))
        avg_vol_event = price_df.loc[event_mask, "Volume"].mean()
        results["volume_ratio"] = float(avg_vol_event / avg_vol_all) if avg_vol_all > 0 else 0.0
    else:
        results["volume_ratio"] = float("nan")

    # --- 3. News density ratio ---
    # News count is external — not used in event detection (only attached after).
    if news_df is not None and not news_df.empty and "published_utc" in news_df.columns:
        news_dates = pd.to_datetime(news_df["published_utc"], errors="coerce").dt.tz_localize(None)

        def count_news_around(date, window_days=2):
            start = date - pd.Timedelta(days=window_days)
            end = date + pd.Timedelta(days=window_days)
            return int(((news_dates >= start) & (news_dates <= end)).sum())

        event_news_counts = [count_news_around(pd.Timestamp(d)) for d in event_dates]
        random_news_counts = [count_news_around(pd.Timestamp(d)) for d in random_dates]

        results["news_density_event"] = float(np.mean(event_news_counts)) if event_news_counts else 0.0
        results["news_density_random"] = float(np.mean(random_news_counts)) if random_news_counts else 0.0
    else:
        results["news_density_event"] = float("nan")
        results["news_density_random"] = float("nan")

    # --- 4. Redundancy rate ---
    # Purely temporal — measures event spread.
    event_ts = np.sort(pd.to_datetime(event_dates).astype(np.int64))
    n = len(event_ts)
    redundant = 0
    for i in range(n):
        for j in range(i + 1, n):
            diff_days = abs(event_ts[j] - event_ts[i]) / 1e9 / 86400
            if diff_days <= 3:
                redundant += 1
                break
    results["redundancy_rate"] = redundant / n if n > 0 else 0.0

    # ===================================================================
    # SECONDARY METRICS (CAR-based — partially circular, sanity check only)
    # ===================================================================
    # The pipeline ranks events by CAR, so detected events will inherently
    # have high |CAR|. These metrics confirm the pipeline is working as
    # designed but do NOT independently validate event quality.

    event_cars = events_df["abs_car"].values
    results["mean_abs_car"] = float(np.mean(event_cars))

    random_abs_returns = np.abs(price_df["stock_return"].values[random_indices])
    results["random_mean_abs_return"] = float(np.mean(random_abs_returns))

    if len(event_cars) >= 2:
        _, p_val = stats.ttest_ind(event_cars, random_abs_returns, equal_var=False)
        results["car_ttest_pvalue"] = float(p_val)
    else:
        results["car_ttest_pvalue"] = 1.0

    return results


# ---------------------------------------------------------------------------
# Pipeline runners for ablation configs
# ---------------------------------------------------------------------------

def run_full_pipeline(
    ticker, stock_path, market_path, news_path, results_dir, start, end, top_k, pen,
):
    """Standard full pipeline."""
    det = EventDetector(
        ticker=ticker,
        stock_path=stock_path,
        market_path=market_path,
        news_path=news_path,
        results_dir=results_dir,
        start_time=start,
        end_time=end,
        top_k_events=top_k,
        pen=pen,
    )
    det.load_data()
    det.setup_car()

    cp_ret, cp_vol = det.detect_change_points()
    windows = det.build_windows(cp_ret) + det.build_windows(cp_vol)
    merged = det.merge_windows(windows)
    events_df = det.score_events(merged).head(top_k)
    return events_df, det


def run_no_pelt(
    ticker, stock_path, market_path, news_path, results_dir, start, end, top_k, **_kw,
):
    """Ablation: skip PELT, score every date by CAR, take top-k."""
    car = CARCalculator(stock_path=stock_path, market_path=market_path)
    car.load_data()
    car.fit_market_model()
    car.compute_abnormal_returns()

    top_events = car.get_top_k_events(
        k=top_k, window_before=3, window_after=3,
        start_date=start, end_date=end,
    )

    rows = []
    for date, car_val, _ in top_events:
        rows.append({
            "event_date": date,
            "car": car_val,
            "abs_car": abs(car_val),
            "start_idx": 0,
            "end_idx": 0,
        })

    events_df = pd.DataFrame(rows)

    det = EventDetector(
        ticker=ticker,
        stock_path=stock_path,
        market_path=market_path,
        news_path=news_path,
        results_dir=results_dir,
        start_time=start,
        end_time=end,
        top_k_events=top_k,
    )
    det.load_data()
    return events_df, det


def run_no_car(
    ticker, stock_path, market_path, news_path, results_dir, start, end, top_k, pen,
):
    """Ablation: use PELT but rank events by raw |return| instead of CAR."""
    det = EventDetector(
        ticker=ticker,
        stock_path=stock_path,
        market_path=market_path,
        news_path=news_path,
        results_dir=results_dir,
        start_time=start,
        end_time=end,
        top_k_events=top_k,
        pen=pen,
    )
    det.load_data()
    det.setup_car()

    cp_ret, cp_vol = det.detect_change_points()
    windows = det.build_windows(cp_ret) + det.build_windows(cp_vol)
    merged = det.merge_windows(windows)

    events = []
    for s, e in merged:
        center = (s + e) // 2
        if center >= len(det.price_df):
            continue
        row = det.price_df.iloc[center]
        events.append({
            "event_date": row["Date"],
            "start_idx": s,
            "end_idx": e,
            "car": row["stock_return"],
            "abs_car": abs(row["stock_return"]),
        })

    events_df = pd.DataFrame(events)
    if not events_df.empty:
        events_df = events_df.sort_values("abs_car", ascending=False).head(top_k).reset_index(drop=True)

    return events_df, det


def run_random_baseline(
    ticker, stock_path, market_path, news_path, results_dir, start, end, top_k, seed=42, **_kw,
):
    """Baseline: pick random dates."""
    det = EventDetector(
        ticker=ticker,
        stock_path=stock_path,
        market_path=market_path,
        news_path=news_path,
        results_dir=results_dir,
        start_time=start,
        end_time=end,
        top_k_events=top_k,
    )
    det.load_data()
    det.setup_car()

    rng = np.random.RandomState(seed)
    df = det.price_df
    if start:
        df = df[df["Date"] >= pd.Timestamp(start)]
    if end:
        df = df[df["Date"] <= pd.Timestamp(end)]

    indices = rng.choice(len(df), size=min(top_k, len(df)), replace=False)
    rows = []
    for idx in sorted(indices):
        row = df.iloc[idx]
        rows.append({
            "event_date": row["Date"],
            "start_idx": idx,
            "end_idx": idx,
            "car": row["stock_return"],
            "abs_car": abs(row["stock_return"]),
        })

    return pd.DataFrame(rows), det


# ---------------------------------------------------------------------------
# Hyperparameter sweeps
# ---------------------------------------------------------------------------

def run_pen_sweep(
    ticker, stock_path, market_path, news_path, results_dir, start, end, top_k,
    pen_values=(3, 4, 5, 6, 8, 10, 15),
    price_df_with_volume=None,
):
    """Sweep PELT penalty and return results for each value."""
    all_results = []
    for pen in pen_values:
        events_df, det = run_full_pipeline(
            ticker, stock_path, market_path, news_path, results_dir,
            start, end, top_k, pen=pen,
        )
        price_df = price_df_with_volume if price_df_with_volume is not None else det.price_df

        metrics = compute_metrics(events_df, price_df, det.news_df, top_k=top_k)
        metrics["config_name"] = f"pen={pen}"
        metrics["ticker"] = ticker
        all_results.append(metrics)
        print(f"  pen={pen}: events={metrics['n_events']}, "
              f"F1={metrics['f1']:.3f}, VolRatio={metrics['volume_ratio']:.2f}")

    return all_results


def run_window_sweep(
    ticker, stock_path, market_path, news_path, results_dir, start, end, top_k,
    window_values=(1, 2, 3, 5, 7),
    price_df_with_volume=None,
):
    """Sweep CAR window size."""
    all_results = []
    for w in window_values:
        det = EventDetector(
            ticker=ticker,
            stock_path=stock_path,
            market_path=market_path,
            news_path=news_path,
            results_dir=results_dir,
            start_time=start,
            end_time=end,
            top_k_events=top_k,
            pen=6,
            window_left=w,
            window_right=w,
        )
        det.load_data()
        det.setup_car()

        cp_ret, cp_vol = det.detect_change_points()
        windows = det.build_windows(cp_ret) + det.build_windows(cp_vol)
        merged = det.merge_windows(windows)
        events_df = det.score_events(merged).head(top_k)

        price_df = price_df_with_volume if price_df_with_volume is not None else det.price_df
        metrics = compute_metrics(events_df, price_df, det.news_df, top_k=top_k)
        metrics["config_name"] = f"window=+-{w}"
        metrics["ticker"] = ticker
        all_results.append(metrics)
        print(f"  window=+-{w}: events={metrics['n_events']}, "
              f"F1={metrics['f1']:.3f}, VolRatio={metrics['volume_ratio']:.2f}")

    return all_results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

ABLATION_CONFIGS = {
    "full_pipeline": run_full_pipeline,
    "no_pelt": run_no_pelt,
    "no_car": run_no_car,
    "random_baseline": run_random_baseline,
}

# Column definitions: (header, dict_key, format_string)
PRIMARY_COLS = [
    ("Config",    "config_name",         "{}"),
    ("Ticker",    "ticker",              "{}"),
    ("#Evt",      "n_events",            "{}"),
    ("HitRate",   "hit_rate",            "{:.3f}"),
    ("Coverage",  "coverage",            "{:.3f}"),
    ("F1",        "f1",                  "{:.3f}"),
    ("VolRatio",  "volume_ratio",        "{:.2f}"),
    ("NewsDens",  "news_density_event",  "{:.2f}"),
    ("RandNews",  "news_density_random", "{:.2f}"),
    ("Redund%",   "redundancy_rate",     "{:.2%}"),
]

SECONDARY_COLS = [
    ("Config",       "config_name",          "{}"),
    ("Ticker",       "ticker",               "{}"),
    ("Mean|CAR|",    "mean_abs_car",         "{:.4f}"),
    ("Rand|Ret|",    "random_mean_abs_return", "{:.4f}"),
    ("p-value",      "car_ttest_pvalue",     "{:.4f}"),
]


def _print_table(title: str, results: list[dict], cols: list[tuple]):
    """Pretty-print a results table with a title."""
    if not results:
        print(f"\n{title}\n  (no results)\n")
        return

    header = " | ".join(f"{name:>10}" for name, _, _ in cols)
    width = len(header)

    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")
    print(header)
    print("-" * width)

    for r in results:
        row = []
        for name, key, fmt in cols:
            val = r.get(key, "")
            try:
                row.append(f"{fmt.format(val):>10}")
            except (ValueError, TypeError):
                row.append(f"{str(val):>10}")
        print(" | ".join(row))

    print("=" * width)


def print_results(results: list[dict]):
    """Print primary and secondary tables separately."""
    _print_table(
        "PRIMARY METRICS (independent of CAR — no circularity)",
        results,
        PRIMARY_COLS,
    )
    _print_table(
        "SECONDARY METRICS (CAR-based — partially circular, sanity check only)",
        results,
        SECONDARY_COLS,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ChronoStock Evaluation & Ablation Framework",
        epilog=(
            "Primary metrics (Hit Rate, Coverage, F1, Volume Ratio) are fully "
            "independent of CAR and safe for cross-config comparison. "
            "Secondary metrics (Mean |CAR|, p-value) are partially circular "
            "since the pipeline ranks events by CAR."
        ),
    )
    parser.add_argument("--tickers", default="NVDA,AAPL,TSLA,MSFT,AMZN",
                        help="Comma-separated tickers")
    parser.add_argument("--market", default="^DJI", help="Market benchmark ticker")
    parser.add_argument("--start", default="2021-04-01", help="Start date")
    parser.add_argument("--end", default="2026-03-20", help="End date")
    parser.add_argument("--top-k", type=int, default=20, help="Top-k events to evaluate")
    parser.add_argument("--pen", type=int, default=6, help="PELT penalty (for full pipeline)")
    parser.add_argument("--cache-dir", default="./eval_cache", help="Cache dir for price CSVs")
    parser.add_argument("--news-dir", default=None,
                        help="Directory with cleaned news CSVs (ticker.csv). "
                             "If not set, news metrics are skipped.")
    parser.add_argument("--ablation-only", action="store_true",
                        help="Run only ablation (skip sweeps)")
    parser.add_argument("--sweep-only", action="store_true",
                        help="Run only hyperparameter sweeps (skip ablation)")
    parser.add_argument("--output-csv", default=None,
                        help="Save results to CSV file")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    results_dir = tempfile.mkdtemp(prefix="chrono_eval_")

    all_results = []

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"  Evaluating: {ticker}")
        print(f"{'='*60}")

        stock_path, market_path = fetch_prices(
            ticker, args.market, args.start, args.end, args.cache_dir,
        )

        news_path = None
        if args.news_dir:
            candidate = os.path.join(args.news_dir, f"{ticker}.csv")
            if os.path.exists(candidate):
                news_path = candidate
            else:
                print(f"  Warning: no news CSV for {ticker} at {candidate}")

        if news_path is None:
            news_path = os.path.join(results_dir, f"{ticker}_empty_news.csv")
            pd.DataFrame(columns=["published_utc", "title"]).to_csv(news_path, index=False)

        full_price_df = load_price_df(stock_path, market_path)

        # -- Ablation experiments --
        if not args.sweep_only:
            print(f"\n--- Ablation Study ---")
            for config_name, runner in ABLATION_CONFIGS.items():
                print(f"  Running: {config_name}")
                try:
                    events_df, det = runner(
                        ticker=ticker,
                        stock_path=stock_path,
                        market_path=market_path,
                        news_path=news_path,
                        results_dir=results_dir,
                        start=args.start,
                        end=args.end,
                        top_k=args.top_k,
                        pen=args.pen,
                    )

                    metrics = compute_metrics(events_df, full_price_df, det.news_df, top_k=args.top_k)
                    metrics["config_name"] = config_name
                    metrics["ticker"] = ticker
                    all_results.append(metrics)

                    print(f"    -> F1={metrics['f1']:.3f}, "
                          f"HitRate={metrics['hit_rate']:.3f}, "
                          f"Coverage={metrics['coverage']:.3f}, "
                          f"VolRatio={metrics['volume_ratio']:.2f}")
                except Exception as e:
                    print(f"    ERROR: {e}")

        # -- Hyperparameter sweeps --
        if not args.ablation_only:
            print(f"\n--- PELT Penalty Sweep ---")
            pen_results = run_pen_sweep(
                ticker, stock_path, market_path, news_path, results_dir,
                args.start, args.end, args.top_k,
                price_df_with_volume=full_price_df,
            )
            all_results.extend(pen_results)

            print(f"\n--- CAR Window Sweep ---")
            win_results = run_window_sweep(
                ticker, stock_path, market_path, news_path, results_dir,
                args.start, args.end, args.top_k,
                price_df_with_volume=full_price_df,
            )
            all_results.extend(win_results)

    # -- Final output --
    print("\n\n" + "=" * 60)
    print("  FINAL RESULTS")
    print("=" * 60)
    print_results(all_results)

    if args.output_csv:
        df_out = pd.DataFrame(all_results)
        # Reorder columns: primary first, secondary last
        primary_keys = [k for _, k, _ in PRIMARY_COLS]
        secondary_keys = [k for _, k, _ in SECONDARY_COLS if k not in primary_keys]
        ordered = [c for c in primary_keys + secondary_keys if c in df_out.columns]
        remaining = [c for c in df_out.columns if c not in ordered]
        df_out = df_out[ordered + remaining]
        df_out.to_csv(args.output_csv, index=False)
        print(f"\nResults saved to {args.output_csv}")


if __name__ == "__main__":
    main()
