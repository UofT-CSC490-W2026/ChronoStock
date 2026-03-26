import builtins
from pathlib import Path
import textwrap

from app.models import EarningsDate, OHLCBar, SECFiling, StockMeta, StockNews
from app.pipelines import run_daily_update


def test_tickers_from_env_normalizes_and_filters(monkeypatch) -> None:
    monkeypatch.setenv("DAILY_UPDATE_TICKERS", " nvda, , aapl ,msft ")
    assert run_daily_update._tickers_from_env() == ["NVDA", "AAPL", "MSFT"]


def test_build_update_tickers_keeps_env_order_and_deduplicates(monkeypatch) -> None:
    monkeypatch.setattr(run_daily_update, "_tickers_from_env", lambda: ["NVDA", "AAPL"])
    monkeypatch.setattr(run_daily_update, "refresh_trending", lambda: ["AAPL", "TSLA", "NVDA"])

    assert run_daily_update.build_update_tickers() == ["NVDA", "AAPL", "TSLA"]


def test_refresh_stock_bundle_writes_cached_payload(monkeypatch) -> None:
    written = {}
    monkeypatch.setattr(
        run_daily_update,
        "fetch_bars",
        lambda ticker: [OHLCBar(time="2026-01-01", open=1, high=2, low=0.5, close=1.5, volume=100)],
    )
    monkeypatch.setattr(
        run_daily_update,
        "fetch_info",
        lambda ticker: ("NVIDIA", StockMeta(marketCap=1.0), "equity"),
    )
    monkeypatch.setattr(run_daily_update.cache, "set", lambda key, value: written.update({"key": key, "value": value}))

    run_daily_update.refresh_stock_bundle("NVDA")

    assert written["key"] == "stock:NVDA"
    assert written["value"]["ticker"] == "NVDA"
    assert written["value"]["companyName"] == "NVIDIA"
    assert written["value"]["assetType"] == "equity"
    assert written["value"]["bars"][0]["close"] == 1.5
    assert written["value"]["cached_at"]


def test_refresh_earnings_and_news_and_sec_filings_write_items(monkeypatch) -> None:
    writes = {}
    monkeypatch.setattr(
        run_daily_update,
        "fetch_earnings_dates",
        lambda ticker: [EarningsDate(date="2026-05-01", epsEstimate=1.2)],
    )
    monkeypatch.setattr(
        run_daily_update,
        "fetch_news",
        lambda ticker: [StockNews(id="n1", time="2026-01-01", title="Headline", publisher="Wire")],
    )
    monkeypatch.setattr(
        run_daily_update,
        "fetch_sec_filings",
        lambda ticker: [SECFiling(date="2026-01-01", form="8-K", items=["2.02"], label="Earnings", url="https://sec")],
    )
    monkeypatch.setattr(run_daily_update.cache, "set", lambda key, value: writes.__setitem__(key, value))

    run_daily_update.refresh_earnings("NVDA")
    run_daily_update.refresh_news("NVDA")
    run_daily_update.refresh_sec_filings("NVDA")

    assert writes["earnings:NVDA"]["items"][0]["date"] == "2026-05-01"
    assert writes["news:NVDA"]["items"][0]["id"] == "n1"
    assert writes["sec:filings:NVDA"]["items"][0]["form"] == "8-K"


def test_refresh_prices_returns_early_for_empty_input(monkeypatch) -> None:
    called = {"count": 0}

    class FailTicker:
        def __init__(self, _tickers):
            called["count"] += 1

    monkeypatch.setattr(run_daily_update, "YQTicker", FailTicker)

    run_daily_update.refresh_prices([])

    assert called["count"] == 0


def test_refresh_prices_caches_only_dict_entries(monkeypatch) -> None:
    writes = {}

    class FakeTicker:
        def __init__(self, tickers):
            self.price = {
                "NVDA": {
                    "longName": "NVIDIA",
                    "regularMarketPrice": 900.0,
                    "regularMarketChange": 10.0,
                    "regularMarketChangePercent": 1.12,
                },
                "AAPL": "skip",
            }

    monkeypatch.setattr(run_daily_update, "YQTicker", FakeTicker)
    monkeypatch.setattr(run_daily_update.cache, "set", lambda key, value: writes.__setitem__(key, value))

    run_daily_update.refresh_prices(["NVDA", "AAPL"])

    assert list(writes) == ["price:NVDA"]
    assert writes["price:NVDA"]["companyName"] == "NVIDIA"


def test_refresh_trending_filters_indices_and_caches_items(monkeypatch) -> None:
    writes = {}
    monkeypatch.setattr(
        run_daily_update,
        "get_trending",
        lambda: {"quotes": [{"symbol": "^GSPC"}, {"symbol": "NVDA"}, {"symbol": "AAPL"}]},
    )

    class FakeTicker:
        def __init__(self, tickers):
            self.price = {
                "NVDA": {
                    "longName": "NVIDIA",
                    "regularMarketPrice": 900.0,
                    "regularMarketChange": 10.0,
                    "regularMarketChangePercent": 1.12,
                },
                "AAPL": {
                    "shortName": "Apple",
                    "regularMarketPrice": 180.0,
                    "regularMarketChange": 1.0,
                    "regularMarketChangePercent": 0.5,
                },
            }

    monkeypatch.setattr(run_daily_update, "YQTicker", FakeTicker)
    monkeypatch.setattr(run_daily_update.cache, "set", lambda key, value: writes.update({key: value}))

    tickers = run_daily_update.refresh_trending()

    assert tickers == ["NVDA", "AAPL"]
    assert [item["ticker"] for item in writes["trending"]["items"]] == ["NVDA", "AAPL"]


def test_refresh_trending_skips_non_dict_price_entries(monkeypatch) -> None:
    writes = {}
    monkeypatch.setattr(
        run_daily_update,
        "get_trending",
        lambda: {"quotes": [{"symbol": "NVDA"}, {"symbol": "AAPL"}]},
    )

    class FakeTicker:
        def __init__(self, tickers):
            self.price = {
                "NVDA": {
                    "longName": "NVIDIA",
                    "regularMarketPrice": 900.0,
                    "regularMarketChange": 10.0,
                    "regularMarketChangePercent": 1.12,
                },
                "AAPL": "skip",
            }

    monkeypatch.setattr(run_daily_update, "YQTicker", FakeTicker)
    monkeypatch.setattr(run_daily_update.cache, "set", lambda key, value: writes.update({key: value}))

    tickers = run_daily_update.refresh_trending()

    assert tickers == ["NVDA", "AAPL"]
    assert writes["trending"]["items"] == [
        {
            "ticker": "NVDA",
            "companyName": "NVIDIA",
            "price": 900.0,
            "change": 10.0,
            "changePct": 1.12,
        }
    ]


def test_refresh_trending_caches_empty_result_when_no_quotes(monkeypatch) -> None:
    writes = {}
    monkeypatch.setattr(run_daily_update, "get_trending", lambda: {"quotes": [{"symbol": "^GSPC"}]})
    monkeypatch.setattr(run_daily_update.cache, "set", lambda key, value: writes.update({key: value}))

    assert run_daily_update.refresh_trending() == []
    assert writes["trending"]["items"] == []


def test_main_refreshes_all_resources_for_each_ticker(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(run_daily_update, "build_update_tickers", lambda: ["NVDA", "AAPL"])
    monkeypatch.setattr(run_daily_update, "refresh_prices", lambda tickers: calls.append(("prices", tickers)))
    monkeypatch.setattr(run_daily_update, "refresh_stock_bundle", lambda ticker: calls.append(("stock", ticker)))
    monkeypatch.setattr(run_daily_update, "refresh_earnings", lambda ticker: calls.append(("earnings", ticker)))
    monkeypatch.setattr(run_daily_update, "refresh_news", lambda ticker: calls.append(("news", ticker)))
    monkeypatch.setattr(run_daily_update, "refresh_sec_filings", lambda ticker: calls.append(("sec", ticker)))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    run_daily_update.main()

    assert calls == [
        ("prices", ["NVDA", "AAPL"]),
        ("stock", "NVDA"),
        ("earnings", "NVDA"),
        ("news", "NVDA"),
        ("sec", "NVDA"),
        ("stock", "AAPL"),
        ("earnings", "AAPL"),
        ("news", "AAPL"),
        ("sec", "AAPL"),
    ]


def test_real_main_block_invokes_main(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(run_daily_update, "main", lambda: calls.append("main"))

    source_lines = Path(run_daily_update.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 141 + textwrap.dedent("\n".join(source_lines[141:])) + "\n"
    code = compile(main_block, run_daily_update.__file__, "exec")
    globals_dict = dict(run_daily_update.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == ["main"]
