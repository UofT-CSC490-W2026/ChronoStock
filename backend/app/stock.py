"""
yfinance wrapper — fetches OHLC bars, company info, and fundamentals.

We always fetch the full available history (period="max") and store it as one
file per ticker. Range filtering happens in main.py after reading from cache.
"""
from datetime import datetime, timezone
import yfinance as yf
from .models import OHLCBar, StockMeta, StockNews, EarningsDate


def fetch_bars(ticker: str) -> list[OHLCBar]:
    """Fetch the complete available price history for a ticker."""
    df = yf.download(ticker, period="max", auto_adjust=True, progress=False, multi_level_index=False)

    if df.empty:
        raise ValueError(f"No data returned for {ticker}")

    bars: list[OHLCBar] = []
    for ts, row in df.iterrows():
        bars.append(
            OHLCBar(
                time=ts.strftime("%Y-%m-%d"),
                open=round(float(row["Open"]), 2),
                high=round(float(row["High"]), 2),
                low=round(float(row["Low"]), 2),
                close=round(float(row["Close"]), 2),
                volume=int(row["Volume"]),
            )
        )
    return bars


def _unix_to_date(ts) -> str | None:
    """Convert a unix timestamp (int) to a YYYY-MM-DD string."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def fetch_info(ticker: str) -> tuple[str, StockMeta]:
    """
    Single yfinance call that returns (companyName, StockMeta).
    Avoids calling .info twice.
    """
    info = yf.Ticker(ticker).info

    company_name = info.get("longName") or info.get("shortName") or ticker.upper()

    # Analyst recommendation → human-readable label
    ANALYST_MAP = {
        "strong_buy": "Strong Buy",
        "buy": "Buy",
        "hold": "Hold",
        "underperform": "Underperform",
        "sell": "Sell",
    }
    analyst_raw = info.get("recommendationKey", "")
    analyst = ANALYST_MAP.get(analyst_raw)

    meta = StockMeta(
        marketCap=info.get("marketCap"),
        revenue=info.get("totalRevenue"),
        netIncome=info.get("netIncomeToCommon"),
        eps=info.get("trailingEps"),
        sharesOutstanding=info.get("sharesOutstanding"),
        peRatio=info.get("trailingPE"),
        forwardPE=info.get("forwardPE"),
        dividendRate=info.get("dividendRate"),
        dividendYield=info.get("dividendYield"),
        exDividendDate=_unix_to_date(info.get("exDividendDate")),
        volume=info.get("volume"),
        previousClose=info.get("previousClose"),
        dayLow=info.get("dayLow"),
        dayHigh=info.get("dayHigh"),
        weekLow52=info.get("fiftyTwoWeekLow"),
        weekHigh52=info.get("fiftyTwoWeekHigh"),
        beta=info.get("beta"),
        analystRating=analyst,
        priceTarget=info.get("targetMeanPrice"),
        earningsDate=_unix_to_date(info.get("earningsTimestamp")),
    )

    return company_name, meta


def fetch_earnings_dates(ticker: str) -> list[EarningsDate]:
    """Fetch historical and upcoming earnings dates with EPS data via yfinance."""
    import pandas as pd

    try:
        df = yf.Ticker(ticker).earnings_dates
    except Exception:
        return []

    if df is None or df.empty:
        return []

    items: list[EarningsDate] = []
    for ts, row in df.iterrows():
        try:
            date_str = pd.Timestamp(ts).strftime("%Y-%m-%d")
        except Exception:
            continue

        def _float(val) -> float | None:
            try:
                import math
                f = float(val)
                return None if math.isnan(f) else f
            except Exception:
                return None

        items.append(EarningsDate(
            date=date_str,
            epsEstimate=_float(row.get("EPS Estimate")),
            reportedEps=_float(row.get("Reported EPS")),
            surprisePct=_float(row.get("Surprise(%)")),
        ))

    # Ascending chronological order
    items.sort(key=lambda e: e.date)
    return items


def fetch_news(ticker: str) -> list[StockNews]:
    """Fetch up to 12 recent news articles for a ticker via yfinance."""
    raw = yf.Ticker(ticker).news or []
    items: list[StockNews] = []
    for i, article in enumerate(raw[:12]):
        # yfinance ≥1.2 wraps fields under a 'content' key
        content = article.get("content") or article
        title = content.get("title") or ""
        if not title:
            continue

        # Publisher
        provider = content.get("provider") or {}
        publisher = provider.get("displayName") or article.get("publisher") or ""

        # URL — try canonicalUrl first, then clickThroughUrl, then top-level link
        canon = content.get("canonicalUrl") or {}
        click = content.get("clickThroughUrl") or {}
        url = canon.get("url") or click.get("url") or article.get("link") or article.get("url")

        # Date
        pub_date = content.get("pubDate") or ""
        if pub_date:
            try:
                dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = pub_date[:10]
        else:
            ts = article.get("providerPublishTime")
            date_str = _unix_to_date(ts) or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Summary
        summary = content.get("summary") or content.get("description") or None

        # Thumbnail — pick the largest resolution available
        thumbnail: str | None = None
        thumb_obj = content.get("thumbnail") or article.get("thumbnail") or {}
        resolutions = thumb_obj.get("resolutions") or []
        if resolutions:
            best = max(resolutions, key=lambda r: r.get("width", 0))
            thumbnail = best.get("url")

        items.append(StockNews(
            id=article.get("id") or str(i),
            time=date_str,
            title=title,
            publisher=publisher,
            url=url,
            summary=summary,
            thumbnail=thumbnail,
        ))
    return items


def search_tickers(query: str) -> list[dict]:
    results = []
    try:
        hits = yf.Search(query, max_results=6).quotes
        for h in hits:
            sym = h.get("symbol", "")
            name = h.get("longname") or h.get("shortname") or sym
            if sym:
                results.append({"ticker": sym, "companyName": name})
    except Exception:
        pass
    return results
