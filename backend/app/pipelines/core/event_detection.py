import os
import numpy as np
import pandas as pd
import ruptures as rpt

from .car import CARCalculator


class EventDetector:
    def _normalize_time_arg(self, value, label):
        if value is None:
            return None

        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            raise ValueError(f"Invalid {label}: {value}")

        if getattr(timestamp, "tzinfo", None) is not None:
            timestamp = timestamp.tz_localize(None)

        return timestamp

    def __init__(
        self,
        ticker,
        stock_path,
        market_path,
        news_path,
        results_dir="./data/events",
        start_time=None,
        end_time=None,
        news_window_days=2,
        pen=6,
        window_left=3,
        window_right=3,
        top_k_events=20,
    ):
        self.ticker = ticker
        self.stock_path = stock_path
        self.market_path = market_path
        self.news_path = news_path
        self.results_dir = results_dir

        self.start_time = self._normalize_time_arg(start_time, "start_time")
        self.end_time = self._normalize_time_arg(end_time, "end_time")
        self.news_window_days = news_window_days
        self.pen = pen
        self.window_left = window_left
        self.window_right = window_right
        self.top_k_events = top_k_events

        if self.start_time is not None and self.end_time is not None:
            if self.start_time > self.end_time:
                raise ValueError("start_time must be earlier than or equal to end_time")

        os.makedirs(results_dir, exist_ok=True)

        self.price_df = None
        self.news_df = None
        self.car_model = None

    def _get_detection_df(self):
        df = self.price_df.copy()

        if self.start_time is not None:
            df = df[df["Date"] >= self.start_time]
        if self.end_time is not None:
            df = df[df["Date"] <= self.end_time]

        if df.empty:
            raise ValueError("No price data available in the requested time range")

        return df

    # -----------------------------
    # Load data
    # -----------------------------
    def load_data(self):
        stock = pd.read_csv(self.stock_path, parse_dates=["Date"])
        market = pd.read_csv(self.market_path, parse_dates=["Date"])

        stock = stock[["Date", "Close"]].rename(columns={"Close": "stock_price"})
        market = market[["Date", "Close"]].rename(columns={"Close": "market_price"})

        df = pd.merge(stock, market, on="Date", how="inner")
        df = df.sort_values("Date").reset_index(drop=True)

        # ensure NO timezone
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)

        # returns
        df["stock_return"] = df["stock_price"].pct_change()
        df["market_return"] = df["market_price"].pct_change()

        df = df.dropna().reset_index(drop=True)

        # volatility (10-day rolling std)
        df["volatility"] = df["stock_return"].rolling(10).std()

        df = df.dropna().reset_index(drop=True)

        self.price_df = df

        # Load news
        self.news_df = pd.read_csv(self.news_path)

        self.news_df["published_utc"] = pd.to_datetime(
            self.news_df["published_utc"],
            errors="coerce"
        ).dt.tz_localize(None)

        self.news_df = self.news_df.dropna(subset=["published_utc"])

        print("Loaded price rows:", len(self.price_df))
        print("Loaded news rows:", len(self.news_df))

    # -----------------------------
    # Setup CAR model
    # -----------------------------
    def setup_car(self):
        self.car_model = CARCalculator(
            stock_path=self.stock_path,
            market_path=self.market_path,
        )

        self.car_model.load_data()
        self.car_model.fit_market_model()
        self.car_model.compute_abnormal_returns()

    # -----------------------------
    # Run PELT
    # -----------------------------
    def run_pelt(self, series):
        series = series.dropna()

        algo = rpt.Pelt(model="l2").fit(series.values)
        cps = algo.predict(pen=self.pen)

        # remove final endpoint
        cps = cps[:-1]

        return cps

    # -----------------------------
    # Detect change points
    # -----------------------------
    def detect_change_points(self):
        df = self._get_detection_df()

        abs_returns = np.abs(df["stock_return"])
        abs_returns = (abs_returns - abs_returns.mean()) / abs_returns.std()

        volatility = df["volatility"]
        volatility = (volatility - volatility.mean()) / volatility.std()

        cp_returns = self.run_pelt(abs_returns)
        cp_vol = self.run_pelt(volatility)

        index_positions = df.index.to_list()

        cp_returns = [
            index_positions[cp]
            for cp in cp_returns
            if 0 <= cp < len(index_positions)
        ]
        cp_vol = [
            index_positions[cp]
            for cp in cp_vol
            if 0 <= cp < len(index_positions)
        ]

        print("Change points (returns):", len(cp_returns))
        print("Change points (volatility):", len(cp_vol))

        return cp_returns, cp_vol

    # -----------------------------
    # Build windows
    # -----------------------------
    def build_windows(self, cp_list):
        windows = []

        n = len(self.price_df)

        for cp in cp_list:
            start = max(0, cp - self.window_left)
            end = min(n - 1, cp + self.window_right)
            windows.append((start, end))

        return windows

    # -----------------------------
    # Merge windows
    # -----------------------------
    def merge_windows(self, windows):
        if len(windows) == 0:
            return []

        windows = sorted(windows)
        merged = [list(windows[0])]

        for start, end in windows[1:]:
            prev_start, prev_end = merged[-1]

            if start <= prev_end:
                merged[-1][1] = max(prev_end, end)
            else:
                merged.append([start, end])

        return merged

    # -----------------------------
    # Score events using CAR
    # -----------------------------
    def score_events(self, merged_windows):
        events = []

        for start, end in merged_windows:
            center_idx = (start + end) // 2

            if center_idx >= len(self.price_df):
                continue

            event_date = self.price_df.iloc[center_idx]["Date"]
            event_date = pd.Timestamp(event_date).tz_localize(None)

            try:
                car, _ = self.car_model.compute_car(
                    event_date,
                    window_before=3,
                    window_after=3,
                )
            except Exception as e:
                print("CAR failed for:", event_date, "|", e)
                continue

            events.append(
                {
                    "event_date": event_date,
                    "start_idx": start,
                    "end_idx": end,
                    "car": car,
                    "abs_car": abs(car),
                }
            )

        if len(events) == 0:
            print("WARNING: No events detected after CAR scoring.")
            return pd.DataFrame(
                columns=["event_date", "start_idx", "end_idx", "car", "abs_car"]
            )

        events_df = pd.DataFrame(events)

        events_df = (
            events_df
            .sort_values("abs_car", ascending=False)
            .reset_index(drop=True)
        )

        return events_df

    # -----------------------------
    # Attach news
    # -----------------------------
    def attach_news(self, events_df):
        results = []

        for _, row in events_df.iterrows():
            event_date = row["event_date"]

            start = event_date - pd.Timedelta(days=self.news_window_days)
            end = event_date + pd.Timedelta(days=self.news_window_days)

            news_subset = self.news_df[
                (self.news_df["published_utc"] >= start)
                & (self.news_df["published_utc"] <= end)
            ]

            for _, news in news_subset.iterrows():
                result = row.to_dict()
                result.update(news.to_dict())
                results.append(result)

        results_df = pd.DataFrame(results)
        if results_df.empty:
            return pd.DataFrame(columns=list(events_df.columns) + list(self.news_df.columns))
        return results_df

    # -----------------------------
    # Full pipeline
    # -----------------------------
    def run(self):
        self.load_data()
        self.setup_car()

        cp_returns, cp_vol = self.detect_change_points()

        windows_returns = self.build_windows(cp_returns)
        windows_vol = self.build_windows(cp_vol)

        # union of both signals
        all_windows = windows_returns + windows_vol

        merged_windows = self.merge_windows(all_windows)

        print("Merged windows:", len(merged_windows))

        events_df = self.score_events(merged_windows)

        events_df = events_df.head(self.top_k_events)

        results_df = self.attach_news(events_df)

        if not events_df.empty and "event_date" in events_df.columns:
            events_df.sort_values("event_date", inplace=True)
        if not results_df.empty and "event_date" in results_df.columns:
            results_df.sort_values("event_date", inplace=True)
        output_path = os.path.join(self.results_dir, f"{self.ticker}.csv")
        results_df.to_csv(output_path, index=False)

        print("Saved:", output_path)

        return events_df, results_df


# -----------------------------
# Run experiment
# -----------------------------
if __name__ == "__main__":
    detector = EventDetector(
        ticker="NVDA",
        stock_path="./data/stock_prices/NVDA.csv",
        market_path="./data/stock_prices/^DJI.csv",
        news_path="./data/stock_news_cleaned/NVDA.csv",
        start_time="2021-04-24",
        end_time="2026-03-20",
        news_window_days=2,
        pen=4,
        window_left=3,
        window_right=3,
        top_k_events=25,
    )

    events, news = detector.run()

    print(events)
