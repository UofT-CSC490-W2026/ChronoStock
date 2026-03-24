import os
from datetime import datetime, timezone

from yahooquery import Ticker as YQTicker, get_trending

from . import cache
from .edgar import fetch_sec_filings
from .main import StockResponse
from .stock import fetch_bars, fetch_earnings_dates, fetch_info, fetch_news


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tickers_from_env() -> list[str]:
    raw = os.environ.get("DAILY_UPDATE_TICKERS", "")
    return [ticker.strip().upper() for ticker in raw.split(",") if ticker.strip()]


def refresh_stock_bundle(ticker: str) -> None:
    bars = fetch_bars(ticker)
    company_name, meta = fetch_info(ticker)

    payload = StockResponse(
        ticker=ticker,
        companyName=company_name,
        bars=bars,
        events=[],
        meta=meta,
    ).model_dump()
    payload["cached_at"] = _now_iso()
    cache.set(f"stock:{ticker}", payload)


def refresh_earnings(ticker: str) -> None:
    items = fetch_earnings_dates(ticker)
    cache.set(
        f"earnings:{ticker}",
        {
            "cached_at": _now_iso(),
            "items": [item.model_dump() for item in items],
        },
    )


def refresh_news(ticker: str) -> None:
    items = fetch_news(ticker)
    cache.set(
        f"news:{ticker}",
        {
            "cached_at": _now_iso(),
            "items": [item.model_dump() for item in items],
        },
    )


def refresh_sec_filings(ticker: str) -> None:
    items = fetch_sec_filings(ticker)
    cache.set(
        f"sec:filings:{ticker}",
        {
            "cached_at": _now_iso(),
            "items": [item.model_dump() for item in items],
        },
    )


def refresh_prices(tickers: list[str]) -> None:
    if not tickers:
        return

    price_data = YQTicker(tickers).price
    for ticker in tickers:
        info = price_data.get(ticker, {})
        if not isinstance(info, dict):
            continue

        payload = {
            "ticker": ticker,
            "companyName": info.get("longName") or info.get("shortName") or ticker,
            "price": info.get("regularMarketPrice"),
            "change": info.get("regularMarketChange"),
            "changePct": info.get("regularMarketChangePercent"),
            "cached_at": _now_iso(),
        }
        cache.set(f"price:{ticker}", payload)


def refresh_trending() -> list[str]:
    data = get_trending()
    quotes = data.get("quotes", [])
    tickers = [q["symbol"] for q in quotes if not q["symbol"].startswith("^")][:12]

    if not tickers:
        cache.set("trending", {"cached_at": _now_iso(), "items": []})
        return []

    price_data = YQTicker(tickers).price
    items = []
    for ticker in tickers:
        info = price_data.get(ticker, {})
        if not isinstance(info, dict):
            continue
        items.append(
            {
                "ticker": ticker,
                "companyName": info.get("longName") or info.get("shortName") or ticker,
                "price": info.get("regularMarketPrice"),
                "change": info.get("regularMarketChange"),
                "changePct": info.get("regularMarketChangePercent"),
            }
        )

    cache.set("trending", {"cached_at": _now_iso(), "items": items})
    return tickers


def main() -> None:
    env_tickers = _tickers_from_env()
    trending_tickers = refresh_trending()

    # Keep explicit tickers first, then append trending names without duplicates.
    tickers = list(dict.fromkeys(env_tickers + trending_tickers))
    refresh_prices(tickers)

    for ticker in tickers:
        print(f"Refreshing {ticker}...")
        refresh_stock_bundle(ticker)
        refresh_earnings(ticker)
        refresh_news(ticker)
        refresh_sec_filings(ticker)

    print(f"Daily update complete for {len(tickers)} ticker(s).")


if __name__ == "__main__":
    main()
