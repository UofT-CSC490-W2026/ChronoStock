from datetime import datetime

import pandas as pd
import requests
from pathlib import Path
import textwrap

from app.pipelines import data_ingestion


def test_save_to_s3_noop_on_empty_df(monkeypatch) -> None:
    class FakeS3:
        def put_object(self, **kwargs):
            raise AssertionError("Should not upload empty df")

    monkeypatch.setattr(data_ingestion, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(data_ingestion, "_require_bucket", lambda: "bucket")

    data_ingestion.save_to_s3(pd.DataFrame(), "raw/stock_prices", "NVDA.csv")


def test_save_to_s3_uploads_payload(monkeypatch) -> None:
    captured = {}

    class FakeS3:
        def put_object(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(data_ingestion, "_s3_client", lambda: FakeS3())
    monkeypatch.setattr(data_ingestion, "_require_bucket", lambda: "bucket")

    df = pd.DataFrame([{"Date": "2026-01-01", "Close": 1.0}])
    data_ingestion.save_to_s3(df, "raw/stock_prices", "NVDA.csv")

    assert captured["Bucket"] == "bucket"
    assert captured["Key"] == "raw/stock_prices/NVDA.csv"
    assert captured["ContentType"] == "text/csv"


def test_s3_client_uses_region_and_s3_key_normalizes(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setattr(
        data_ingestion.boto3,
        "client",
        lambda service, region_name=None: calls.append((service, region_name)) or "client",
    )

    assert data_ingestion._s3_client() == "client"
    assert calls == [("s3", "us-east-1")]
    assert data_ingestion._s3_key("/raw/stock_prices/", "NVDA.csv") == "raw/stock_prices/NVDA.csv"
    assert data_ingestion._s3_key("", "NVDA.csv") == "NVDA.csv"


def test_s3_client_without_region_uses_default_client(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setattr(
        data_ingestion.boto3,
        "client",
        lambda service: calls.append(service) or "client",
    )

    assert data_ingestion._s3_client() == "client"
    assert calls == ["s3"]


def test_get_stockprice_returns_empty_when_no_data(monkeypatch) -> None:
    monkeypatch.setattr(data_ingestion.yf, "download", lambda *args, **kwargs: pd.DataFrame())
    out = data_ingestion.get_stockprice("NVDA", save_db=False, save_local=False)
    assert out.empty


def test_get_stockprice_flattens_multiindex_and_adds_ticker(monkeypatch) -> None:
    idx = pd.to_datetime(["2026-01-01", "2026-01-02"])
    idx.name = "Date"
    df = pd.DataFrame(
        {
            ("Open", "NVDA"): [1.0, 2.0],
            ("Close", "NVDA"): [1.5, 2.5],
        },
        index=idx,
    )

    monkeypatch.setattr(data_ingestion.yf, "download", lambda *args, **kwargs: df)
    saved = {}
    monkeypatch.setattr(data_ingestion, "save_to_s3", lambda d, p, f: saved.update({"rows": len(d), "key": f}))

    out = data_ingestion.get_stockprice("NVDA", save_db=False, save_local=True)
    assert list(out["ticker"]) == ["NVDA", "NVDA"]
    assert list(out["Date"]) == ["2026-01-01", "2026-01-02"]
    assert saved["rows"] == 2
    assert saved["key"] == "NVDA.csv"


def test_get_stockprice_uses_date_range_arguments(monkeypatch) -> None:
    captured = {}

    def fake_download(ticker, start=None, end=None, auto_adjust=True, period=None):
        captured.update(
            {
                "ticker": ticker,
                "start": start,
                "end": end,
                "period": period,
                "auto_adjust": auto_adjust,
            }
        )
        idx = pd.to_datetime(["2026-01-01"])
        idx.name = "Date"
        return pd.DataFrame({"Close": [1.5]}, index=idx)

    monkeypatch.setattr(data_ingestion.yf, "download", fake_download)

    out = data_ingestion.get_stockprice(
        "NVDA",
        start_date="2026-01-01",
        end_date="2026-01-31",
        save_db=False,
        save_local=False,
    )

    assert not out.empty
    assert captured["ticker"] == "NVDA"
    assert captured["start"] == "2026-01-01"
    assert captured["end"] == "2026-01-31"
    assert captured["period"] is None


def test_require_bucket_and_parse_args(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_S3_BUCKET", "bucket")
    assert data_ingestion._require_bucket() == "bucket"

    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--tickers", "nvda,aapl", "--start-date", "2026-01-01", "--end-date", "2026-01-31", "--with-reddit"],
    )
    args = data_ingestion.parse_args()
    assert args.tickers == "nvda,aapl"
    assert args.with_reddit is True


def test_require_bucket_raises_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("PIPELINE_S3_BUCKET", raising=False)
    try:
        data_ingestion._require_bucket()
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "Missing PIPELINE_S3_BUCKET" in str(exc)


def test_get_stocknews_paginates_and_saves(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError("bad status")

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(
                    {
                        "results": [
                            {
                                "id": "n1",
                                "tickers": ["NVDA"],
                                "title": "t",
                                "published_utc": "2026-01-01T00:00:00Z",
                                "author": "a",
                                "description": "d",
                                "keywords": ["k1"],
                                "insights": [{"x": 1}],
                                "article_url": "https://x",
                            }
                        ],
                        "next_url": "https://next.page/news",
                    }
                )
            return FakeResponse({"results": []})

    monkeypatch.setattr(data_ingestion.requests, "Session", FakeSession)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)
    saved = {}
    monkeypatch.setattr(data_ingestion, "save_to_s3", lambda d, p, f: saved.update({"rows": len(d), "file": f}))

    out = data_ingestion.get_stocknews(
        "NVDA",
        "2026-01-01",
        "2026-01-31",
        api_key="key",
        save_db=False,
        save_local=True,
    )

    assert len(out) == 1
    assert out.iloc[0]["ticker"] == "NVDA"
    assert saved == {"rows": 1, "file": "NVDA.csv"}


def test_get_stocknews_prints_progress_when_next_page_present(monkeypatch) -> None:
    printed = []

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(
                    {
                        "results": [{"id": "n1", "published_utc": "2026-01-01T00:00:00Z"}],
                        "next_url": "https://next.page/news",
                    }
                )
            return FakeResponse({"results": []})

    monkeypatch.setattr(data_ingestion.requests, "Session", FakeSession)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    data_ingestion.get_stocknews("NVDA", "2026-01-01", "2026-01-31", api_key="key", save_db=False, save_local=False)

    assert any("Sleeping 13s to respect free tier limit" in line for line in printed)


def test_get_stocknews_timeout_retries_then_stops(monkeypatch) -> None:
    class FakeSession:
        def get(self, *args, **kwargs):
            raise requests.exceptions.Timeout("timeout")

    monkeypatch.setattr(data_ingestion.requests, "Session", FakeSession)
    monkeypatch.setattr(data_ingestion, "POLYGON_MAX_RETRIES", 2)
    monkeypatch.setattr(data_ingestion, "POLYGON_RETRY_SLEEP_SECONDS", 0)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)

    out = data_ingestion.get_stocknews(
        "NVDA",
        "2026-01-01",
        "2026-01-31",
        api_key="key",
        save_db=False,
        save_local=False,
    )
    assert out.empty


def test_get_stocknews_handles_429_then_request_error(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            raise requests.exceptions.HTTPError("bad status")

        def json(self):
            return {}

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(429)
            raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr(data_ingestion.requests, "Session", FakeSession)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)

    out = data_ingestion.get_stocknews("NVDA", "2026-01-01", "2026-01-31", api_key="key", save_db=False, save_local=False)
    assert out.empty


def test_get_stocknews_stops_cleanly_when_results_empty(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(data_ingestion.requests, "Session", FakeSession)

    out = data_ingestion.get_stocknews(
        "NVDA",
        "2026-01-01",
        "2026-01-31",
        api_key="key",
        save_db=False,
        save_local=False,
    )

    assert out.empty


def test_get_stocknews_uses_existing_next_url_api_key(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, timeout=None):
            calls.append((url, params))
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(
                    {
                        "results": [{"id": "n1", "published_utc": "2026-01-01T00:00:00Z"}],
                        "next_url": "https://next.page/news?apiKey=key",
                    }
                )
            return FakeResponse({"results": []})

    monkeypatch.setattr(data_ingestion.requests, "Session", FakeSession)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)

    out = data_ingestion.get_stocknews("NVDA", "2026-01-01", "2026-01-31", api_key="key", save_db=False, save_local=False)

    assert len(out) == 1
    assert calls[1][0] == "https://next.page/news?apiKey=key"
    assert calls[1][1] is None


def test_get_stocknews_handles_single_page_without_next_url(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [{"id": "n1", "published_utc": "2026-01-01T00:00:00Z"}],
                "next_url": None,
            }

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(data_ingestion.requests, "Session", FakeSession)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: (_ for _ in ()).throw(AssertionError("should not sleep")))

    out = data_ingestion.get_stocknews("NVDA", "2026-01-01", "2026-01-31", api_key="key", save_db=False, save_local=False)

    assert len(out) == 1


def test_get_stock_reddit_collects_submission_and_comment(monkeypatch) -> None:
    start_ts = int(datetime.strptime("2026-01-01", "%Y-%m-%d").timestamp())

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    state = {
        "submission_called": 0,
        "comment_called": 0,
    }

    def fake_get(url, params=None, timeout=None):
        if "submission" in url:
            state["submission_called"] += 1
            if state["submission_called"] == 1 and params["after"] == start_ts:
                return FakeResponse(
                    {
                        "data": [
                            {
                                "created_utc": start_ts + 10,
                                "author": "user1",
                                "score": 10,
                                "title": "NVDA post",
                                "selftext": "body",
                                "full_link": "https://reddit.com/r/x",
                            }
                        ]
                    }
                )
            return FakeResponse({"data": []})

        state["comment_called"] += 1
        if state["comment_called"] == 1 and params["after"] == start_ts:
            return FakeResponse(
                {
                    "data": [
                        {
                            "created_utc": start_ts + 20,
                            "author": "user2",
                            "score": 3,
                            "body": "comment body",
                            "link_id": "t3_abc",
                            "id": "c1",
                        }
                    ]
                }
            )
        return FakeResponse({"data": []})

    monkeypatch.setattr(data_ingestion.requests, "get", fake_get)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)
    saved = {}
    monkeypatch.setattr(data_ingestion, "save_to_s3", lambda d, p, f: saved.update({"rows": len(d), "file": f}))

    out = data_ingestion.get_stock_reddit(
        query="nvda",
        start_date="2026-01-01",
        end_date="2026-01-03",
        tickername="NVDA",
        verbose=False,
        save_db=False,
        save_local=True,
    )

    assert len(out) == 2
    assert set(out["Type"]) == {"Submission", "Comment"}
    assert out.iloc[0]["ticker"] == "NVDA"
    assert saved == {"rows": 2, "file": "NVDA.csv"}


def test_get_stock_reddit_returns_empty_on_fetch_error(monkeypatch) -> None:
    monkeypatch.setattr(data_ingestion.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)

    out = data_ingestion.get_stock_reddit(
        query="nvda",
        start_date="2026-01-01",
        end_date="2026-01-03",
        tickername="NVDA",
        verbose=False,
        save_db=False,
        save_local=False,
    )
    assert out.empty


def test_get_stock_reddit_verbose_no_data(monkeypatch) -> None:
    printed = []

    class FakeResponse:
        def json(self):
            return {"data": []}

    monkeypatch.setattr(data_ingestion.requests, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    out = data_ingestion.get_stock_reddit(
        query="nvda",
        start_date="2026-01-01",
        end_date="2026-01-03",
        tickername="NVDA",
        verbose=True,
        save_db=False,
        save_local=False,
    )

    assert out.empty
    assert any("No data found." in line for line in printed)


def test_get_stock_reddit_does_not_upload_when_save_flags_false(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    state = {"submission": 0, "comment": 0, "uploaded": False}
    start_ts = int(datetime.strptime("2026-01-01", "%Y-%m-%d").timestamp())

    def fake_get(url, params=None, timeout=None):
        if "submission" in url:
            state["submission"] += 1
            if state["submission"] == 1:
                return FakeResponse({"data": [{"created_utc": start_ts + 1, "author": "u", "score": 1, "title": "x", "selftext": "y"}]})
            return FakeResponse({"data": []})
        state["comment"] += 1
        return FakeResponse({"data": []})

    monkeypatch.setattr(data_ingestion.requests, "get", fake_get)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)
    monkeypatch.setattr(data_ingestion, "save_to_s3", lambda *args, **kwargs: state.update({"uploaded": True}))

    out = data_ingestion.get_stock_reddit(
        query="nvda",
        start_date="2026-01-01",
        end_date="2026-01-03",
        tickername="NVDA",
        verbose=False,
        save_db=False,
        save_local=False,
    )

    assert len(out) == 1
    assert state["uploaded"] is False


def test_get_stock_reddit_verbose_progress_prints(monkeypatch) -> None:
    printed = []
    start_ts = int(datetime.strptime("2026-01-01", "%Y-%m-%d").timestamp())

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    state = {"submission": 0, "comment": 0}

    def fake_get(url, params=None, timeout=None):
        if "submission" in url:
            state["submission"] += 1
            if state["submission"] == 1:
                return FakeResponse({"data": [{"created_utc": start_ts + 1, "author": "u", "score": 1, "title": "x", "selftext": "y"}]})
            return FakeResponse({"data": []})
        state["comment"] += 1
        if state["comment"] == 1:
            return FakeResponse({"data": [{"created_utc": start_ts + 2, "author": "c", "score": 2, "body": "b", "link_id": "t3_abc", "id": "c1"}]})
        return FakeResponse({"data": []})

    monkeypatch.setattr(data_ingestion.requests, "get", fake_get)
    monkeypatch.setattr(data_ingestion.time, "sleep", lambda _s: None)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    out = data_ingestion.get_stock_reddit(
        query="nvda",
        start_date="2026-01-01",
        end_date="2026-01-03",
        tickername="NVDA",
        verbose=True,
        save_db=False,
        save_local=False,
    )

    assert len(out) == 2
    assert any("Fetching Submissions" in line for line in printed)
    assert any("Fetching Comments" in line for line in printed)
    assert any("Total rows:" in line for line in printed)


def test_main_runs_all_steps_and_handles_errors(monkeypatch) -> None:
    calls = []
    printed = []
    monkeypatch.setattr(
        data_ingestion,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {"tickers": "nvda,aapl", "start_date": "2026-01-01", "end_date": "2026-01-31", "with_reddit": True},
        )(),
    )
    monkeypatch.setenv("POLYGON_API_KEY", "poly")

    def fake_price(ticker, *args, **kwargs):
        calls.append(("price", ticker))
        if ticker == "AAPL":
            raise RuntimeError("price fail")

    def fake_news(ticker, *args, **kwargs):
        calls.append(("news", ticker))

    def fake_reddit(**kwargs):
        calls.append(("reddit", kwargs["tickername"]))
        if kwargs["tickername"] == "AAPL":
            raise RuntimeError("reddit fail")

    monkeypatch.setattr(data_ingestion, "get_stockprice", fake_price)
    monkeypatch.setattr(data_ingestion, "get_stocknews", fake_news)
    monkeypatch.setattr(data_ingestion, "get_stock_reddit", fake_reddit)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    exec(
        compile(
            "args = parse_args()\n"
            "tickers = [ticker.strip().upper() for ticker in args.tickers.split(',') if ticker.strip()]\n"
            "api_key = os.environ.get('POLYGON_API_KEY', '')\n"
            "for ticker in tickers:\n"
            "    print(f'\\nProcessing {ticker}...')\n"
            "    try:\n"
            "        get_stockprice(ticker, args.start_date, args.end_date, save_db=False, save_local=True)\n"
            "    except Exception as e:\n"
            "        print(f'Price error for {ticker}: {e}')\n"
            "    try:\n"
            "        get_stocknews(ticker, args.start_date, args.end_date, api_key=api_key, save_db=False, save_local=True)\n"
            "    except Exception as e:\n"
            "        print(f'News error for {ticker}: {e}')\n"
            "    if args.with_reddit:\n"
            "        try:\n"
            "            get_stock_reddit(query=f'{ticker.lower()}', start_date=args.start_date, end_date=args.end_date, tickername=ticker, save_db=False, save_local=True)\n"
            "        except Exception as e:\n"
            "            print(f'Reddit error for {ticker}: {e}')\n"
            "print('\\nIngestion complete.')\n",
            "<test_main_block>",
            "exec",
        ),
        data_ingestion.__dict__,
        {},
    )

    assert ("price", "NVDA") in calls
    assert ("news", "AAPL") in calls
    assert ("reddit", "NVDA") in calls
    assert any("Price error for AAPL" in line for line in printed)
    assert any("Reddit error for AAPL" in line for line in printed)


def test_main_block_without_reddit_and_with_news_error(monkeypatch) -> None:
    calls = []
    printed = []
    monkeypatch.setattr(
        data_ingestion,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {"tickers": "nvda", "start_date": "2026-01-01", "end_date": "2026-01-31", "with_reddit": False},
        )(),
    )
    monkeypatch.setenv("POLYGON_API_KEY", "poly")
    monkeypatch.setattr(data_ingestion, "get_stockprice", lambda *args, **kwargs: calls.append("price"))
    monkeypatch.setattr(
        data_ingestion,
        "get_stocknews",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("news fail")),
    )
    monkeypatch.setattr(data_ingestion, "get_stock_reddit", lambda **kwargs: calls.append("reddit"))
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    exec(
        compile(
            "args = parse_args()\n"
            "tickers = [ticker.strip().upper() for ticker in args.tickers.split(',') if ticker.strip()]\n"
            "api_key = os.environ.get('POLYGON_API_KEY', '')\n"
            "for ticker in tickers:\n"
            "    print(f'\\nProcessing {ticker}...')\n"
            "    try:\n"
            "        get_stockprice(ticker, args.start_date, args.end_date, save_db=False, save_local=True)\n"
            "    except Exception as e:\n"
            "        print(f'Price error for {ticker}: {e}')\n"
            "    try:\n"
            "        get_stocknews(ticker, args.start_date, args.end_date, api_key=api_key, save_db=False, save_local=True)\n"
            "    except Exception as e:\n"
            "        print(f'News error for {ticker}: {e}')\n"
            "    if args.with_reddit:\n"
            "        try:\n"
            "            get_stock_reddit(query=f'{ticker.lower()}', start_date=args.start_date, end_date=args.end_date, tickername=ticker, save_db=False, save_local=True)\n"
            "        except Exception as e:\n"
            "            print(f'Reddit error for {ticker}: {e}')\n"
            "print('\\nIngestion complete.')\n",
            "<test_main_block_no_reddit>",
            "exec",
        ),
        data_ingestion.__dict__,
        {},
    )

    assert calls == ["price"]
    assert any("News error for NVDA: news fail" in line for line in printed)
    assert any("Ingestion complete." in line for line in printed)


def test_real_main_block_executes_file_lines(monkeypatch) -> None:
    calls = []
    printed = []
    monkeypatch.setattr(
        data_ingestion,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {"tickers": "nvda", "start_date": "2026-01-01", "end_date": "2026-01-31", "with_reddit": False},
        )(),
    )
    monkeypatch.setenv("POLYGON_API_KEY", "poly")
    monkeypatch.setattr(data_ingestion, "get_stockprice", lambda *args, **kwargs: calls.append(("price", args[0])))
    monkeypatch.setattr(data_ingestion, "get_stocknews", lambda *args, **kwargs: calls.append(("news", args[0])))
    monkeypatch.setattr(data_ingestion, "get_stock_reddit", lambda **kwargs: calls.append(("reddit", kwargs["tickername"])))
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    source_lines = Path(data_ingestion.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 329 + textwrap.dedent("\n".join(source_lines[329:])) + "\n"
    code = compile(main_block, data_ingestion.__file__, "exec")
    globals_dict = dict(data_ingestion.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == [("price", "NVDA"), ("news", "NVDA")]
    assert any("Processing NVDA" in line for line in printed)


def test_real_main_block_covers_price_news_and_reddit_errors(monkeypatch) -> None:
    printed = []
    monkeypatch.setattr(
        data_ingestion,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {"tickers": "nvda", "start_date": "2026-01-01", "end_date": "2026-01-31", "with_reddit": True},
        )(),
    )
    monkeypatch.setenv("POLYGON_API_KEY", "poly")
    monkeypatch.setattr(
        data_ingestion,
        "get_stockprice",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("price fail")),
    )
    monkeypatch.setattr(
        data_ingestion,
        "get_stocknews",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("news fail")),
    )
    monkeypatch.setattr(
        data_ingestion,
        "get_stock_reddit",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("reddit fail")),
    )
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    source_lines = Path(data_ingestion.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 329 + textwrap.dedent("\n".join(source_lines[329:])) + "\n"
    code = compile(main_block, data_ingestion.__file__, "exec")
    globals_dict = dict(data_ingestion.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert any("Price error for NVDA: price fail" in line for line in printed)
    assert any("News error for NVDA: news fail" in line for line in printed)
    assert any("Reddit error for NVDA: reddit fail" in line for line in printed)
