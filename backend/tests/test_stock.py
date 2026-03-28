from datetime import datetime

import pandas as pd
import pytest

from app import stock


def test_unix_to_date_valid_and_invalid() -> None:
    assert stock._unix_to_date(0) == "1970-01-01"
    assert stock._unix_to_date("bad") is None


def test_fetch_bars_success(monkeypatch: pytest.MonkeyPatch) -> None:
    df = pd.DataFrame(
        {
            "Open": [10.111],
            "High": [12.345],
            "Low": [9.001],
            "Close": [11.999],
            "Volume": [1234],
        },
        index=[pd.Timestamp("2026-01-02")],
    )

    def fake_download(*args, **kwargs):
        return df

    monkeypatch.setattr(stock.yf, "download", fake_download)

    bars = stock.fetch_bars("NVDA")
    assert len(bars) == 1
    assert bars[0].time == "2026-01-02"
    assert bars[0].open == 10.11
    assert bars[0].high == 12.35
    assert bars[0].low == 9.0
    assert bars[0].close == 12.0
    assert bars[0].volume == 1234


def test_fetch_bars_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stock.yf, "download", lambda *args, **kwargs: pd.DataFrame())
    with pytest.raises(ValueError, match="No data returned"):
        stock.fetch_bars("NVDA")


def test_fetch_info_maps_fields_and_asset_type(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        info = {
            "longName": "NVIDIA Corp",
            "recommendationKey": "strong_buy",
            "marketCap": 100,
            "totalRevenue": 200,
            "trailingEps": 3.2,
            "exDividendDate": 1704067200,
            "earningsTimestamp": 1706745600,
            "quoteType": "EQUITY",
        }

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())

    company, meta, asset = stock.fetch_info("nvda")
    assert company == "NVIDIA Corp"
    assert asset == "equity"
    assert meta.marketCap == 100
    assert meta.revenue == 200
    assert meta.analystRating == "Strong Buy"
    assert meta.exDividendDate == "2024-01-01"
    assert meta.earningsDate == "2024-02-01"


def test_fetch_info_fallbacks_unknown_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        info = {"shortName": "Short Name", "quoteType": "SOMETHING_ELSE"}

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())

    company, _, asset = stock.fetch_info("abc")
    assert company == "Short Name"
    assert asset == "unknown"


def test_fetch_info_company_name_falls_back_to_ticker_upper(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        info = {}

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())
    company, _, _ = stock.fetch_info("msft")
    assert company == "MSFT"


def test_fetch_earnings_dates_exception_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_ticker(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(stock.yf, "Ticker", broken_ticker)
    assert stock.fetch_earnings_dates("NVDA") == []


def test_fetch_earnings_dates_none_or_empty_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoneTicker:
        earnings_dates = None

    class EmptyTicker:
        earnings_dates = pd.DataFrame()

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: NoneTicker())
    assert stock.fetch_earnings_dates("NVDA") == []

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: EmptyTicker())
    assert stock.fetch_earnings_dates("NVDA") == []


def test_fetch_earnings_dates_parses_and_sorts(monkeypatch: pytest.MonkeyPatch) -> None:
    df = pd.DataFrame(
        {
            "EPS Estimate": [1.0, float("nan")],
            "Reported EPS": [1.1, "bad"],
            "Surprise(%)": [10.0, None],
        },
        index=[pd.Timestamp("2026-03-01"), pd.Timestamp("2026-01-01")],
    )

    class FakeTicker:
        earnings_dates = df

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())

    items = stock.fetch_earnings_dates("NVDA")
    assert [i.date for i in items] == ["2026-01-01", "2026-03-01"]
    assert items[0].epsEstimate is None
    assert items[0].reportedEps is None
    assert items[0].surprisePct is None
    assert items[1].epsEstimate == 1.0


def test_fetch_earnings_dates_skips_unparseable_index(monkeypatch: pytest.MonkeyPatch) -> None:
    df = pd.DataFrame(
        {
            "EPS Estimate": [1.0, 2.0],
            "Reported EPS": [1.1, 2.1],
            "Surprise(%)": [10.0, 20.0],
        },
        index=["bad-date", pd.Timestamp("2026-03-01")],
    )

    class FakeTicker:
        earnings_dates = df

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())

    items = stock.fetch_earnings_dates("NVDA")
    assert [i.date for i in items] == ["2026-03-01"]


def test_fetch_news_handles_transforms_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_news = [
        {
            "id": "1",
            "content": {
                "title": "First",
                "provider": {"displayName": "Provider A"},
                "canonicalUrl": {"url": "https://a.com"},
                "pubDate": "2026-01-01T10:00:00Z",
                "summary": "Summary A",
                "thumbnail": {
                    "resolutions": [
                        {"url": "small", "width": 100},
                        {"url": "big", "width": 400},
                    ]
                },
            },
        },
        {
            "id": "1",  # duplicate id
            "content": {"title": "Duplicate Should Skip"},
        },
        {
            "id": "2",
            "title": "Legacy title",
            "publisher": "Legacy Publisher",
            "providerPublishTime": 1704067200,
            "description": "Legacy description",
            "url": "https://legacy.com",
        },
        {
            "id": "3",
            "content": {"title": ""},  # empty title should skip
        },
    ]

    class FakeTicker:
        news = raw_news

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())

    items = stock.fetch_news("NVDA", limit=50)
    assert len(items) == 2
    assert items[0].id == "1"  # sorted most recent first
    assert items[1].id == "2"
    assert items[0].thumbnail == "big"
    assert items[0].publisher == "Provider A"


def test_fetch_news_limit_is_capped_to_min_one(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        news = [
            {"id": "1", "content": {"title": "A", "pubDate": "2026-01-01T00:00:00Z"}},
            {"id": "2", "content": {"title": "B", "pubDate": "2026-01-02T00:00:00Z"}},
        ]

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())
    items = stock.fetch_news("NVDA", limit=0)
    assert len(items) == 1


def test_fetch_news_falls_back_when_pub_date_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTicker:
        news = [
            {
                "id": "1",
                "content": {
                    "title": "A",
                    "pubDate": "not-a-date",
                },
            }
        ]

    monkeypatch.setattr(stock.yf, "Ticker", lambda *_: FakeTicker())
    items = stock.fetch_news("NVDA", limit=5)

    assert len(items) == 1
    assert items[0].time == "not-a-date"[:10]


def test_search_tickers_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    stock._search_cache.clear()

    class FakeSearch:
        def __init__(self, *_args, **_kwargs):
            self.quotes = [
                {"symbol": "NVDA", "longname": "NVIDIA"},
                {"symbol": "AAPL", "shortname": "Apple"},
                {"longname": "MissingSymbol"},
            ]

    monkeypatch.setattr(stock.yf, "Search", FakeSearch)
    hits = stock.search_tickers("n")
    assert hits == [
        {"ticker": "NVDA", "companyName": "NVIDIA"},
        {"ticker": "AAPL", "companyName": "Apple"},
    ]

    def broken_search(*_args, **_kwargs):
        raise RuntimeError("search broken")

    monkeypatch.setattr(stock.yf, "Search", broken_search)
    assert stock.search_tickers("other") == []


def test_search_tickers_uses_cached_results_until_ttl_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    stock._search_cache.clear()
    calls = {"count": 0}

    class FakeSearch:
        def __init__(self, *_args, **_kwargs):
            calls["count"] += 1
            self.quotes = [{"symbol": "NVDA", "longname": "NVIDIA"}]

    now = {"value": 1000.0}
    monkeypatch.setattr(stock.yf, "Search", FakeSearch)
    monkeypatch.setattr(stock, "time", lambda: now["value"])

    first = stock.search_tickers("nvda")
    second = stock.search_tickers("nvda")

    now["value"] += stock._SEARCH_CACHE_TTL + 1
    third = stock.search_tickers("nvda")

    assert first == [{"ticker": "NVDA", "companyName": "NVIDIA"}]
    assert second == first
    assert third == first
    assert calls["count"] == 2


def test_search_tickers_caches_empty_results_after_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    stock._search_cache.clear()
    calls = {"count": 0}

    def broken_search(*_args, **_kwargs):
        calls["count"] += 1
        raise RuntimeError("search broken")

    monkeypatch.setattr(stock.yf, "Search", broken_search)
    monkeypatch.setattr(stock, "time", lambda: 1000.0)

    first = stock.search_tickers("broken")
    second = stock.search_tickers("broken")

    assert first == []
    assert second == []
    assert calls["count"] == 1
