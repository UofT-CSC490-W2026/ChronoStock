import argparse
import builtins
from types import SimpleNamespace
from pathlib import Path
import textwrap

import pandas as pd
import pytest

from app.pipelines import run_monthly_event_pipeline as monthly


def test_require_env_and_date_helpers(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_S3_BUCKET", "bucket")
    assert monthly._require_env("PIPELINE_S3_BUCKET") == "bucket"

    monkeypatch.delenv("PIPELINE_S3_BUCKET", raising=False)
    with pytest.raises(ValueError, match="Missing required setting"):
        monthly._require_env("PIPELINE_S3_BUCKET")

    assert monthly._date_range_for_incremental("2026-03-20", 5) == ("2026-03-15", "2026-03-20")
    assert monthly._date_range_for_incremental("2026-03-20", 0) == ("2026-03-19", "2026-03-20")
    assert monthly._rolling_five_year_start("2026-03-20") == "2021-03-21"


def test_read_s3_csv_or_empty_handles_missing_and_reads_csv(monkeypatch) -> None:
    class NoSuchKey(Exception):
        pass

    class Body:
        def read(self):
            return b"id,value\n1,2\n"

    class Client:
        def __init__(self, mode):
            self.mode = mode
            self.exceptions = SimpleNamespace(NoSuchKey=NoSuchKey)

        def get_object(self, Bucket, Key):
            if self.mode == "missing":
                raise NoSuchKey()
            return {"Body": Body()}

    monkeypatch.setattr(monthly, "_s3_client", lambda: Client("missing"))
    assert monthly._read_s3_csv_or_empty("b", "k").empty

    monkeypatch.setattr(monthly, "_s3_client", lambda: Client("ok"))
    frame = monthly._read_s3_csv_or_empty("b", "k")
    assert list(frame.columns) == ["id", "value"]
    assert frame.iloc[0]["value"] == 2


def test_merge_raw_news_and_clean_news() -> None:
    existing_raw = pd.DataFrame(
        [
            {"id": "1", "published_utc": "2026-03-02T00:00:00Z", "headline": "old", "ticker": None},
            {"id": "2", "published_utc": "2026-03-03T00:00:00Z", "headline": "keep", "ticker": "NVDA"},
        ]
    )
    fresh_raw = pd.DataFrame(
        [
            {"id": "1", "published_utc": "2026-03-04T00:00:00Z", "headline": "newer"},
            {"id": "3", "published_utc": "2026-03-01T00:00:00Z", "headline": "fresh"},
        ]
    )
    merged_raw = monthly._merge_raw_news(existing_raw, fresh_raw, "NVDA")
    assert list(merged_raw["id"]) == ["3", "2", "1"]
    assert list(merged_raw["ticker"]) == ["NVDA", "NVDA", "NVDA"]

    existing_clean = pd.DataFrame([{"id": "1", "published_utc": "2026-03-02T00:00:00Z", "title": "old"}])
    fresh_clean = pd.DataFrame([{"id": "1", "published_utc": "2026-03-03T00:00:00Z", "title": "new"}])
    merged_clean = monthly._merge_clean_news(existing_clean, fresh_clean)
    assert merged_clean.iloc[0]["published_utc"] == "2026-03-03T00:00:00Z"
    assert merged_clean.iloc[0]["title"] == "new"


def test_merge_helpers_handle_missing_id_and_ticker_columns() -> None:
    raw = monthly._merge_raw_news(
        pd.DataFrame([{"published_utc": "2026-03-02T00:00:00Z", "headline": "a"}]),
        pd.DataFrame([{"published_utc": "2026-03-01T00:00:00Z", "headline": "b"}]),
        "NVDA",
    )
    clean = monthly._merge_clean_news(
        pd.DataFrame([{"published_utc": "2026-03-02T00:00:00Z", "title": "a"}]),
        pd.DataFrame([{"published_utc": "2026-03-01T00:00:00Z", "title": "b"}]),
    )

    assert list(raw["ticker"]) == ["NVDA", "NVDA"]
    assert list(clean["title"]) == ["b", "a"]


def test_parse_args_reads_cli(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--tickers", "nvda,aapl", "--start-date", "2026-01-01", "--skip-ingestion"],
    )
    args = monthly.parse_args()
    assert args.tickers == "nvda,aapl"
    assert args.start_date == "2026-01-01"
    assert args.skip_ingestion is True


def test_main_runs_success_path(monkeypatch) -> None:
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="nvda,aapl",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=3,
            skip_ingestion=False,
            skip_cleaning=False,
            skip_event_pipeline=False,
        ),
    )
    monkeypatch.setattr(monthly, "_require_env", lambda name: {"PIPELINE_S3_BUCKET": "bucket", "POLYGON_API_KEY": "poly", "LLM_API_KEY": "llm"}[name])
    monkeypatch.setattr(monthly, "_read_s3_csv_or_empty", lambda bucket, key: pd.DataFrame([{"id": "1", "published_utc": "2026-03-19T00:00:00Z"}]))
    monkeypatch.setattr(monthly, "get_stockprice", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        monthly,
        "get_stocknews",
        lambda *args, **kwargs: pd.DataFrame([{"id": "1", "published_utc": "2026-03-20T00:00:00Z"}]),
    )
    monkeypatch.setattr(monthly, "_merge_raw_news", lambda existing, fresh, ticker: pd.DataFrame([{"id": "1"}]))
    monkeypatch.setattr(monthly, "save_to_s3", lambda df, prefix, name: None)
    monkeypatch.setitem(monthly.CLEANING_KEYWORDS, "NVDA", ["nvidia"])
    monkeypatch.setitem(monthly.CLEANING_KEYWORDS, "AAPL", ["apple"])
    monkeypatch.setattr(monthly, "clean_news_dataframe", lambda df, keywords: pd.DataFrame([{"id": "1", "published_utc": "2026-03-20T00:00:00Z"}]))
    monkeypatch.setattr(monthly, "_merge_clean_news", lambda existing, fresh: fresh)
    monkeypatch.setattr(monthly, "save_cleaned_to_s3", lambda df, ticker: None)
    run_calls = []
    monkeypatch.setattr(monthly, "run_pipeline_for_ticker", lambda **kwargs: run_calls.append(kwargs["ticker"]))
    monkeypatch.setenv("PIPELINE_LLM_BATCH_SIZE", "10")
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    monthly.main()
    assert run_calls == ["NVDA", "AAPL"]


def test_main_collects_failures_and_honors_skip_flags(monkeypatch) -> None:
    printed = []
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="nvda,msft",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=2,
            skip_ingestion=False,
            skip_cleaning=False,
            skip_event_pipeline=True,
        ),
    )
    monkeypatch.setattr(monthly, "_require_env", lambda name: {"PIPELINE_S3_BUCKET": "bucket", "POLYGON_API_KEY": "poly"}[name])
    monkeypatch.setitem(monthly.CLEANING_KEYWORDS, "NVDA", ["nvidia"])
    monkeypatch.setattr(monthly, "get_stockprice", lambda *args, **kwargs: None)

    def fake_get_stocknews(ticker, *args, **kwargs):
        if ticker == "MSFT":
            raise RuntimeError("ingest failed")
        return pd.DataFrame([{"id": "1", "published_utc": "2026-03-20T00:00:00Z"}])

    monkeypatch.setattr(monthly, "get_stocknews", fake_get_stocknews)
    monkeypatch.setattr(
        monthly,
        "_read_s3_csv_or_empty",
        lambda bucket, key: pd.DataFrame([{"id": "1", "published_utc": "2026-03-20T00:00:00Z"}])
        if key.endswith("NVDA.csv")
        else pd.DataFrame(),
    )
    monkeypatch.setattr(monthly, "_merge_raw_news", lambda existing, fresh, ticker: fresh)
    monkeypatch.setattr(monthly, "save_to_s3", lambda df, prefix, name: None)
    monkeypatch.setattr(monthly, "clean_news_dataframe", lambda df, keywords: (_ for _ in ()).throw(RuntimeError("clean failed")))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    monthly.main()

    assert any("Ingestion failed for MSFT" in line for line in printed)
    assert any("Cleaning failed for NVDA" in line for line in printed)
    assert any("Monthly pipeline completed with 2 failure" in line for line in printed)


def test_read_s3_csv_or_empty_handles_404_code(monkeypatch) -> None:
    class FakeClient:
        class exceptions:
            class NoSuchKey(Exception):
                pass

        def get_object(self, Bucket, Key):
            exc = RuntimeError("missing")
            exc.response = {"Error": {"Code": "404"}}
            raise exc

    monkeypatch.setattr(monthly, "_s3_client", lambda: FakeClient())
    assert monthly._read_s3_csv_or_empty("b", "k").empty


def test_s3_client_uses_region_and_require_env_missing(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setattr(
        monthly.boto3,
        "client",
        lambda service, region_name=None: calls.append((service, region_name)) or "client",
    )
    assert monthly._s3_client() == "client"
    assert calls == [("s3", "us-east-1")]

    monkeypatch.delenv("MISSING_ENV", raising=False)
    with pytest.raises(ValueError, match="MISSING_ENV"):
        monthly._require_env("MISSING_ENV")


def test_s3_client_without_region_uses_default_client(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setattr(monthly.boto3, "client", lambda service: calls.append(service) or "client")

    assert monthly._s3_client() == "client"
    assert calls == ["s3"]


def test_read_s3_csv_or_empty_reraises_unexpected_error(monkeypatch) -> None:
    class FakeClient:
        class exceptions:
            class NoSuchKey(Exception):
                pass

        def get_object(self, Bucket, Key):
            exc = RuntimeError("boom")
            exc.response = {"Error": {"Code": "500"}}
            raise exc

    monkeypatch.setattr(monthly, "_s3_client", lambda: FakeClient())
    with pytest.raises(RuntimeError, match="boom"):
        monthly._read_s3_csv_or_empty("b", "k")


def test_main_skips_cleaning_without_keywords_or_raw_news(monkeypatch) -> None:
    printed = []
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="xyz,nvda",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=2,
            skip_ingestion=True,
            skip_cleaning=False,
            skip_event_pipeline=True,
        ),
    )
    monkeypatch.setattr(monthly, "_require_env", lambda name: "bucket")
    monkeypatch.delitem(monthly.CLEANING_KEYWORDS, "XYZ", raising=False)
    monkeypatch.setitem(monthly.CLEANING_KEYWORDS, "NVDA", ["nvidia"])
    monkeypatch.setattr(monthly, "_read_s3_csv_or_empty", lambda bucket, key: pd.DataFrame())
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    monthly.main()

    assert any("Skipping cleaning for XYZ: no keyword config found." in line for line in printed)
    assert any("Skipping cleaning for NVDA: no raw news found." in line for line in printed)


def test_main_skips_when_incremental_raw_is_empty(monkeypatch) -> None:
    printed = []
    raw_df = pd.DataFrame([{"id": "1", "published_utc": "2026-01-01T00:00:00Z"}])
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="nvda",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=2,
            skip_ingestion=True,
            skip_cleaning=False,
            skip_event_pipeline=True,
        ),
    )
    monkeypatch.setattr(monthly, "_require_env", lambda name: "bucket")
    monkeypatch.setitem(monthly.CLEANING_KEYWORDS, "NVDA", ["nvidia"])
    monkeypatch.setattr(monthly, "_read_s3_csv_or_empty", lambda bucket, key: raw_df)
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    monthly.main()
    assert any("No incremental raw news to clean for NVDA." in line for line in printed)


def test_main_skips_event_pipeline_when_flag_set(monkeypatch) -> None:
    called = {"event": False}
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="nvda",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=2,
            skip_ingestion=True,
            skip_cleaning=True,
            skip_event_pipeline=True,
        ),
    )
    monkeypatch.setattr(monthly, "_require_env", lambda name: "bucket")
    monkeypatch.setattr(monthly, "run_pipeline_for_ticker", lambda **kwargs: called.update({"event": True}))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    monthly.main()
    assert called["event"] is False


def test_main_event_pipeline_failure_is_reported(monkeypatch) -> None:
    printed = []
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="nvda",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=2,
            skip_ingestion=True,
            skip_cleaning=True,
            skip_event_pipeline=False,
        ),
    )

    def fake_require(name):
        values = {"PIPELINE_S3_BUCKET": "bucket", "POLYGON_API_KEY": "poly", "LLM_API_KEY": "llm"}
        return values[name]

    monkeypatch.setattr(monthly, "_require_env", fake_require)
    monkeypatch.setattr(monthly, "run_pipeline_for_ticker", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("event fail")))
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    monthly.main()

    assert any("Event pipeline failed for NVDA: event fail" in line for line in printed)
    assert any("Monthly pipeline completed with 1 failure" in line for line in printed)


def test_main_ingestion_skips_empty_merge_without_upload(monkeypatch) -> None:
    uploads = {"called": False}
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="nvda",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=2,
            skip_ingestion=False,
            skip_cleaning=True,
            skip_event_pipeline=True,
        ),
    )
    monkeypatch.setattr(monthly, "_require_env", lambda name: {"PIPELINE_S3_BUCKET": "bucket", "POLYGON_API_KEY": "poly"}[name])
    monkeypatch.setattr(monthly, "get_stockprice", lambda *args, **kwargs: None)
    monkeypatch.setattr(monthly, "_read_s3_csv_or_empty", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(monthly, "get_stocknews", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(monthly, "save_to_s3", lambda *args, **kwargs: uploads.update({"called": True}))
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    monthly.main()

    assert uploads["called"] is False


def test_main_cleaning_skips_empty_merged_clean_without_upload(monkeypatch) -> None:
    uploads = {"called": False}
    raw_df = pd.DataFrame([{"id": "1", "published_utc": "2026-03-20T00:00:00Z", "title": "NVDA", "description": "nvidia"}])
    monkeypatch.setattr(
        monthly,
        "parse_args",
        lambda: argparse.Namespace(
            tickers="nvda",
            start_date="2026-01-01",
            end_date="2026-03-20",
            benchmark_ticker="^DJI",
            incremental_days=2,
            skip_ingestion=True,
            skip_cleaning=False,
            skip_event_pipeline=True,
        ),
    )
    monkeypatch.setattr(monthly, "_require_env", lambda name: "bucket")
    monkeypatch.setitem(monthly.CLEANING_KEYWORDS, "NVDA", ["nvidia"])
    monkeypatch.setattr(
        monthly,
        "_read_s3_csv_or_empty",
        lambda bucket, key: raw_df if key.endswith(f"{monthly.RAW_NEWS_PREFIX}/NVDA.csv") or key.endswith("raw/stock_news/NVDA.csv") else pd.DataFrame(),
    )
    monkeypatch.setattr(monthly, "clean_news_dataframe", lambda *args, **kwargs: pd.DataFrame())
    monkeypatch.setattr(monthly, "save_cleaned_to_s3", lambda *args, **kwargs: uploads.update({"called": True}))
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    monthly.main()

    assert uploads["called"] is False


def test_real_main_block_invokes_main(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(monthly, "main", lambda: calls.append("main"))

    source_lines = Path(monthly.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 252 + textwrap.dedent("\n".join(source_lines[252:])) + "\n"
    code = compile(main_block, monthly.__file__, "exec")
    globals_dict = dict(monthly.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == ["main"]
