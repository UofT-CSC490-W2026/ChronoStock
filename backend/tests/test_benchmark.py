from types import SimpleNamespace

import pytest

from app import benchmark


def test_client_fixture_uses_testclient_context(monkeypatch) -> None:
    calls = {}

    class FakeContext:
        def __enter__(self):
            calls["entered"] = True
            return "client"

        def __exit__(self, exc_type, exc, tb):
            calls["exited"] = True

    monkeypatch.setattr(
        benchmark,
        "TestClient",
        lambda app, raise_server_exceptions=True: calls.update(
            {"app": app, "raise_server_exceptions": raise_server_exceptions}
        )
        or FakeContext(),
    )

    gen = benchmark.client.__wrapped__()
    assert next(gen) == "client"
    assert calls["app"] is benchmark.app
    assert calls["raise_server_exceptions"] is True
    with pytest.raises(StopIteration):
        next(gen)
    assert calls["entered"] is True
    assert calls["exited"] is True


def test_auth_headers_requires_credentials(monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "AUTH_EMAIL", "")
    monkeypatch.setattr(benchmark, "AUTH_PASSWORD", "")

    with pytest.raises(RuntimeError, match="Missing auth"):
        benchmark.auth_headers.__wrapped__(SimpleNamespace())


def test_auth_headers_requires_access_token(monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "AUTH_EMAIL", "user@example.com")
    monkeypatch.setattr(benchmark, "AUTH_PASSWORD", "secret")
    client = SimpleNamespace(post=lambda *args, **kwargs: SimpleNamespace(status_code=401, json=lambda: {}))

    with pytest.raises(RuntimeError, match="Auth failed"):
        benchmark.auth_headers.__wrapped__(client)


def test_auth_headers_returns_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "AUTH_EMAIL", "user@example.com")
    monkeypatch.setattr(benchmark, "AUTH_PASSWORD", "secret")
    seen = {}

    def fake_post(path, json):
        seen["path"] = path
        seen["json"] = json
        return SimpleNamespace(status_code=200, json=lambda: {"access_token": "abc"})

    headers = benchmark.auth_headers.__wrapped__(SimpleNamespace(post=fake_post))

    assert seen == {
        "path": "/auth/login",
        "json": {"email": "user@example.com", "password": "secret"},
    }
    assert headers == {"Authorization": "Bearer abc"}


def test_warmup_hits_all_expected_routes(monkeypatch) -> None:
    monkeypatch.setattr(benchmark, "TICKER", "NVDA")
    monkeypatch.setattr(benchmark, "INDICATOR_NAME", "CPI")
    calls = []
    client = SimpleNamespace(get=lambda path: calls.append(path))

    benchmark.warmup.__wrapped__(client)

    assert calls == [
        "/health",
        "/api/trending",
        "/api/prices?tickers=NVDA",
        "/api/stock/NVDA",
        "/api/news/NVDA",
        "/api/earnings/NVDA",
        "/api/sec/NVDA",
        "/api/market-summary",
        "/api/indicator/CPI",
        "/api/search?q=NVDA",
    ]


def test_benchmark_endpoint_wrappers_use_expected_clients() -> None:
    calls = []

    def fake_benchmark(func, path, **kwargs):
        calls.append((func.__name__, path, kwargs))

    client = SimpleNamespace(
        get=lambda *args, **kwargs: None,
        post=lambda *args, **kwargs: None,
        delete=lambda *args, **kwargs: None,
    )
    headers = {"Authorization": "Bearer token"}

    benchmark.test_health(fake_benchmark, client)
    benchmark.test_trending(fake_benchmark, client)
    benchmark.test_prices(fake_benchmark, client)
    benchmark.test_stock(fake_benchmark, client)
    benchmark.test_news(fake_benchmark, client)
    benchmark.test_earnings(fake_benchmark, client)
    benchmark.test_sec(fake_benchmark, client)
    benchmark.test_search(fake_benchmark, client)
    benchmark.test_market_summary(fake_benchmark, client)
    benchmark.test_indicator(fake_benchmark, client)
    benchmark.test_market_analysis(fake_benchmark, client, headers)
    benchmark.test_auth_me(fake_benchmark, client, headers)
    benchmark.test_watchlist_get(fake_benchmark, client, headers)
    benchmark.test_watchlist_add(fake_benchmark, client, headers)
    benchmark.test_watchlist_remove(fake_benchmark, client, headers)

    assert calls == [
        ("<lambda>", "/health", {}),
        ("<lambda>", "/api/trending", {}),
        ("<lambda>", f"/api/prices?tickers={benchmark.TICKER}", {}),
        ("<lambda>", f"/api/stock/{benchmark.TICKER}", {}),
        ("<lambda>", f"/api/news/{benchmark.TICKER}", {}),
        ("<lambda>", f"/api/earnings/{benchmark.TICKER}", {}),
        ("<lambda>", f"/api/sec/{benchmark.TICKER}", {}),
        ("<lambda>", f"/api/search?q={benchmark.TICKER}", {}),
        ("<lambda>", "/api/market-summary", {}),
        ("<lambda>", f"/api/indicator/{benchmark.INDICATOR_NAME}", {}),
        ("<lambda>", "/api/market-analysis", {"headers": headers}),
        ("<lambda>", "/auth/me", {"headers": headers}),
        ("<lambda>", "/api/watchlist", {"headers": headers}),
        ("<lambda>", f"/api/watchlist/{benchmark.TICKER}", {"headers": headers}),
        ("<lambda>", f"/api/watchlist/{benchmark.TICKER}", {"headers": headers}),
    ]
