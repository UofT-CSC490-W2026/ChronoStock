from .run_daily_update import build_update_tickers, refresh_prices


def main() -> None:
    tickers = build_update_tickers()
    refresh_prices(tickers)
    print(f"Hourly update complete for {len(tickers)} ticker(s).")


if __name__ == "__main__":
    main()
