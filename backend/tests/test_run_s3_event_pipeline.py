import sqlite3
from pathlib import Path
from types import SimpleNamespace
import sys
import argparse
import json
import textwrap

import pytest

from app.pipelines import run_s3_event_pipeline as pipeline


def test_require_env_prefers_explicit_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_TEST_KEY", "from_env")
    assert pipeline._require_env("PIPELINE_TEST_KEY", "from_arg") == "from_arg"


def test_require_env_uses_environment_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_TEST_KEY", "from_env")
    assert pipeline._require_env("PIPELINE_TEST_KEY", None) == "from_env"


def test_require_env_raises_on_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPELINE_TEST_KEY", raising=False)
    with pytest.raises(ValueError, match="Missing required setting"):
        pipeline._require_env("PIPELINE_TEST_KEY", None)


def test_build_s3_key_handles_empty_prefix() -> None:
    assert pipeline._build_s3_key("/", "file.csv") == "file.csv"


def test_build_s3_key_trims_slashes() -> None:
    assert pipeline._build_s3_key("events/filtered/", "NVDA.csv") == "events/filtered/NVDA.csv"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.marketwatch.com/story/x", "MarketWatch"),
        ("https://www.benzinga.com/news/1", "Benzinga"),
        ("https://www.fool.com/investing/1", "Motley Fool"),
        ("https://www.globenewswire.com/news-release/1", "GlobeNewsWire"),
        ("https://unknown.example.com/article", "News"),
    ],
)
def test_source_from_url_mappings(url: str, expected: str) -> None:
    assert pipeline._source_from_url(url) == expected


def test_parse_sentiment_uses_matching_insight_entry() -> None:
    row = {
        "ticker": "NVDA",
        "insights": '[{"ticker": "NVDA", "sentiment": "positive", "sentiment_reasoning": "beat"}]',
    }
    assert pipeline._parse_sentiment(row) == ("positive", "beat")


def test_parse_sentiment_invalid_json_falls_back_to_car() -> None:
    row = {"ticker": "NVDA", "insights": "not json", "car": "-0.7"}
    assert pipeline._parse_sentiment(row) == ("negative", None)


def test_parse_sentiment_neutral_when_zero_or_missing_car() -> None:
    row = {"ticker": "NVDA", "insights": "[]", "car": "0"}
    assert pipeline._parse_sentiment(row) == ("neutral", None)


def test_parse_sentiment_skips_non_matching_and_invalid_entries() -> None:
    row = {
        "ticker": "NVDA",
        "insights": json.dumps(
            [
                {"ticker": "AAPL", "sentiment": "positive"},
                {"ticker": "NVDA", "sentiment": "sideways"},
            ]
        ),
        "car": "-1.5",
    }
    assert pipeline._parse_sentiment(row) == ("negative", None)


def test_parse_sentiment_invalid_car_value_defaults_to_neutral() -> None:
    row = {"ticker": "NVDA", "insights": "[]", "car": "bad-car"}
    assert pipeline._parse_sentiment(row) == ("neutral", None)


def test_load_filtered_csv_skips_invalid_rows_and_truncates_summary(tmp_path: Path) -> None:
    csv_path = tmp_path / "filtered.csv"
    long_desc = "x" * 700
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        f"nvda,2026-01-01,Event A,{long_desc},https://example.com/a,1.25,1.25,,[]\n"
        "nvda,,Missing Date,desc,https://example.com/b,0,0,id-2,[]\n"
        ",2026-01-01,Missing Ticker,desc,https://example.com/c,0,0,id-3,[]\n",
        encoding="utf-8",
    )

    rows = pipeline._load_filtered_csv(csv_path, default_ticker="nvda")
    assert len(rows) == 2
    assert rows[0]["ticker"] == "NVDA"
    assert len(rows[0]["summary"]) == 500
    assert rows[0]["event_id"].startswith("NVDA-2026-01-01-")
    assert rows[1]["ticker"] == "NVDA"


def test_load_filtered_csv_sets_invalid_car_values_to_none(tmp_path: Path) -> None:
    csv_path = tmp_path / "filtered_invalid_car.csv"
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "nvda,2026-01-01,Event A,desc,https://example.com/a,bad,also-bad,id-1,[]\n",
        encoding="utf-8",
    )

    rows = pipeline._load_filtered_csv(csv_path, default_ticker="nvda")

    assert len(rows) == 1
    assert rows[0]["car"] is None
    assert rows[0]["abs_car"] is None


def test_replace_ticker_events_replaces_existing_rows() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE stock_events (
            ticker TEXT NOT NULL,
            event_id TEXT NOT NULL,
            event_date TEXT NOT NULL,
            published_utc TEXT,
            title TEXT NOT NULL,
            summary TEXT,
            sentiment TEXT NOT NULL,
            sentiment_reasoning TEXT,
            source TEXT NOT NULL,
            url TEXT,
            car REAL,
            abs_car REAL,
            pipeline_run_at TEXT NOT NULL,
            PRIMARY KEY (ticker, event_id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO stock_events (
            ticker, event_id, event_date, published_utc, title, summary,
            sentiment, sentiment_reasoning, source, url, car, abs_car, pipeline_run_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "NVDA",
            "old-1",
            "2026-01-01",
            None,
            "Old",
            "Old",
            "neutral",
            None,
            "News",
            None,
            0.0,
            0.0,
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()

    inserted = pipeline._replace_ticker_events(
        conn,
        "NVDA",
        [
            {
                "ticker": "NVDA",
                "event_id": "new-1",
                "event_date": "2026-02-01",
                "published_utc": None,
                "title": "New",
                "summary": "Summary",
                "sentiment": "positive",
                "sentiment_reasoning": "reason",
                "source": "News",
                "url": "https://example.com",
                "car": 1.0,
                "abs_car": 1.0,
            }
        ],
        "2026-02-02T00:00:00+00:00",
    )
    conn.commit()

    rows = conn.execute("SELECT event_id FROM stock_events WHERE ticker = ?", ("NVDA",)).fetchall()
    assert inserted == 1
    assert rows == [("new-1",)]


def test_record_pipeline_run_inserts_row() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY,
            pipeline_name TEXT NOT NULL,
            scope TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            details TEXT
        )
        """
    )

    pipeline._record_pipeline_run(
        conn,
        run_id="run-1",
        status="completed",
        started_at="2026-01-01T00:00:00+00:00",
        completed_at="2026-01-01T00:00:01+00:00",
        details='{"rows":1}',
    )
    conn.commit()

    row = conn.execute("SELECT run_id, status FROM pipeline_runs").fetchone()
    assert row == ("run-1", "completed")


def test_write_filtered_results_to_db_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    filtered = tmp_path / "filtered.csv"
    filtered.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event,desc,https://example.com,1.0,1.0,id-1,[]\n",
        encoding="utf-8",
    )

    class FakeConn:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False
            self.closed = False

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

        def close(self) -> None:
            self.closed = True

    fake_conn = FakeConn()
    recorded_statuses: list[str] = []

    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_conn", lambda: fake_conn)
    monkeypatch.setattr(pipeline, "_replace_ticker_events", lambda *args, **kwargs: 1)

    def fake_record(*args, **kwargs):
        recorded_statuses.append(kwargs["status"])

    monkeypatch.setattr(pipeline, "_record_pipeline_run", fake_record)

    inserted = pipeline._write_filtered_results_to_db(filtered, "NVDA")

    assert inserted == 1
    assert fake_conn.committed is True
    assert fake_conn.rolled_back is False
    assert fake_conn.closed is True
    assert recorded_statuses == ["completed"]


def test_write_filtered_results_to_db_failure_records_failed_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    filtered = tmp_path / "filtered.csv"
    filtered.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event,desc,https://example.com,1.0,1.0,id-1,[]\n",
        encoding="utf-8",
    )

    class FakeConn:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0
            self.closed = False

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

        def close(self) -> None:
            self.closed = True

    fake_conn = FakeConn()
    recorded_statuses: list[str] = []

    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_conn", lambda: fake_conn)

    def boom(*args, **kwargs):
        raise RuntimeError("db insert failed")

    monkeypatch.setattr(pipeline, "_replace_ticker_events", boom)

    def fake_record(*args, **kwargs):
        recorded_statuses.append(kwargs["status"])

    monkeypatch.setattr(pipeline, "_record_pipeline_run", fake_record)

    with pytest.raises(RuntimeError, match="db insert failed"):
        pipeline._write_filtered_results_to_db(filtered, "NVDA")

    assert fake_conn.rollbacks == 1
    assert fake_conn.commits == 1
    assert fake_conn.closed is True
    assert recorded_statuses == ["failed"]


def test_write_filtered_results_to_db_ignores_failed_status_record_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    filtered = tmp_path / "filtered.csv"
    filtered.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event,desc,https://example.com,1.0,1.0,id-1,[]\n",
        encoding="utf-8",
    )

    class FakeConn:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0
            self.closed = False

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

        def close(self) -> None:
            self.closed = True

    fake_conn = FakeConn()
    recorded_statuses: list[str] = []

    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_conn", lambda: fake_conn)
    monkeypatch.setattr(
        pipeline,
        "_replace_ticker_events",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db insert failed")),
    )

    def fake_record(*args, **kwargs):
        recorded_statuses.append(kwargs["status"])
        if kwargs["status"] == "failed":
            raise RuntimeError("record failed")

    monkeypatch.setattr(pipeline, "_record_pipeline_run", fake_record)

    with pytest.raises(RuntimeError, match="db insert failed"):
        pipeline._write_filtered_results_to_db(filtered, "NVDA")

    assert fake_conn.rollbacks == 1
    assert fake_conn.commits == 0
    assert fake_conn.closed is True
    assert recorded_statuses == ["failed"]


def test_download_and_upload_file_delegate_to_s3_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []

    class FakeS3:
        def download_file(self, bucket, key, dest):
            calls.append(("download", bucket, key, dest))

        def upload_file(self, source, bucket, key):
            calls.append(("upload", source, bucket, key))

    monkeypatch.setattr(pipeline, "_s3_client", lambda: FakeS3())
    dest = tmp_path / "nested" / "file.csv"
    src = tmp_path / "source.csv"
    src.write_text("x", encoding="utf-8")

    pipeline._download_file("bucket", "key.csv", dest)
    pipeline._upload_file(src, "bucket", "out.csv")

    assert dest.parent.exists() is True
    assert calls[0] == ("download", "bucket", "key.csv", str(dest))
    assert calls[1] == ("upload", str(src), "bucket", "out.csv")


def test_s3_client_uses_region_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []
    monkeypatch.setenv("AWS_REGION", "ca-central-1")
    monkeypatch.setattr(
        pipeline.boto3,
        "client",
        lambda service, region_name=None: calls.append((service, region_name)) or "client",
    )

    assert pipeline._s3_client() == "client"
    assert calls == [("s3", "ca-central-1")]


def test_s3_client_without_region_uses_default_client(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setattr(
        pipeline.boto3,
        "client",
        lambda service: calls.append(service) or "client",
    )

    assert pipeline._s3_client() == "client"
    assert calls == ["s3"]


def test_parse_args_reads_required_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "prog",
            "--ticker",
            "NVDA",
            "--bucket",
            "bucket",
            "--llm-model",
            "model",
            "--llm-api-key",
            "key",
            "--top-k-events",
            "9",
        ],
    )

    args = pipeline.parse_args()

    assert args.ticker == "NVDA"
    assert args.bucket == "bucket"
    assert args.llm_model == "model"
    assert args.top_k_events == 9


def test_run_pipeline_for_ticker_raises_system_exit_when_event_detector_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.endswith("core.event_detection"):
            raise ModuleNotFoundError("missing detector")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(SystemExit, match="Event pipeline dependency is missing"):
        pipeline.run_pipeline_for_ticker(
            ticker="NVDA",
            bucket="bucket",
            llm_api_key="key",
            llm_model="model",
        )


def test_run_pipeline_for_ticker_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    temp_root = tmp_path / "pipeline"
    uploaded = []
    written = []

    class FakeDetector:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            out_dir = Path(self.kwargs["results_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            raw_path = out_dir / "NVDA.csv"
            raw_path.write_text(
                "id,event_date,title\n"
                "e1,2026-01-01,Event 1\n"
                "e2,2026-01-02,Event 2\n",
                encoding="utf-8",
            )
            return None, [{"id": "e1"}, {"id": "e2"}]

    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeFilter:
        def __init__(self, llm, batch_size):
            self.batch_size = batch_size

        def run(self, events_df, start_date=None, end_date=None):
            return ["e2"]

    monkeypatch.setitem(sys.modules, "app.pipelines.core.event_detection", SimpleNamespace(EventDetector=FakeDetector))
    monkeypatch.setitem(
        sys.modules,
        "app.pipelines.core.llm",
        SimpleNamespace(
            ChatCompletionsLLM=FakeLLM,
            NewsLLMFilter=FakeFilter,
            load_events=lambda path: __import__("pandas").read_csv(path),
        ),
    )
    monkeypatch.setattr(pipeline.tempfile, "mkdtemp", lambda prefix="": str(temp_root))
    monkeypatch.setattr(
        pipeline,
        "_download_file",
        lambda bucket, key, dest: dest.parent.mkdir(parents=True, exist_ok=True) or dest.write_text("stub", encoding="utf-8"),
    )
    monkeypatch.setattr(pipeline, "_upload_file", lambda source, bucket, key: uploaded.append((Path(source).name, bucket, key)))
    monkeypatch.setattr(pipeline, "_write_filtered_results_to_db", lambda path, ticker: written.append((Path(path).name, ticker)) or 1)
    monkeypatch.setattr(pipeline, "_require_env", lambda name, current: current or f"{name.lower()}-value")
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    inserted = pipeline.run_pipeline_for_ticker(
        ticker="nvda",
        bucket="bucket",
        llm_api_key="key",
        llm_model="model",
        llm_batch_size=5,
    )

    assert inserted == 1
    assert uploaded[0] == ("NVDA.csv", "bucket", "events/raw/NVDA.csv")
    assert uploaded[1] == ("NVDA_event_news_llm_filtered.csv", "bucket", "events/filtered/NVDA_event_news_llm_filtered.csv")
    assert written == [("NVDA_event_news_llm_filtered.csv", "NVDA")]
    assert temp_root.exists() is False


def test_run_pipeline_for_ticker_raises_when_raw_output_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    temp_root = tmp_path / "pipeline_missing"

    class FakeDetector:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            return None, []

    monkeypatch.setitem(sys.modules, "app.pipelines.core.event_detection", SimpleNamespace(EventDetector=FakeDetector))
    monkeypatch.setitem(
        sys.modules,
        "app.pipelines.core.llm",
        SimpleNamespace(
            ChatCompletionsLLM=lambda **kwargs: None,
            NewsLLMFilter=lambda llm, batch_size: None,
            load_events=lambda path: None,
        ),
    )
    monkeypatch.setattr(pipeline.tempfile, "mkdtemp", lambda prefix="": str(temp_root))
    monkeypatch.setattr(
        pipeline,
        "_download_file",
        lambda bucket, key, dest: dest.parent.mkdir(parents=True, exist_ok=True) or dest.write_text("stub", encoding="utf-8"),
    )
    monkeypatch.setattr(pipeline, "_require_env", lambda name, current: current or "value")

    with pytest.raises(RuntimeError, match="Expected raw output was not created"):
        pipeline.run_pipeline_for_ticker(ticker="NVDA", bucket="bucket", llm_api_key="key", llm_model="model")


def test_run_pipeline_for_ticker_requires_llm_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "app.pipelines.core.event_detection", SimpleNamespace(EventDetector=lambda **kwargs: None))
    monkeypatch.setitem(
        sys.modules,
        "app.pipelines.core.llm",
        SimpleNamespace(
            ChatCompletionsLLM=lambda **kwargs: None,
            NewsLLMFilter=lambda llm, batch_size: None,
            load_events=lambda path: None,
        ),
    )

    def fake_require(name: str, current: str | None) -> str:
        if name == "LLM_API_KEY":
            raise ValueError("Missing required setting: LLM_API_KEY")
        return current or "value"

    monkeypatch.setattr(pipeline, "_require_env", fake_require)

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        pipeline.run_pipeline_for_ticker(
            ticker="NVDA",
            bucket="bucket",
            llm_api_key=None,
            llm_model="model",
        )


def test_main_passes_args_to_run_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    args = SimpleNamespace(
        ticker="NVDA",
        bucket="bucket-from-arg",
        stock_prefix="sp",
        market_prefix="mp",
        news_prefix="np",
        events_prefix="ep",
        filtered_prefix="fp",
        benchmark_ticker="^DJI",
        start_date="2026-01-01",
        end_date="2026-02-01",
        news_window_days=2,
        pen=4,
        window_left=3,
        window_right=3,
        top_k_events=25,
        llm_model="model",
        llm_base_url="http://llm",
        llm_api_key="key",
        llm_batch_size=30,
        llm_max_tokens=256,
        llm_temperature=0.0,
    )
    monkeypatch.setattr(pipeline, "parse_args", lambda: args)
    monkeypatch.setattr(pipeline, "_require_env", lambda name, current: current)
    monkeypatch.setattr(pipeline, "run_pipeline_for_ticker", lambda **kwargs: captured.update(kwargs))

    pipeline.main()

    assert captured["ticker"] == "NVDA"
    assert captured["bucket"] == "bucket-from-arg"
    assert captured["filtered_prefix"] == "fp"


def test_main_requires_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    args = argparse.Namespace(
        ticker="NVDA",
        bucket=None,
        stock_prefix="sp",
        market_prefix="mp",
        news_prefix="np",
        events_prefix="ep",
        filtered_prefix="fp",
        benchmark_ticker="^DJI",
        start_date=None,
        end_date=None,
        news_window_days=2,
        pen=4,
        window_left=3,
        window_right=3,
        top_k_events=25,
        llm_model="model",
        llm_base_url=None,
        llm_api_key="key",
        llm_batch_size=30,
        llm_max_tokens=256,
        llm_temperature=0.0,
    )
    monkeypatch.setattr(pipeline, "parse_args", lambda: args)
    monkeypatch.setattr(
        pipeline,
        "_require_env",
        lambda name, current: (_ for _ in ()).throw(ValueError("Missing required setting: PIPELINE_S3_BUCKET")),
    )

    with pytest.raises(ValueError, match="PIPELINE_S3_BUCKET"):
        pipeline.main()


def test_real_main_block_invokes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(pipeline, "main", lambda: calls.append("main"))

    source_lines = Path(pipeline.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 428 + textwrap.dedent("\n".join(source_lines[428:])) + "\n"
    code = compile(main_block, pipeline.__file__, "exec")
    globals_dict = dict(pipeline.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == ["main"]
