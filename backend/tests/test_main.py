from datetime import datetime, timezone
from types import SimpleNamespace
import sys
import sqlite3
from pathlib import Path
import uuid

from fastapi.testclient import TestClient

from app import main
from app.models import EarningsDate, NewsEvent, SECFiling, StockNews, MarketSummary, IndicatorHistory, IndicatorDataPoint, MarketAnalysis


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(main, "init_db", lambda: None)
    return TestClient(main.app)


def _workspace_db_path() -> Path:
    path = Path.cwd() / ".pytest_tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"main_{uuid.uuid4().hex}.db"


def _sqlite_client(monkeypatch) -> TestClient:
    db_path = _workspace_db_path()

    def get_conn():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(main, "get_conn", get_conn)
    monkeypatch.setattr(main, "init_db", lambda: None)

    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (user_id, ticker)
            );
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    return TestClient(main.app)


def test_health_endpoint(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_search_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(main, "search_tickers", lambda _q: [{"ticker": "NVDA", "companyName": "NVIDIA"}])
    with _client(monkeypatch) as client:
        resp = client.get("/api/search", params={"q": "nv"})
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "NVDA", "companyName": "NVIDIA"}]


def test_get_stock_uses_fresh_cache(monkeypatch) -> None:
    cached = {
        "ticker": "NVDA",
        "companyName": "NVIDIA",
        "assetType": "equity",
        "bars": [
            {
                "time": "2026-01-01",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100,
            }
        ],
        "events": [],
        "meta": {},
        "cached_at": _now_iso(),
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "stock:NVDA" else None)
    monkeypatch.setattr(main, "fetch_bars", lambda _ticker: (_ for _ in ()).throw(AssertionError("should not fetch")))
    monkeypatch.setattr(main, "fetch_info", lambda _ticker: (_ for _ in ()).throw(AssertionError("should not fetch")))

    import app.demo_events as demo_events

    monkeypatch.setattr(
        demo_events,
        "get_demo_events",
        lambda _ticker: [
            NewsEvent(
                id="e1",
                time="2025-01-01",
                title="old",
                summary="old",
                sentiment="neutral",
                source="News",
            ),
            NewsEvent(
                id="e2",
                time="2026-01-02",
                title="new",
                summary="new",
                sentiment="positive",
                source="News",
            ),
        ],
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/stock/nvda", params={"range": "ALL"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "NVDA"
    assert len(body["bars"]) == 1
    assert len(body["events"]) == 1
    assert body["events"][0]["id"] == "e2"


def test_get_stock_provider_value_error_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main, "fetch_bars", lambda _ticker: (_ for _ in ()).throw(ValueError("not found")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/stock/xxxx")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "not found"


def test_get_stock_fetches_and_caches_when_cache_stale(monkeypatch) -> None:
    stale = {
        "ticker": "NVDA",
        "companyName": "Old",
        "assetType": "equity",
        "bars": [],
        "events": [],
        "meta": {},
        "cached_at": "2000-01-01T00:00:00+00:00",
    }
    saved = {}
    monkeypatch.setattr(main.cache, "get", lambda _key: stale)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setattr(main, "fetch_bars", lambda _ticker: [main.OHLCBar(time="2026-01-01", open=1, high=1, low=1, close=1, volume=1)])
    monkeypatch.setattr(main, "fetch_info", lambda _ticker: ("NVIDIA", {"sector": "Tech"}, "equity"))
    monkeypatch.setitem(
        sys.modules,
        "app.demo_events",
        SimpleNamespace(get_demo_events=lambda _ticker: []),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/stock/nvda", params={"range": "ALL"})

    assert resp.status_code == 200
    assert saved["key"] == "stock:NVDA"
    assert resp.json()["companyName"] == "NVIDIA"


def test_get_stock_provider_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main, "fetch_bars", lambda _ticker: (_ for _ in ()).throw(RuntimeError("provider down")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/stock/nvda")

    assert resp.status_code == 502
    assert "Data provider error" in resp.json()["detail"]


def test_filter_bars_with_range_filters_old_rows() -> None:
    bars = [
        SimpleNamespace(time="2000-01-01"),
        SimpleNamespace(time=_now_iso()[:10]),
    ]
    filtered = main._filter_bars(bars, "1W")
    assert len(filtered) == 1
    assert filtered[0].time == _now_iso()[:10]


def test_filter_bars_all_returns_original_list() -> None:
    bars = [SimpleNamespace(time="2000-01-01")]
    assert main._filter_bars(bars, "ALL") is bars


def test_prices_uses_cache_and_bulk_fetch(monkeypatch) -> None:
    def fake_cache_get(key):
        if key == "price:AAPL":
            return {
                "ticker": "AAPL",
                "companyName": "Apple",
                "price": 100.0,
                "change": 1.0,
                "changePct": 1.0,
                "cached_at": _now_iso(),
            }
        return None

    cache_sets = []
    monkeypatch.setattr(main.cache, "get", fake_cache_get)
    monkeypatch.setattr(main.cache, "set", lambda key, value: cache_sets.append((key, value)))

    class FakeYQTicker:
        def __init__(self, symbols):
            self.price = {
                "NVDA": {
                    "longName": "NVIDIA",
                    "regularMarketPrice": 900.0,
                    "regularMarketChange": 10.0,
                    "regularMarketChangePercent": 1.12,
                }
            }

    monkeypatch.setitem(sys.modules, "yahooquery", SimpleNamespace(Ticker=FakeYQTicker))

    with _client(monkeypatch) as client:
        resp = client.get("/api/prices", params={"tickers": "AAPL,NVDA"})
    assert resp.status_code == 200
    body = resp.json()
    assert [item["ticker"] for item in body] == ["AAPL", "NVDA"]
    assert any(key == "price:NVDA" for key, _ in cache_sets)


def test_prices_returns_empty_for_blank_input(monkeypatch) -> None:
    with _client(monkeypatch) as client:
        resp = client.get("/api/prices", params={"tickers": " , "})
    assert resp.status_code == 200
    assert resp.json() == []


def test_prices_provider_failure_falls_back_to_symbol_names(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)

    class BrokenTicker:
        def __init__(self, symbols):
            raise RuntimeError("provider down")

    monkeypatch.setitem(sys.modules, "yahooquery", SimpleNamespace(Ticker=BrokenTicker))

    with _client(monkeypatch) as client:
        resp = client.get("/api/prices", params={"tickers": "NVDA,AAPL"})

    assert resp.status_code == 200
    assert resp.json() == [
        {"ticker": "NVDA", "companyName": "NVDA", "price": None, "change": None, "changePct": None},
        {"ticker": "AAPL", "companyName": "AAPL", "price": None, "change": None, "changePct": None},
    ]


def test_prices_handles_non_dict_provider_payload(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)

    class FakeYQTicker:
        def __init__(self, symbols):
            self.price = {"NVDA": "bad-payload"}

    monkeypatch.setitem(sys.modules, "yahooquery", SimpleNamespace(Ticker=FakeYQTicker))

    with _client(monkeypatch) as client:
        resp = client.get("/api/prices", params={"tickers": "NVDA"})

    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "NVDA", "companyName": "NVDA", "price": None, "change": None, "changePct": None}]


def test_prices_ignores_stale_cache_and_refetches(monkeypatch) -> None:
    stale = {
        "ticker": "NVDA",
        "companyName": "Old",
        "price": 1.0,
        "change": 0.1,
        "changePct": 0.1,
        "cached_at": "2000-01-01T00:00:00+00:00",
    }
    saved = {}
    monkeypatch.setattr(main.cache, "get", lambda key: stale if key == "price:NVDA" else None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))

    class FakeYQTicker:
        def __init__(self, symbols):
            self.price = {
                "NVDA": {
                    "shortName": "NVIDIA New",
                    "regularMarketPrice": 900.0,
                    "regularMarketChange": 9.0,
                    "regularMarketChangePercent": 1.0,
                }
            }

    monkeypatch.setitem(sys.modules, "yahooquery", SimpleNamespace(Ticker=FakeYQTicker))

    with _client(monkeypatch) as client:
        resp = client.get("/api/prices", params={"tickers": "NVDA"})

    assert resp.status_code == 200
    assert resp.json()[0]["companyName"] == "NVIDIA New"
    assert saved["key"] == "price:NVDA"


def test_market_summary_refetches_when_cache_is_stale(monkeypatch) -> None:
    saved = {}
    cached = {"categories": [], "cachedAt": "2000-01-01T00:00:00+00:00"}
    summary = MarketSummary(categories=[], cachedAt=_now_iso())
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "market:summary" else None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(sys.modules, "app.macro", SimpleNamespace(fetch_market_summary=lambda: summary))

    with _client(monkeypatch) as client:
        resp = client.get("/api/market-summary")

    assert resp.status_code == 200
    assert saved["key"] == "market:summary"
    assert resp.json()["cachedAt"] == summary.cachedAt


def test_indicator_history_returns_cached_payload(monkeypatch) -> None:
    cached = {
        "name": "Known",
        "unit": "%",
        "data": [{"time": "2026-01-01", "value": 1.2}],
        "cachedAt": _now_iso(),
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "indicator:known" else None)
    monkeypatch.setitem(
        sys.modules,
        "app.macro",
        SimpleNamespace(
            fetch_indicator_history=lambda name: (_ for _ in ()).throw(AssertionError("should not fetch")),
            INDICATOR_MAP={"Known": ("fred_level", "X", "%")},
        ),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/indicator/Known")

    assert resp.status_code == 200
    assert resp.json()["data"][0]["value"] == 1.2


def test_indicator_history_returns_cached_payload_with_naive_timestamp(monkeypatch) -> None:
    cached = {
        "name": "Known",
        "unit": "%",
        "data": [{"time": "2026-01-01", "value": 1.2}],
        "cachedAt": datetime.now().isoformat(),
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "indicator:known" else None)
    monkeypatch.setitem(
        sys.modules,
        "app.macro",
        SimpleNamespace(
            fetch_indicator_history=lambda name: (_ for _ in ()).throw(AssertionError("should not fetch")),
            INDICATOR_MAP={"Known": ("fred_level", "X", "%")},
        ),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/indicator/Known")

    assert resp.status_code == 200
    assert resp.json()["cachedAt"] == cached["cachedAt"]


def test_indicator_history_fetches_when_cache_has_no_timestamp(monkeypatch) -> None:
    saved = {}
    history = IndicatorHistory(
        name="Known",
        unit="%",
        data=[IndicatorDataPoint(time="2026-01-01", value=2.5)],
        cachedAt=_now_iso(),
    )
    monkeypatch.setattr(main.cache, "get", lambda key: {"name": "Known", "unit": "%", "data": []} if key == "indicator:known" else None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(
        sys.modules,
        "app.macro",
        SimpleNamespace(
            fetch_indicator_history=lambda name: history,
            INDICATOR_MAP={"Known": ("fred_level", "X", "%")},
        ),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/indicator/Known")

    assert resp.status_code == 200
    assert saved["key"] == "indicator:known"
    assert resp.json()["data"][0]["value"] == 2.5


def test_indicator_history_refetches_when_naive_cache_is_stale(monkeypatch) -> None:
    saved = {}
    history = IndicatorHistory(
        name="Known",
        unit="%",
        data=[IndicatorDataPoint(time="2026-01-01", value=3.5)],
        cachedAt=_now_iso(),
    )
    monkeypatch.setattr(
        main.cache,
        "get",
        lambda key: {
            "name": "Known",
            "unit": "%",
            "data": [{"time": "2020-01-01", "value": 1.0}],
            "cachedAt": "2000-01-01T00:00:00",
        } if key == "indicator:known" else None,
    )
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(
        sys.modules,
        "app.macro",
        SimpleNamespace(
            fetch_indicator_history=lambda name: history,
            INDICATOR_MAP={"Known": ("fred_level", "X", "%")},
        ),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/indicator/Known")

    assert resp.status_code == 200
    assert saved["key"] == "indicator:known"
    assert resp.json()["data"][0]["value"] == 3.5


def test_trending_skips_non_dict_price_entries(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)

    class FakeTicker:
        def __init__(self, symbols):
            self.price = {"NVDA": "bad", "AAPL": {"shortName": "Apple", "regularMarketPrice": 100.0}}

    monkeypatch.setitem(
        sys.modules,
        "yahooquery",
        SimpleNamespace(get_trending=lambda: {"quotes": [{"symbol": "NVDA"}, {"symbol": "AAPL"}]}, Ticker=FakeTicker),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/trending")

    assert resp.status_code == 200
    assert [item["ticker"] for item in resp.json()] == ["AAPL"]


def test_market_summary_returns_cached_payload(monkeypatch) -> None:
    cached = {
        "categories": [],
        "cachedAt": datetime.now().isoformat(),  # naive timestamp path
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "market:summary" else None)

    with _client(monkeypatch) as client:
        resp = client.get("/api/market-summary")
    assert resp.status_code == 200
    assert resp.json()["cachedAt"] == cached["cachedAt"]


def test_market_summary_fetches_and_caches_when_not_cached(monkeypatch) -> None:
    saved = {}
    summary = MarketSummary(categories=[], cachedAt=_now_iso())
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(sys.modules, "app.macro", SimpleNamespace(fetch_market_summary=lambda: summary))

    with _client(monkeypatch) as client:
        resp = client.get("/api/market-summary")

    assert resp.status_code == 200
    assert saved["key"] == "market:summary"
    assert saved["value"]["cachedAt"] == summary.cachedAt


def test_market_summary_fetch_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setitem(sys.modules, "app.macro", SimpleNamespace(fetch_market_summary=lambda: (_ for _ in ()).throw(RuntimeError("bad macro"))))

    with _client(monkeypatch) as client:
        resp = client.get("/api/market-summary")

    assert resp.status_code == 502
    assert "Macro data fetch error" in resp.json()["detail"]


def test_market_analysis_returns_cached_payload_with_auth_override(monkeypatch) -> None:
    cached = {
        "regime": "risk-on",
        "regimeSentiment": "bullish",
        "summary": "summary",
        "narrative": "narrative",
        "keyDrivers": [],
        "historicalContext": "history",
        "watchlist": [],
        "generatedAt": _now_iso(),
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "market:analysis" else None)

    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "u1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/api/market-analysis")
        assert resp.status_code == 200
        assert resp.json()["regime"] == "risk-on"
    finally:
        main.app.dependency_overrides.clear()


def test_market_analysis_returns_cached_payload_with_naive_generated_at(monkeypatch) -> None:
    cached = {
        "regime": "risk-on",
        "regimeSentiment": "bullish",
        "summary": "summary",
        "narrative": "narrative",
        "keyDrivers": [],
        "historicalContext": "history",
        "watchlist": [],
        "generatedAt": datetime.now().isoformat(),
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "market:analysis" else None)

    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "u1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/api/market-analysis")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["generatedAt"] == cached["generatedAt"]


def test_market_analysis_generates_when_cached_payload_has_no_timestamp(monkeypatch) -> None:
    saved = {}
    analysis = MarketAnalysis(
        regime="regime",
        regimeSentiment="neutral",
        summary="sum",
        narrative="nar",
        keyDrivers=[],
        historicalContext="hist",
        watchlist=[],
        generatedAt=_now_iso(),
    )

    def fake_cache_get(key):
        if key == "market:analysis":
            return {"regime": "old", "summary": "old"}
        if key == "market:summary":
            return {"categories": [], "cachedAt": _now_iso()}
        return None

    monkeypatch.setattr(main.cache, "get", fake_cache_get)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(sys.modules, "app.analysis", SimpleNamespace(generate_market_analysis=lambda summary: analysis))
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "u1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/api/market-analysis")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert saved["key"] == "market:analysis"
    assert resp.json()["regime"] == "regime"


def test_market_analysis_refetches_when_naive_cached_payload_is_stale(monkeypatch) -> None:
    saved = {}
    analysis = MarketAnalysis(
        regime="regime",
        regimeSentiment="neutral",
        summary="sum",
        narrative="nar",
        keyDrivers=[],
        historicalContext="hist",
        watchlist=[],
        generatedAt=_now_iso(),
    )

    def fake_cache_get(key):
        if key == "market:analysis":
            return {
                "regime": "old",
                "regimeSentiment": "bearish",
                "summary": "old",
                "narrative": "old",
                "keyDrivers": [],
                "historicalContext": "old",
                "watchlist": [],
                "generatedAt": "2000-01-01T00:00:00",
            }
        if key == "market:summary":
            return {"categories": [], "cachedAt": _now_iso()}
        return None

    monkeypatch.setattr(main.cache, "get", fake_cache_get)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(sys.modules, "app.analysis", SimpleNamespace(generate_market_analysis=lambda summary: analysis))
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "u1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/api/market-analysis")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert saved["key"] == "market:analysis"
    assert resp.json()["summary"] == "sum"


def test_market_analysis_uses_cached_summary_and_generates(monkeypatch) -> None:
    saved = {}
    cached_summary = {"categories": [], "cachedAt": _now_iso()}
    analysis = MarketAnalysis(
        regime="regime",
        regimeSentiment="neutral",
        summary="sum",
        narrative="nar",
        keyDrivers=[],
        historicalContext="hist",
        watchlist=[],
        generatedAt=_now_iso(),
    )

    def fake_cache_get(key):
        if key == "market:analysis":
            return None
        if key == "market:summary":
            return cached_summary
        return None

    monkeypatch.setattr(main.cache, "get", fake_cache_get)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(sys.modules, "app.analysis", SimpleNamespace(generate_market_analysis=lambda summary: analysis))
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "u1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/api/market-analysis")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert saved["key"] == "market:analysis"
    assert resp.json()["regime"] == "regime"


def test_market_analysis_generation_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setitem(sys.modules, "app.macro", SimpleNamespace(fetch_market_summary=lambda: MarketSummary(categories=[], cachedAt=_now_iso())))
    monkeypatch.setitem(sys.modules, "app.analysis", SimpleNamespace(generate_market_analysis=lambda summary: (_ for _ in ()).throw(RuntimeError("llm bad"))))
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "u1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/api/market-analysis")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 502
    assert "Analysis generation error" in resp.json()["detail"]


def test_market_analysis_macro_fetch_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setitem(
        sys.modules,
        "app.macro",
        SimpleNamespace(fetch_market_summary=lambda: (_ for _ in ()).throw(RuntimeError("bad macro"))),
    )
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "u1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/api/market-analysis")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 502
    assert "Macro data fetch error" in resp.json()["detail"]


def test_get_earnings_uses_cache(monkeypatch) -> None:
    cached = {
        "cached_at": _now_iso(),
        "items": [{"date": "2026-05-01", "epsEstimate": 1.2, "reportedEps": None, "surprisePct": None}],
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "earnings:NVDA" else None)
    monkeypatch.setattr(main, "fetch_earnings_dates", lambda _ticker: (_ for _ in ()).throw(AssertionError("should not fetch")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/earnings/nvda")

    assert resp.status_code == 200
    assert resp.json()[0]["date"] == "2026-05-01"


def test_get_earnings_fetches_and_caches(monkeypatch) -> None:
    saved = {}
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setattr(main, "fetch_earnings_dates", lambda _ticker: [EarningsDate(date="2026-06-01", epsEstimate=2.0)])

    with _client(monkeypatch) as client:
        resp = client.get("/api/earnings/nvda")

    assert resp.status_code == 200
    assert saved["key"] == "earnings:NVDA"


def test_get_earnings_fetch_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main, "fetch_earnings_dates", lambda _ticker: (_ for _ in ()).throw(RuntimeError("bad earnings")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/earnings/nvda")

    assert resp.status_code == 502
    assert "Earnings fetch error" in resp.json()["detail"]


def test_get_news_fetch_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main, "fetch_news", lambda ticker, limit=250: (_ for _ in ()).throw(RuntimeError("boom")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/news/nvda")

    assert resp.status_code == 502
    assert "News fetch error" in resp.json()["detail"]


def test_get_news_fetches_and_caches(monkeypatch) -> None:
    saved = {}
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setattr(main, "fetch_news", lambda ticker, limit=250: [StockNews(id="n1", time="2026-01-01", title="Headline", publisher="Wire")])

    with _client(monkeypatch) as client:
        resp = client.get("/api/news/nvda")

    assert resp.status_code == 200
    assert saved["key"] == "news:NVDA"


def test_get_sec_filings_uses_cache(monkeypatch) -> None:
    cached = {
        "cached_at": _now_iso(),
        "items": [{"date": "2026-01-01", "form": "8-K", "items": ["2.02"], "label": "Earnings", "url": "https://sec"}],
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "sec:filings:NVDA" else None)
    monkeypatch.setattr(main, "fetch_sec_filings", lambda _ticker: (_ for _ in ()).throw(AssertionError("should not fetch")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/sec/nvda")

    assert resp.status_code == 200
    assert resp.json()[0]["form"] == "8-K"


def test_get_sec_filings_fetch_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main, "fetch_sec_filings", lambda _ticker: (_ for _ in ()).throw(RuntimeError("bad sec")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/sec/nvda")

    assert resp.status_code == 502
    assert "SEC EDGAR error" in resp.json()["detail"]


def test_trending_returns_cached_items(monkeypatch) -> None:
    cached = {
        "cached_at": _now_iso(),
        "items": [{"ticker": "NVDA", "companyName": "NVIDIA", "price": 900.0, "change": 1.0, "changePct": 0.1}],
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "trending" else None)

    with _client(monkeypatch) as client:
        resp = client.get("/api/trending")

    assert resp.status_code == 200
    assert resp.json()[0]["ticker"] == "NVDA"


def test_trending_fetches_live_items_and_caches(monkeypatch) -> None:
    saved = {}
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))

    class FakeTicker:
        def __init__(self, symbols):
            self.price = {
                "NVDA": {
                    "longName": "NVIDIA",
                    "regularMarketPrice": 900.0,
                    "regularMarketChange": 10.0,
                    "regularMarketChangePercent": 1.12,
                }
            }

    monkeypatch.setitem(
        sys.modules,
        "yahooquery",
        SimpleNamespace(get_trending=lambda: {"quotes": [{"symbol": "^GSPC"}, {"symbol": "NVDA"}]}, Ticker=FakeTicker),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/trending")

    assert resp.status_code == 200
    assert resp.json()[0]["ticker"] == "NVDA"
    assert saved["key"] == "trending"


def test_trending_returns_empty_when_live_has_no_symbols(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setitem(
        sys.modules,
        "yahooquery",
        SimpleNamespace(get_trending=lambda: {"quotes": [{"symbol": "^GSPC"}]}, Ticker=lambda symbols: None),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/trending")

    assert resp.status_code == 200
    assert resp.json() == []


def test_indicator_history_unknown_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    fake_macro = SimpleNamespace(fetch_indicator_history=lambda name: None, INDICATOR_MAP={"Known": ("fred_level", "X", "%")})
    monkeypatch.setitem(sys.modules, "app.macro", fake_macro)

    with _client(monkeypatch) as client:
        resp = client.get("/api/indicator/Nope")

    assert resp.status_code == 404
    assert "Unknown indicator" in resp.json()["detail"]


def test_indicator_history_fetches_and_caches_success(monkeypatch) -> None:
    saved = {}
    history = IndicatorHistory(
        name="Known",
        unit="%",
        data=[IndicatorDataPoint(time="2026-01-01", value=1.2)],
        cachedAt=_now_iso(),
    )
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setitem(
        sys.modules,
        "app.macro",
        SimpleNamespace(fetch_indicator_history=lambda name: history, INDICATOR_MAP={"Known": ("fred_level", "X", "%")}),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/indicator/Known")

    assert resp.status_code == 200
    assert saved["key"] == "indicator:known"
    assert resp.json()["data"][0]["value"] == 1.2


def test_indicator_history_fetch_error_returns_502(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setitem(
        sys.modules,
        "app.macro",
        SimpleNamespace(
            fetch_indicator_history=lambda name: (_ for _ in ()).throw(RuntimeError("bad indicator")),
            INDICATOR_MAP={"Known": ("fred_level", "X", "%")},
        ),
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/indicator/Known")

    assert resp.status_code == 502
    assert "Indicator fetch error" in resp.json()["detail"]


def test_signup_and_login_flow(monkeypatch) -> None:
    monkeypatch.setattr(main, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setattr(main, "verify_password", lambda password, hashed: hashed == f"hashed::{password}")
    monkeypatch.setattr(main, "create_token", lambda user_id, email: f"token::{user_id}::{email}")

    with _sqlite_client(monkeypatch) as client:
        signup_resp = client.post("/auth/signup", json={"email": "u1@example.com", "password": "secret"})
        login_resp = client.post("/auth/login", json={"email": "u1@example.com", "password": "secret"})

    assert signup_resp.status_code == 200
    assert signup_resp.json()["access_token"].startswith("token::")
    assert login_resp.status_code == 200
    assert login_resp.json()["access_token"].startswith("token::")


def test_me_endpoint_returns_current_user(monkeypatch) -> None:
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "user-1", "email": "u1@example.com"}
    try:
        with _client(monkeypatch) as client:
            resp = client.get("/auth/me")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"id": "user-1", "email": "u1@example.com"}


def test_login_rejects_invalid_password(monkeypatch) -> None:
    monkeypatch.setattr(main, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setattr(main, "verify_password", lambda password, hashed: False)

    with _sqlite_client(monkeypatch) as client:
        client.post("/auth/signup", json={"email": "u1@example.com", "password": "secret"})
        resp = client.post("/auth/login", json={"email": "u1@example.com", "password": "wrong"})

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_signup_rejects_duplicate_email(monkeypatch) -> None:
    monkeypatch.setattr(main, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setattr(main, "create_token", lambda user_id, email: "token")

    with _sqlite_client(monkeypatch) as client:
        first = client.post("/auth/signup", json={"email": "u1@example.com", "password": "secret"})
        second = client.post("/auth/signup", json={"email": "u1@example.com", "password": "secret"})

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["detail"] == "Email already registered"


def test_forgot_password_existing_user_stores_token_and_sends_email(monkeypatch) -> None:
    sent = {}
    monkeypatch.setattr(main, "_send_reset_email", lambda email, link: sent.update({"email": email, "link": link}))
    monkeypatch.setattr(main, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setenv("FRONTEND_URL", "http://frontend.test")

    with _sqlite_client(monkeypatch) as client:
        signup_resp = client.post("/auth/signup", json={"email": "u1@example.com", "password": "secret"})
        forgot_resp = client.post("/auth/forgot-password", json={"email": "u1@example.com"})

    assert signup_resp.status_code == 200
    assert forgot_resp.status_code == 200
    assert forgot_resp.json()["message"].startswith("If that email is registered")
    assert sent["email"] == "u1@example.com"
    assert "http://frontend.test/reset-password?token=" in sent["link"]


def test_forgot_password_unregistered_email_still_returns_generic_message(monkeypatch) -> None:
    sent = {"called": False}
    monkeypatch.setattr(main, "_send_reset_email", lambda email, link: sent.update({"called": True}))

    with _sqlite_client(monkeypatch) as client:
        resp = client.post("/auth/forgot-password", json={"email": "missing@example.com"})

    assert resp.status_code == 200
    assert resp.json()["message"].startswith("If that email is registered")
    assert sent["called"] is False


def test_reset_password_updates_password_and_deletes_token(monkeypatch) -> None:
    monkeypatch.setattr(main, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setattr(main, "create_token", lambda user_id, email: "token")

    with _sqlite_client(monkeypatch) as client:
        conn = main.get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO users (id, email, hashed_password, created_at) VALUES (?, ?, ?, ?)",
                ("manual-user", "manual@example.com", "old", _now_iso()),
            )
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                ("reset-token", "manual-user", "2099-01-01T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()

        resp = client.post("/auth/reset-password", json={"token": "reset-token", "new_password": "new-secret"})

        conn = main.get_conn()
        try:
            user_row = conn.execute("SELECT hashed_password FROM users WHERE id = ?", ("manual-user",)).fetchone()
            token_row = conn.execute("SELECT token FROM password_reset_tokens WHERE token = ?", ("reset-token",)).fetchone()
        finally:
            conn.close()

    assert resp.status_code == 200
    assert user_row["hashed_password"] == "hashed::new-secret"
    assert token_row is None


def test_reset_password_rejects_missing_or_expired_token(monkeypatch) -> None:
    monkeypatch.setattr(main, "hash_password", lambda password: f"hashed::{password}")

    with _sqlite_client(monkeypatch) as client:
        missing = client.post("/auth/reset-password", json={"token": "missing", "new_password": "x"})
        conn = main.get_conn()
        try:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                ("expired-token", "user-1", "2000-01-01T00:00:00+00:00"),
            )
            conn.commit()
        finally:
            conn.close()
        expired = client.post("/auth/reset-password", json={"token": "expired-token", "new_password": "x"})

    assert missing.status_code == 400
    assert expired.status_code == 400


def test_watchlist_add_get_remove_flow(monkeypatch) -> None:
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "user-1", "email": "u1@example.com"}
    try:
        with _sqlite_client(monkeypatch) as client:
            add_resp = client.post("/api/watchlist/nvda")
            list_resp = client.get("/api/watchlist")
            remove_resp = client.delete("/api/watchlist/nvda")
            list_after_remove = client.get("/api/watchlist")
    finally:
        main.app.dependency_overrides.clear()

    assert add_resp.status_code == 204
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["ticker"] == "NVDA"
    assert remove_resp.status_code == 204
    assert list_after_remove.json() == []


def test_watchlist_duplicate_insert_keeps_single_row(monkeypatch) -> None:
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "user-1", "email": "u1@example.com"}
    try:
        with _sqlite_client(monkeypatch) as client:
            first = client.post("/api/watchlist/nvda")
            second = client.post("/api/watchlist/NVDA")
            listed = client.get("/api/watchlist")
    finally:
        main.app.dependency_overrides.clear()

    assert first.status_code == 204
    assert second.status_code == 204
    assert len(listed.json()) == 1


def test_watchlist_empty_list_for_new_user(monkeypatch) -> None:
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "new-user", "email": "new@example.com"}
    try:
        with _sqlite_client(monkeypatch) as client:
            resp = client.get("/api/watchlist")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == []


def test_send_reset_email_logs_in_dev_mode(monkeypatch) -> None:
    printed = []
    monkeypatch.setattr(main, "EMAIL_BACKEND", "log")
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    main._send_reset_email("u1@example.com", "http://frontend/reset")

    assert any("u1@example.com" in line and "http://frontend/reset" in line for line in printed)


def test_send_reset_email_uses_ses(monkeypatch) -> None:
    sent = {}

    class FakeSES:
        def send_email(self, **kwargs):
            sent.update(kwargs)

    monkeypatch.setattr(main, "EMAIL_BACKEND", "ses")
    monkeypatch.setattr(main, "SES_FROM_EMAIL", "noreply@example.com")
    monkeypatch.setenv("AWS_REGION", "ca-central-1")
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda service, region_name=None: FakeSES()))

    main._send_reset_email("u1@example.com", "http://frontend/reset")

    assert sent["Source"] == "noreply@example.com"
    assert sent["Destination"]["ToAddresses"] == ["u1@example.com"]


def test_news_returns_cached_payload(monkeypatch) -> None:
    cached = {
        "cached_at": _now_iso(),
        "items": [{"id": "n1", "time": "2026-01-01", "title": "Headline", "publisher": "Wire"}],
    }
    monkeypatch.setattr(main.cache, "get", lambda key: cached if key == "news:NVDA" else None)
    monkeypatch.setattr(main, "fetch_news", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not fetch")))

    with _client(monkeypatch) as client:
        resp = client.get("/api/news/nvda")

    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "n1"


def test_sec_filings_fetch_and_cache(monkeypatch) -> None:
    saved = {}
    monkeypatch.setattr(main.cache, "get", lambda _key: None)
    monkeypatch.setattr(main.cache, "set", lambda key, value: saved.update({"key": key, "value": value}))
    monkeypatch.setattr(
        main,
        "fetch_sec_filings",
        lambda _ticker: [SECFiling(date="2026-01-01", form="8-K", items=["2.02"], label="Earnings", url="https://sec")],
    )

    with _client(monkeypatch) as client:
        resp = client.get("/api/sec/nvda")

    assert resp.status_code == 200
    assert saved["key"] == "sec:filings:NVDA"


def test_trending_returns_empty_on_provider_failure(monkeypatch) -> None:
    monkeypatch.setattr(main.cache, "get", lambda _key: None)

    class BrokenTrending:
        def __call__(self):
            raise RuntimeError("provider down")

    monkeypatch.setitem(sys.modules, "yahooquery", SimpleNamespace(get_trending=BrokenTrending()))

    with _client(monkeypatch) as client:
        resp = client.get("/api/trending")

    assert resp.status_code == 200
    assert resp.json() == []


def test_remove_from_watchlist_is_idempotent(monkeypatch) -> None:
    main.app.dependency_overrides[main.get_current_user] = lambda: {"sub": "user-1", "email": "u1@example.com"}
    try:
        with _sqlite_client(monkeypatch) as client:
            resp = client.delete("/api/watchlist/nvda")
            listed = client.get("/api/watchlist")
    finally:
        main.app.dependency_overrides.clear()

    assert resp.status_code == 204
    assert listed.json() == []
