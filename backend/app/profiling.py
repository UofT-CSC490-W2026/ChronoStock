import argparse
import cProfile
import os
import pstats
import re

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_PATH = os.path.join(APP_DIR, "report.txt")
NUM_REPORT = 20


def _get_auth_header(client) -> dict[str, str]:
    email = os.environ.get("AUTH_EMAIL", "").strip()
    password = os.environ.get("AUTH_PASSWORD", "").strip()
    if not (email and password):
        return {}

    resp = client.post("/auth/login", json={"email": email, "password": password})
    token = (resp.json() or {}).get("access_token") if resp.status_code == 200 else ""
    return {"Authorization": f"Bearer {token}"} if token else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile ChronoStock backend via test requests")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol to profile")
    parser.add_argument("--indicator", default="VIX", help="Macro indicator name for /api/indicator/{name}",
    )
    args = parser.parse_args()

    ticker = args.ticker.upper()
    indicator_name = args.indicator

    from fastapi.testclient import TestClient
    from app.main import app

    # Use TestClient as a context manager so FastAPI startup runs (init_db(), etc.).
    with TestClient(app, raise_server_exceptions=True) as client:
        auth_header = _get_auth_header(client)
        if not auth_header:
            raise SystemExit(
                "Error: Authentication failed."
            )

        profiler = cProfile.Profile()

        print(f"Profiling ticker={ticker}, indicator={indicator_name} ...")
        profiler.enable()
        client.get("/health")
        client.get("/api/trending")
        client.get("/api/market-summary")
        client.get(f"/api/prices?tickers={ticker}")
        client.get(f"/api/stock/{ticker}")
        client.get(f"/api/news/{ticker}")
        client.get(f"/api/earnings/{ticker}")
        client.get(f"/api/sec/{ticker}")
        client.get(f"/api/indicator/{indicator_name}")
        client.get("/api/market-analysis", headers=auth_header)
        client.get("/auth/me", headers=auth_header)
        client.get("/api/watchlist", headers=auth_header)
        client.post(f"/api/watchlist/{ticker}", headers=auth_header)
        client.delete(f"/api/watchlist/{ticker}", headers=auth_header)
        client.get(f"/api/search?q={ticker}")
        profiler.disable()

    with open(REPORT_PATH, "w", encoding="utf-8") as report:
        stats = pstats.Stats(profiler, stream=report).sort_stats("cumulative")
        stats.print_stats(re.escape(APP_DIR), NUM_REPORT)

    print(f"Report saved to {REPORT_PATH}")


if __name__ == "__main__":
    main()
