import pandas as pd
import pytest
from types import SimpleNamespace
from pathlib import Path
import textwrap

from app.pipelines import data_cleaning


def test_s3_key_normalizes_prefix() -> None:
    assert data_cleaning._s3_key("/clean/stock_news/", "NVDA.csv") == "clean/stock_news/NVDA.csv"
    assert data_cleaning._s3_key("", "NVDA.csv") == "NVDA.csv"


def test_load_stock_news_csv_missing_file_raises(tmp_path) -> None:
    try:
        data_cleaning.load_stock_news("NVDA", source="csv", csv_dir=str(tmp_path))
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_load_stock_news_rejects_invalid_source() -> None:
    try:
        data_cleaning.load_stock_news("NVDA", source="db")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "source must be one of" in str(exc)


def test_require_bucket_and_load_stock_news_from_s3(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_S3_BUCKET", "bucket")

    class Body:
        def read(self):
            return b"id,title\n1,Headline\n"

    class FakeS3:
        def get_object(self, Bucket, Key):
            return {"Body": Body()}

    monkeypatch.setattr(data_cleaning, "_s3_client", lambda: FakeS3())
    assert data_cleaning._require_bucket() == "bucket"

    df = data_cleaning.load_stock_news("NVDA", source="s3")
    assert list(df["title"]) == ["Headline"]


def test_s3_client_uses_region(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("AWS_REGION", "ca-central-1")
    monkeypatch.setattr(
        data_cleaning.boto3,
        "client",
        lambda service, region_name=None: calls.append((service, region_name)) or "client",
    )

    assert data_cleaning._s3_client() == "client"
    assert calls == [("s3", "ca-central-1")]


def test_s3_client_without_region_uses_default_client(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setattr(data_cleaning.boto3, "client", lambda service: calls.append(service) or "client")

    assert data_cleaning._s3_client() == "client"
    assert calls == ["s3"]


def test_require_bucket_raises_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("PIPELINE_S3_BUCKET", raising=False)
    with pytest.raises(ValueError, match="Missing PIPELINE_S3_BUCKET"):
        data_cleaning._require_bucket()


def test_load_stock_news_s3_error_bubbles(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_S3_BUCKET", "bucket")

    class FakeS3:
        def get_object(self, Bucket, Key):
            raise RuntimeError("s3 down")

    monkeypatch.setattr(data_cleaning, "_s3_client", lambda: FakeS3())

    with pytest.raises(RuntimeError, match="s3 down"):
        data_cleaning.load_stock_news("NVDA", source="s3")


def test_load_stock_news_csv_success(tmp_path) -> None:
    csv_path = tmp_path / "NVDA.csv"
    csv_path.write_text("id,title\n1,Headline\n", encoding="utf-8")

    df = data_cleaning.load_stock_news("NVDA", source="csv", csv_dir=str(tmp_path))

    assert list(df["title"]) == ["Headline"]


def test_clean_news_dataframe_filters_dedupes_and_removes_noise() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "1",
                "published_utc": "2026-01-01T00:00:00Z",
                "title": "Apple launches iPhone",
                "description": "New product event",
            },
            {
                "id": "2",
                "published_utc": "2026-01-01T02:00:00Z",
                "title": "Apple launches iPhone!",
                "description": "Duplicate",
            },
            {
                "id": "3",
                "published_utc": "2026-01-02T00:00:00Z",
                "title": "Why Apple stock may rise",
                "description": "Opinion piece",
            },
            {
                "id": "4",
                "published_utc": "2026-01-03T00:00:00Z",
                "title": "Banana market update",
                "description": "Irrelevant",
            },
        ]
    )

    out = data_cleaning.clean_news_dataframe(df, ["apple", "aapl", "iphone"])

    assert list(out["id"]) == ["1"]
    assert out.iloc[0]["published_utc"] == "2026-01-01T00:00:00Z"


def test_clean_news_dataframe_returns_empty_when_no_rows_match_keywords() -> None:
    df = pd.DataFrame(
        [
            {
                "id": "1",
                "published_utc": "2026-01-01T00:00:00Z",
                "title": "Banana market update",
                "description": "Irrelevant",
            }
        ]
    )

    out = data_cleaning.clean_news_dataframe(df, ["nvidia"])

    assert out.empty


def test_clean_news_dataframe_empty_input_returns_copy() -> None:
    df = pd.DataFrame(columns=["id", "published_utc", "title", "description"])
    out = data_cleaning.clean_news_dataframe(df, ["nvidia"])
    assert out.empty
    assert list(out.columns) == list(df.columns)


def test_save_cleaned_to_local_csv_writes_file(tmp_path) -> None:
    df = pd.DataFrame([{"id": "1", "title": "x"}])
    data_cleaning.save_cleaned_to_local_csv(df, "NVDA", output_dir=str(tmp_path))

    saved = pd.read_csv(tmp_path / "NVDA.csv")
    assert list(saved["id"]) == [1]


def test_save_cleaned_to_local_csv_noop_on_empty(tmp_path) -> None:
    data_cleaning.save_cleaned_to_local_csv(pd.DataFrame(), "NVDA", output_dir=str(tmp_path))
    assert (tmp_path / "NVDA.csv").exists() is False


def test_save_cleaned_to_s3_skips_empty_and_uploads_non_empty(monkeypatch) -> None:
    uploaded = {}

    class FakeS3:
        def put_object(self, **kwargs):
            uploaded.update(kwargs)

    monkeypatch.setenv("PIPELINE_S3_BUCKET", "bucket")
    monkeypatch.setattr(data_cleaning, "_s3_client", lambda: FakeS3())
    data_cleaning.save_cleaned_to_s3(pd.DataFrame(), "NVDA")
    assert uploaded == {}

    data_cleaning.save_cleaned_to_s3(pd.DataFrame([{"id": "1"}]), "NVDA")
    assert uploaded["Bucket"] == "bucket"
    assert uploaded["Key"].endswith("NVDA.csv")


def test_clean_stock_news_routes_to_csv_output(monkeypatch, tmp_path) -> None:
    loaded = pd.DataFrame([
        {
            "id": "1",
            "published_utc": "2026-01-01T00:00:00Z",
            "title": "Apple launches iPhone",
            "description": "desc",
        }
    ])
    monkeypatch.setattr(data_cleaning, "load_stock_news", lambda *args, **kwargs: loaded)
    monkeypatch.setattr(data_cleaning, "clean_news_dataframe", lambda df, _kw: df)

    called = {}

    def fake_save(df, ticker, output_dir):
        called["rows"] = len(df)
        called["ticker"] = ticker
        called["output_dir"] = output_dir

    monkeypatch.setattr(data_cleaning, "save_cleaned_to_local_csv", fake_save)

    data_cleaning.clean_stock_news(
        "NVDA",
        ["nvidia"],
        source="csv",
        output="csv",
        input_csv_dir=str(tmp_path),
        output_csv_dir=str(tmp_path / "out"),
    )

    assert called["rows"] == 1
    assert called["ticker"] == "NVDA"


def test_clean_stock_news_routes_to_s3_output(monkeypatch) -> None:
    loaded = pd.DataFrame(
        [
            {
                "id": "1",
                "published_utc": "2026-01-01T00:00:00Z",
                "title": "NVIDIA launches product",
                "description": "desc",
            }
        ]
    )
    called = {}
    monkeypatch.setattr(data_cleaning, "load_stock_news", lambda *args, **kwargs: loaded)
    monkeypatch.setattr(data_cleaning, "clean_news_dataframe", lambda df, _kw: df)
    monkeypatch.setattr(
        data_cleaning,
        "save_cleaned_to_s3",
        lambda df, ticker: called.update({"rows": len(df), "ticker": ticker}),
    )

    data_cleaning.clean_stock_news("NVDA", ["nvidia"], source="s3", output="s3")

    assert called == {"rows": 1, "ticker": "NVDA"}


def test_clean_stock_news_load_error_is_handled(monkeypatch) -> None:
    monkeypatch.setattr(data_cleaning, "load_stock_news", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    # Should not raise.
    data_cleaning.clean_stock_news("NVDA", ["nvidia"], source="csv", output="csv")


def test_clean_stock_news_handles_empty_and_invalid_output(monkeypatch) -> None:
    monkeypatch.setattr(data_cleaning, "load_stock_news", lambda *args, **kwargs: pd.DataFrame())
    data_cleaning.clean_stock_news("NVDA", ["nvidia"], source="csv", output="csv")

    loaded = pd.DataFrame([{"id": "1", "published_utc": "2026-01-01T00:00:00Z", "title": "NVDA", "description": "nvidia"}])
    monkeypatch.setattr(data_cleaning, "load_stock_news", lambda *args, **kwargs: loaded)
    monkeypatch.setattr(data_cleaning, "clean_news_dataframe", lambda df, kw: df)
    with pytest.raises(ValueError, match="output must be one of"):
        data_cleaning.clean_stock_news("NVDA", ["nvidia"], source="csv", output="bad")


def test_parse_args_reads_cli(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["prog", "--tickers", "nvda,aapl", "--source", "csv", "--output", "csv"])
    args = data_cleaning.parse_args()
    assert args.tickers == "nvda,aapl"
    assert args.source == "csv"
    assert args.output == "csv"


def test_main_block_like_flow_skips_unknown_ticker(monkeypatch) -> None:
    printed = []
    calls = []
    monkeypatch.setattr(
        data_cleaning,
        "parse_args",
        lambda: SimpleNamespace(tickers="xyz,nvda", source="csv", output="csv"),
    )
    monkeypatch.setattr(
        data_cleaning,
        "clean_stock_news",
        lambda ticker, keywords, source, output: calls.append((ticker, tuple(keywords), source, output)),
    )
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    args = data_cleaning.parse_args()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]

    for ticker in tickers:
        keywords = data_cleaning.DEFAULT_TICKERS.get(ticker)
        if not keywords:
            print(f"Skipping {ticker}: no keyword config found.")
            continue

        print(f"\nCleaning data for {ticker}...")
        data_cleaning.clean_stock_news(ticker, keywords, source=args.source, output=args.output)

    print("\nCleaning complete.")

    assert any("Skipping XYZ: no keyword config found." in line for line in printed)
    assert calls == [("NVDA", tuple(data_cleaning.DEFAULT_TICKERS["NVDA"]), "csv", "csv")]


def test_main_block_like_flow_runs_known_ticker_with_s3(monkeypatch) -> None:
    printed = []
    calls = []
    monkeypatch.setattr(
        data_cleaning,
        "parse_args",
        lambda: SimpleNamespace(tickers="nvda", source="s3", output="s3"),
    )
    monkeypatch.setattr(
        data_cleaning,
        "clean_stock_news",
        lambda ticker, keywords, source, output: calls.append((ticker, tuple(keywords), source, output)),
    )
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    args = data_cleaning.parse_args()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    for ticker in tickers:
        keywords = data_cleaning.DEFAULT_TICKERS.get(ticker)
        if not keywords:
            print(f"Skipping {ticker}: no keyword config found.")
            continue
        print(f"\nCleaning data for {ticker}...")
        data_cleaning.clean_stock_news(ticker, keywords, source=args.source, output=args.output)
    print("\nCleaning complete.")

    assert any("Cleaning data for NVDA" in line for line in printed)
    assert calls == [("NVDA", tuple(data_cleaning.DEFAULT_TICKERS["NVDA"]), "s3", "s3")]


def test_real_main_block_executes_file_lines(monkeypatch) -> None:
    calls = []
    printed = []
    monkeypatch.setattr(
        data_cleaning,
        "parse_args",
        lambda: SimpleNamespace(tickers="xyz,nvda", source="csv", output="csv"),
    )
    monkeypatch.setattr(
        data_cleaning,
        "clean_stock_news",
        lambda ticker, keywords, source, output: calls.append((ticker, tuple(keywords), source, output)),
    )
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    source_lines = Path(data_cleaning.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 198 + textwrap.dedent("\n".join(source_lines[198:])) + "\n"
    code = compile(main_block, data_cleaning.__file__, "exec")
    globals_dict = dict(data_cleaning.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert any("Skipping XYZ: no keyword config found." in line for line in printed)
    assert calls == [("NVDA", tuple(data_cleaning.DEFAULT_TICKERS["NVDA"]), "csv", "csv")]
