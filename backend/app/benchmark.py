"""
API endpoint benchmark suite — pytest-benchmark.

Usage:
  pytest app/benchmark.py -v
  pytest app/benchmark.py -v --benchmark-sort=mean
  pytest app/benchmark.py -v --benchmark-compare
"""
import os

import pytest
from fastapi.testclient import TestClient
from app.main import app

TICKER = os.environ.get("TICKER", "AAPL").upper()
INDICATOR_NAME = os.environ.get("INDICATOR", "VIX").strip()
AUTH_EMAIL = os.environ.get("AUTH_EMAIL", "").strip()
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "").strip()

@pytest.fixture(scope="session")
def client():
    # Context manager is required so FastAPI startup runs (init_db(), etc.).
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client) -> dict[str, str]:
    if not (AUTH_EMAIL and AUTH_PASSWORD):
        raise RuntimeError("Missing auth: set AUTH_TOKEN or AUTH_EMAIL/AUTH_PASSWORD.")
    resp = client.post("/auth/login", json={"email": AUTH_EMAIL, "password": AUTH_PASSWORD})
    token = (resp.json() or {}).get("access_token") if resp.status_code == 200 else ""
    if not token:
        raise RuntimeError("Auth failed: could not obtain access token.")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def warmup(client):
    # Cold pass — populates cache, not measured
    client.get("/health")
    client.get("/api/trending")
    client.get(f"/api/prices?tickers={TICKER}")
    client.get(f"/api/stock/{TICKER}")
    client.get(f"/api/news/{TICKER}")
    client.get(f"/api/earnings/{TICKER}")
    client.get(f"/api/sec/{TICKER}")
    client.get("/api/market-summary")
    client.get(f"/api/indicator/{INDICATOR_NAME}")
    client.get(f"/api/search?q={TICKER}")


def test_health(benchmark, client):
    benchmark(client.get, "/health")


def test_trending(benchmark, client):
    benchmark(client.get, "/api/trending")


def test_prices(benchmark, client):
    benchmark(client.get, f"/api/prices?tickers={TICKER}")


def test_stock(benchmark, client):
    benchmark(client.get, f"/api/stock/{TICKER}")


def test_news(benchmark, client):
    benchmark(client.get, f"/api/news/{TICKER}")


def test_earnings(benchmark, client):
    benchmark(client.get, f"/api/earnings/{TICKER}")


def test_sec(benchmark, client):
    benchmark(client.get, f"/api/sec/{TICKER}")


def test_search(benchmark, client):
    benchmark(client.get, f"/api/search?q={TICKER}")


def test_market_summary(benchmark, client):
    benchmark(client.get, "/api/market-summary")


def test_indicator(benchmark, client):
    benchmark(client.get, f"/api/indicator/{INDICATOR_NAME}")


def test_market_analysis(benchmark, client, auth_headers):
    benchmark(client.get, "/api/market-analysis", headers=auth_headers)


def test_auth_me(benchmark, client, auth_headers):
    benchmark(client.get, "/auth/me", headers=auth_headers)


def test_watchlist_get(benchmark, client, auth_headers):
    benchmark(client.get, "/api/watchlist", headers=auth_headers)


def test_watchlist_add(benchmark, client, auth_headers):
    benchmark(client.post, f"/api/watchlist/{TICKER}", headers=auth_headers)


def test_watchlist_remove(benchmark, client, auth_headers):
    benchmark(client.delete, f"/api/watchlist/{TICKER}", headers=auth_headers)
