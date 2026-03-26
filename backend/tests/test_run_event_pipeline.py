import argparse
import builtins
import json
from pathlib import Path
import textwrap
import uuid

import pytest

from app.pipelines import run_event_pipeline as pipeline


def _workspace_dir(name: str) -> Path:
    path = Path.cwd() / ".pytest_tmp" / f"{name}_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_parse_args_reads_cli_values(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["prog", "--input-csv", "a.csv", "--input-csv", "b.csv", "--demodata-dir", "demo", "--ticker", "nvda"],
    )
    args = pipeline.parse_args()
    assert args.input_csv == ["a.csv", "b.csv"]
    assert args.demodata_dir == "demo"
    assert args.ticker == "nvda"


def test_main_raises_when_no_inputs(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "parse_args", lambda: argparse.Namespace(input_csv=[], demodata_dir=None, ticker=None))
    monkeypatch.setattr(pipeline, "init_db", lambda: None)

    with pytest.raises(SystemExit, match="No input files provided"):
        pipeline.main()


def test_main_raises_when_input_file_missing(monkeypatch) -> None:
    missing = _workspace_dir("run_event_pipeline_missing") / "missing.csv"
    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: argparse.Namespace(input_csv=[str(missing)], demodata_dir=None, ticker=None),
    )
    monkeypatch.setattr(pipeline, "init_db", lambda: None)

    with pytest.raises(SystemExit, match="Input file not found"):
        pipeline.main()


def test_main_raises_when_no_valid_rows(monkeypatch) -> None:
    csv_path = _workspace_dir("run_event_pipeline_no_rows") / "events.csv"
    csv_path.write_text("ticker,event_date,title\n", encoding="utf-8")
    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: argparse.Namespace(input_csv=[str(csv_path)], demodata_dir=None, ticker=None),
    )
    monkeypatch.setattr(pipeline, "init_db", lambda: None)

    with pytest.raises(SystemExit, match="No valid event rows found"):
        pipeline.main()


def test_main_imports_unique_files_and_records_success(monkeypatch) -> None:
    csv_path = _workspace_dir("run_event_pipeline_success") / "events.csv"
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event A,desc,https://example.com/a,1.0,1.0,id-1,[]\n",
        encoding="utf-8",
    )

    class FakeConn:
        def __init__(self) -> None:
            self.committed = False
            self.closed = False

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            raise AssertionError("rollback should not be called")

        def close(self) -> None:
            self.closed = True

    conn = FakeConn()
    inserted = []
    recorded = []
    printed = []

    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: argparse.Namespace(input_csv=[str(csv_path), str(csv_path)], demodata_dir=None, ticker=None),
    )
    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_conn", lambda: conn)
    monkeypatch.setattr(
        pipeline,
        "_replace_ticker_events",
        lambda conn_arg, ticker, records, pipeline_run_at: inserted.append((ticker, len(records))) or len(records),
    )
    monkeypatch.setattr(
        pipeline,
        "_record_pipeline_run",
        lambda conn_arg, run_id, status, started_at, completed_at, details: recorded.append(
            {"status": status, "details": json.loads(details)}
        ),
    )
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    pipeline.main()

    assert inserted == [("NVDA", 1)]
    assert recorded == [{"status": "completed", "details": {"tickers": {"NVDA": 1}}}]
    assert conn.committed is True
    assert conn.closed is True
    assert any("Imported events for 1 ticker" in line for line in printed)


def test_main_records_failed_run_and_reraises(monkeypatch) -> None:
    csv_path = _workspace_dir("run_event_pipeline_failure") / "events.csv"
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event A,desc,https://example.com/a,1.0,1.0,id-1,[]\n",
        encoding="utf-8",
    )

    class FakeConn:
        def __init__(self) -> None:
            self.rollbacks = 0
            self.commits = 0
            self.closed = False

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

        def close(self) -> None:
            self.closed = True

    conn = FakeConn()
    statuses = []

    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: argparse.Namespace(input_csv=[str(csv_path)], demodata_dir=None, ticker=None),
    )
    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_conn", lambda: conn)

    def fail_replace(conn_arg, ticker, records, pipeline_run_at):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(pipeline, "_replace_ticker_events", fail_replace)
    monkeypatch.setattr(
        pipeline,
        "_record_pipeline_run",
        lambda conn_arg, run_id, status, started_at, completed_at, details: statuses.append(status),
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        pipeline.main()

    assert statuses == ["failed"]
    assert conn.rollbacks == 1
    assert conn.commits == 1
    assert conn.closed is True


def test_main_ignores_failed_pipeline_run_record_error(monkeypatch) -> None:
    csv_path = _workspace_dir("run_event_pipeline_failure_record") / "events.csv"
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event A,desc,https://example.com/a,1.0,1.0,id-1,[]\n",
        encoding="utf-8",
    )

    class FakeConn:
        def __init__(self) -> None:
            self.rollbacks = 0
            self.commits = 0
            self.closed = False

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

        def close(self) -> None:
            self.closed = True

    conn = FakeConn()
    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: argparse.Namespace(input_csv=[str(csv_path)], demodata_dir=None, ticker=None),
    )
    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_conn", lambda: conn)
    monkeypatch.setattr(
        pipeline,
        "_replace_ticker_events",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("insert failed")),
    )
    monkeypatch.setattr(
        pipeline,
        "_record_pipeline_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("record failed")),
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        pipeline.main()

    assert conn.rollbacks == 1
    assert conn.commits == 0
    assert conn.closed is True


def test_parse_sentiment_falls_back_when_insight_sentiment_invalid() -> None:
    row = {
        "ticker": "NVDA",
        "insights": '[{"ticker":"NVDA","sentiment":"unknown","sentiment_reasoning":"x"}]',
        "car": "1.5",
    }
    assert pipeline._parse_sentiment(row) == ("positive", None)


def test_parse_sentiment_returns_matching_valid_sentiment() -> None:
    row = {
        "ticker": "NVDA",
        "insights": '[{"ticker":"NVDA","sentiment":"negative","sentiment_reasoning":"miss"}]',
        "car": "1.5",
    }
    assert pipeline._parse_sentiment(row) == ("negative", "miss")


def test_parse_sentiment_handles_non_matching_entries_and_type_error() -> None:
    row = {
        "ticker": "NVDA",
        "insights": '[{"ticker":"AAPL","sentiment":"positive"},{"ticker":"NVDA","sentiment":"unknown"}]',
        "car": "-1.0",
    }
    assert pipeline._parse_sentiment(row) == ("negative", None)

    row = {"ticker": "NVDA", "insights": '{"not":"a list"}', "car": "0"}
    assert pipeline._parse_sentiment(row) == ("neutral", None)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.marketwatch.com/story/x", "MarketWatch"),
        ("https://www.benzinga.com/news/1", "Benzinga"),
        ("https://www.fool.com/investing/1", "Motley Fool"),
        ("https://www.globenewswire.com/news-release/1", "GlobeNewsWire"),
        ("https://example.com/x", "News"),
    ],
)
def test_source_from_url_maps_known_sources(url: str, expected: str) -> None:
    assert pipeline._source_from_url(url) == expected


def test_load_filtered_csv_sets_invalid_car_values_to_none(tmp_path) -> None:
    csv_path = _workspace_dir("run_event_pipeline_invalid_car") / "events.csv"
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event A,desc,https://example.com/a,bad,bad,id-1,[]\n",
        encoding="utf-8",
    )

    rows = pipeline._load_filtered_csv(csv_path, default_ticker="NVDA")
    assert rows[0]["car"] is None
    assert rows[0]["abs_car"] is None


def test_load_filtered_csv_skips_missing_required_fields(tmp_path) -> None:
    csv_path = _workspace_dir("run_event_pipeline_missing_fields") / "events.csv"
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,,desc,https://example.com/a,1.0,1.0,id-1,[]\n"
        ",2026-01-01,Event B,desc,https://example.com/b,1.0,1.0,id-2,[]\n",
        encoding="utf-8",
    )

    assert pipeline._load_filtered_csv(csv_path, default_ticker=None) == []


def test_replace_ticker_events_and_record_pipeline_run_round_trip() -> None:
    import sqlite3

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

    inserted = pipeline._replace_ticker_events(
        conn,
        "NVDA",
        [
            {
                "ticker": "NVDA",
                "event_id": "e1",
                "event_date": "2026-01-01",
                "published_utc": None,
                "title": "Event A",
                "summary": "desc",
                "sentiment": "positive",
                "sentiment_reasoning": None,
                "source": "News",
                "url": "https://example.com/a",
                "car": 1.0,
                "abs_car": 1.0,
            }
        ],
        "2026-01-02T00:00:00+00:00",
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

    event_row = conn.execute("SELECT ticker, event_id FROM stock_events").fetchone()
    run_row = conn.execute("SELECT pipeline_name, status FROM pipeline_runs").fetchone()

    assert inserted == 1
    assert event_row == ("NVDA", "e1")
    assert run_row == ("event_backfill", "completed")


def test_main_loads_from_demodata_dir(monkeypatch) -> None:
    data_dir = _workspace_dir("run_event_pipeline_demodata")
    csv_path = data_dir / "NVDA_event_news_llm_filtered.csv"
    csv_path.write_text(
        "ticker,event_date,title,description,url,car,abs_car,id,insights\n"
        "NVDA,2026-01-01,Event A,desc,https://example.com/a,1.0,1.0,id-1,[]\n",
        encoding="utf-8",
    )

    class FakeConn:
        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            raise AssertionError("rollback should not be called")

        def close(self) -> None:
            pass

    inserted = []
    monkeypatch.setattr(
        pipeline,
        "parse_args",
        lambda: argparse.Namespace(input_csv=[], demodata_dir=str(data_dir), ticker=None),
    )
    monkeypatch.setattr(pipeline, "init_db", lambda: None)
    monkeypatch.setattr(pipeline, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(
        pipeline,
        "_replace_ticker_events",
        lambda conn_arg, ticker, records, pipeline_run_at: inserted.append((ticker, len(records))) or len(records),
    )
    monkeypatch.setattr(pipeline, "_record_pipeline_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: None)

    pipeline.main()
    assert inserted == [("NVDA", 1)]


def test_real_main_block_invokes_main(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(pipeline, "main", lambda: calls.append("main"))

    source_lines = Path(pipeline.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 245 + textwrap.dedent("\n".join(source_lines[245:])) + "\n"
    code = compile(main_block, pipeline.__file__, "exec")
    globals_dict = dict(pipeline.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == ["main"]
