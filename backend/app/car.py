import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression


class CARCalculator:
    def __init__(self, stock_path, market_path):
        self.stock_path = stock_path
        self.market_path = market_path

        self.data = None
        self.alpha = None
        self.beta = None

    def load_data(self):
        stock = pd.read_csv(self.stock_path, parse_dates=["Date"])
        market = pd.read_csv(self.market_path, parse_dates=["Date"])

        # Your CSV uses Close instead of Adj Close
        stock = stock[["Date", "Close"]].rename(columns={"Close": "stock_price"})
        market = market[["Date", "Close"]].rename(columns={"Close": "market_price"})

        df = pd.merge(stock, market, on="Date", how="inner")
        df = df.sort_values("Date")

        # Compute returns
        df["stock_return"] = df["stock_price"].pct_change()
        df["market_return"] = df["market_price"].pct_change()

        df = df.dropna().reset_index(drop=True)
        self.data = df

        print("Loaded data:", len(df), "rows")

    def fit_market_model(self, estimation_window=252):
        df = self.data.iloc[:estimation_window]

        X = df[["market_return"]].values
        y = df["stock_return"].values

        model = LinearRegression()
        model.fit(X, y)

        self.alpha = model.intercept_
        self.beta = model.coef_[0]

        print(f"alpha: {self.alpha:.6f}")
        print(f"beta: {self.beta:.4f}")

    def compute_abnormal_returns(self):
        df = self.data.copy()

        df["expected_return"] = self.alpha + self.beta * df["market_return"]
        df["abnormal_return"] = df["stock_return"] - df["expected_return"]

        self.data = df

    def compute_car(
        self,
        event_date,
        window_before=3,
        window_after=3,
        report_weight=0.7,
        report_months=None,
        negative_weight=0.8,
    ):
        df = self.data
        event_date = pd.to_datetime(event_date)

        if report_months is None:
            report_months = {1, 5, 7, 11}

        idx = df.index[df["Date"] == event_date]
        if len(idx) == 0:
            raise ValueError("Event date not found")

        idx = idx[0]

        start = max(0, idx - window_before)
        end = min(len(df) - 1, idx + window_after)

        window = df.iloc[start:end + 1]
        car = window["abnormal_return"].sum()

        if event_date.month in report_months:
            car *= report_weight

        if car < 0:
            car *= negative_weight

        return car, window

    def get_top_k_events(
        self,
        k=5,
        window_before=3,
        window_after=3,
        start_date=None,
        end_date=None,
        report_weight=0.7,
        report_months=None,
        negative_weight=0.8,
        merge_window=7,
    ):
        """
        Get top-k dates with highest absolute CAR in rolling event windows,
        optionally within a date range. Nearby lower-ranked events within
        merge_window days of a stronger event are skipped.

        Parameters:
            k: number of top events to return
            window_before: days before event to include in CAR
            window_after: days after event to include in CAR
            start_date: filter start date (inclusive), string 'YYYY-MM-DD' or pd.Timestamp
            end_date: filter end date (inclusive), string 'YYYY-MM-DD' or pd.Timestamp
            merge_window: skip events within +/- this many calendar days of a stronger event

        Returns:
            List of tuples: (event_date, CAR, window_df)
        """
        df = self.data.copy()

        # filter by date range if given
        if start_date is not None:
            df = df[df["Date"] >= pd.to_datetime(start_date)]
        if end_date is not None:
            df = df[df["Date"] <= pd.to_datetime(end_date)]

        if report_months is None:
            report_months = {1, 5, 7, 11}

        results = []

        for i in range(len(df)):
            event_date = df.iloc[i]["Date"]
            start = max(0, i - window_before)
            end = min(len(df) - 1, i + window_after)
            window = df.iloc[start:end + 1]
            car = window["abnormal_return"].sum()

            if event_date.month in report_months:
                car *= report_weight

            if car < 0:
                car *= negative_weight

            results.append((event_date, car, window))

        # Sort by absolute CAR descending so the strongest nearby event wins.
        results.sort(key=lambda x: abs(x[1]), reverse=True)

        merged_results = []

        for event_date, car, window in results:
            if any(abs((event_date - kept_date).days) <= merge_window for kept_date, _, _ in merged_results):
                continue

            merged_results.append((event_date, car, window))

            if len(merged_results) == k:
                break

        return merged_results

if __name__ == "__main__":
    car_model = CARCalculator(
        stock_path="./data/stock_prices/NVDA.csv",
        market_path="./data/stock_prices/^DJI.csv"
    )

    car_model.load_data()
    car_model.fit_market_model()
    car_model.compute_abnormal_returns()

    top_events = car_model.get_top_k_events(
        k=20,
        window_before=7,
        window_after=7,
        start_date="2016-01-01",
        end_date="2026-03-20"
    )

    for date, car, window in top_events:
        print(f"Event date: {date.date()}, Adjusted CAR: {car:.6f}")
        # print(window[["Date", "abnormal_return"]])
        print("---")

    car, window = car_model.compute_car("2022-09-01", window_before=7, window_after=7)
    print(f"Adjusted CAR for event on 2022-09-01: {car:.6f}")