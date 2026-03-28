from types import SimpleNamespace
from pathlib import Path
import textwrap

import pandas as pd
import pytest

from app.pipelines.core import llm


def _make_events_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "a1",
                "event_date": pd.Timestamp("2026-01-01"),
                "published_utc": pd.Timestamp("2026-01-01T10:00:00"),
                "title": "t1",
                "description": "d1",
                "abs_car": 0.4,
            },
            {
                "id": "a2",
                "event_date": pd.Timestamp("2026-01-01"),
                "published_utc": pd.Timestamp("2026-01-01T12:00:00"),
                "title": "t2",
                "description": "d2",
                "abs_car": 1.1,
            },
            {
                "id": "b1",
                "event_date": pd.Timestamp("2026-01-02"),
                "published_utc": pd.Timestamp("2026-01-02T09:00:00"),
                "title": "t3",
                "description": "d3",
                "abs_car": 0.9,
            },
            {
                "id": "c1",
                "event_date": pd.Timestamp("2026-01-03"),
                "published_utc": pd.Timestamp("2026-01-03T09:00:00"),
                "title": "t4",
                "description": "d4",
                "abs_car": 0.2,
            },
        ]
    )


def test_extract_ids_supports_json_and_python_literal() -> None:
    filter_pipeline = llm.NewsLLMFilter(llm=lambda _prompt: [])
    assert filter_pipeline.extract_ids('prefix ["id1", "id2"] suffix') == ["id1", "id2"]
    assert filter_pipeline.extract_ids("noise ['id3', 'id4']") == ["id3", "id4"]
    assert filter_pipeline.extract_ids("no bracket") == []
    assert filter_pipeline.extract_ids("[123, 'id5']") == ["id5"]
    assert filter_pipeline.extract_ids("[not valid]") == []


def test_build_date_batches_keeps_same_day_together() -> None:
    df = _make_events_df()
    filter_pipeline = llm.NewsLLMFilter(llm=lambda _prompt: [], batch_size=2)

    batches = filter_pipeline.build_date_batches(df)
    assert len(batches) == 2
    assert list(batches[0]["id"]) == ["a1", "a2"]
    assert list(batches[1]["id"]) == ["b1", "c1"]


def test_keep_one_per_day_prefers_highest_abs_car() -> None:
    df = _make_events_df()
    filter_pipeline = llm.NewsLLMFilter(llm=lambda _prompt: [])

    kept = filter_pipeline.keep_one_per_day(df, ["a1", "a2", "b1"])
    assert set(kept) == {"a2", "b1"}


def test_run_filters_dates_and_skips_failed_batches(capsys: pytest.CaptureFixture[str]) -> None:
    df = _make_events_df()

    calls = {"count": 0}

    def fake_llm(_prompt: str):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("temporary llm error")
        return [{"generated_text": "['a2', 'b1', 'missing']"}]

    filter_pipeline = llm.NewsLLMFilter(llm=fake_llm, batch_size=1)
    selected = filter_pipeline.run(
        df,
        start_date="2026-01-01",
        end_date="2026-01-02T23:59:59",
    )

    assert set(selected) == {"a2", "b1"}
    output = capsys.readouterr().out
    assert "Retrying failed batch 2/2 (attempt 2/3)" in output
    assert "LLM filtering skipped" not in output


def test_call_llm_with_retries_retries_up_to_three_times() -> None:
    calls = {"count": 0}

    def fake_llm(_prompt: str):
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError(f"temporary-{calls['count']}")
        return [{"generated_text": "['a1']"}]

    filter_pipeline = llm.NewsLLMFilter(llm=fake_llm, max_retries=3)

    output = filter_pipeline.call_llm_with_retries("prompt", 1, 2)

    assert output == "['a1']"
    assert calls["count"] == 3


def test_call_llm_with_retries_raises_after_last_attempt() -> None:
    calls = {"count": 0}

    def fake_llm(_prompt: str):
        calls["count"] += 1
        raise RuntimeError("still failing")

    filter_pipeline = llm.NewsLLMFilter(llm=fake_llm, max_retries=3)

    with pytest.raises(RuntimeError, match="still failing"):
        filter_pipeline.call_llm_with_retries("prompt", 1, 1)

    assert calls["count"] == 3


def test_run_skips_failed_batch_after_all_retries(capsys: pytest.CaptureFixture[str]) -> None:
    df = _make_events_df().head(2)

    def always_fail(_prompt: str):
        raise RuntimeError("persistent llm error")

    filter_pipeline = llm.NewsLLMFilter(llm=always_fail, batch_size=10, max_retries=3)

    selected = filter_pipeline.run(df)

    assert selected == []
    output = capsys.readouterr().out
    assert "Retrying failed batch 1/1 (attempt 2/3)" in output
    assert "Retrying failed batch 1/1 (attempt 3/3)" in output
    assert "Skipping failed batch 1/1: persistent llm error" in output
    assert "LLM filtering skipped 1 failed batch(es)." in output


def test_load_events_validates_required_columns(tmp_path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("id,event_date\n1,2026-01-01\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required columns"):
        llm.load_events(csv_path)


def test_load_events_drops_invalid_rows_and_sorts(tmp_path) -> None:
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "id,event_date,published_utc,title,description,abs_car\n"
        "x2,2026-01-03,2026-01-03T10:00:00Z,t,d,1\n"
        "x1,2026-01-01,not-a-date,t,d,1\n"
        "x3,2026-01-02,2026-01-02T10:00:00Z,t,d,1\n",
        encoding="utf-8",
    )

    df = llm.load_events(csv_path)
    assert list(df["id"]) == ["x3", "x2"]


def test_load_events_drops_missing_id_values(tmp_path) -> None:
    csv_path = tmp_path / "events.csv"
    csv_path.write_text(
        "id,event_date,published_utc,title,description,abs_car\n"
        ",2026-01-02,2026-01-02T10:00:00Z,t,d,1\n"
        "x1,2026-01-01,2026-01-01T10:00:00Z,t,d,1\n",
        encoding="utf-8",
    )

    df = llm.load_events(csv_path)

    assert list(df["id"]) == ["x1"]


def test_build_llm_from_args_uses_env_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return "client"

    monkeypatch.setenv("LLM_API_KEY", "from-env")
    monkeypatch.setattr(llm, "ChatCompletionsLLM", lambda **kwargs: fake_chat(**kwargs))
    args = SimpleNamespace(
        api_key=None,
        model="m1",
        base_url="https://example.com",
        max_tokens=99,
        temperature=0.3,
    )

    built = llm.build_llm_from_args(args)
    assert built == "client"
    assert captured == {
        "api_key": "from-env",
        "model": "m1",
        "base_url": "https://example.com",
        "max_tokens": 99,
        "temperature": 0.3,
    }


def test_build_llm_from_args_raises_without_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    args = SimpleNamespace(api_key=None, model="m", base_url=None, max_tokens=1, temperature=0.0)

    with pytest.raises(ValueError, match="Missing API key"):
        llm.build_llm_from_args(args)


def test_chat_completions_llm_uses_base_url_and_returns_generated_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: captured.update({"request_kwargs": kwargs})
                    or SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))])
                )
            )

    monkeypatch.setattr(llm, "OpenAI", FakeClient)
    model = llm.ChatCompletionsLLM(api_key="k", model="m", base_url="http://x", max_tokens=12, temperature=0.2)
    out = model("prompt")

    assert out == [{"generated_text": "hello"}]
    assert captured["client_kwargs"] == {"api_key": "k", "base_url": "http://x"}
    assert captured["request_kwargs"]["model"] == "m"


def test_format_news_block_and_parse_args(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _make_events_df().head(1)
    filter_pipeline = llm.NewsLLMFilter(llm=lambda _prompt: [])
    block = filter_pipeline.format_news_block(df)
    assert "ID: a1" in block
    assert "Title: t1" in block

    monkeypatch.setattr(
        "sys.argv",
        ["prog", "events.csv", "--output-dir", "out", "--batch-size", "7", "--start-date", "2026-01-01"],
    )
    args = llm.parse_args()
    assert args.input_path == "events.csv"
    assert args.output_dir == "out"
    assert args.batch_size == 7


def test_resolve_default_output_uses_input_basename() -> None:
    output = llm.resolve_default_output("/tmp/NVDA_events.csv", "/tmp/out")
    assert output.endswith("NVDA_events.csv")


def test_main_filters_and_writes_output(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    input_path = tmp_path / "events.csv"
    output_dir = tmp_path / "out"
    df = pd.DataFrame(
        [
            {"id": "a1", "event_date": pd.Timestamp("2026-01-02"), "published_utc": pd.Timestamp("2026-01-02"), "title": "t1", "description": "d1", "abs_car": 1.0},
            {"id": "a2", "event_date": pd.Timestamp("2026-01-01"), "published_utc": pd.Timestamp("2026-01-01"), "title": "t2", "description": "d2", "abs_car": 2.0},
        ]
    )
    printed = []
    monkeypatch.setattr(
        llm,
        "parse_args",
        lambda: SimpleNamespace(
            input_path=str(input_path),
            output_dir=str(output_dir),
            api_key="key",
            model="m",
            base_url=None,
            max_tokens=10,
            temperature=0.0,
            batch_size=2,
            start_date=None,
            end_date=None,
        ),
    )
    monkeypatch.setattr(llm, "load_events", lambda path: df)
    monkeypatch.setattr(llm, "build_llm_from_args", lambda args: "fake-llm")

    class FakeFilter:
        def __init__(self, llm_obj, batch_size):
            assert llm_obj == "fake-llm"
            assert batch_size == 2

        def run(self, df_arg, start_date=None, end_date=None):
            return ["a1"]

    monkeypatch.setattr(llm, "NewsLLMFilter", FakeFilter)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    llm.main()

    saved = pd.read_csv(output_dir / "events.csv")
    assert list(saved["id"]) == ["a1"]
    assert any("Selected news: 1" in line for line in printed)


def test_main_writes_empty_filtered_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    input_path = tmp_path / "events.csv"
    output_dir = tmp_path / "out"
    df = pd.DataFrame(
        [
            {
                "id": "a1",
                "event_date": pd.Timestamp("2026-01-02"),
                "published_utc": pd.Timestamp("2026-01-02"),
                "title": "t1",
                "description": "d1",
                "abs_car": 1.0,
            }
        ]
    )
    printed = []
    monkeypatch.setattr(
        llm,
        "parse_args",
        lambda: SimpleNamespace(
            input_path=str(input_path),
            output_dir=str(output_dir),
            api_key="key",
            model="m",
            base_url=None,
            max_tokens=10,
            temperature=0.0,
            batch_size=2,
            start_date=None,
            end_date=None,
        ),
    )
    monkeypatch.setattr(llm, "load_events", lambda path: df)
    monkeypatch.setattr(llm, "build_llm_from_args", lambda args: "fake-llm")

    class FakeFilter:
        def __init__(self, llm_obj, batch_size):
            pass

        def run(self, df_arg, start_date=None, end_date=None):
            return []

    monkeypatch.setattr(llm, "NewsLLMFilter", FakeFilter)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    llm.main()

    saved = pd.read_csv(output_dir / "events.csv")
    assert saved.empty
    assert any("Selected news: 0" in line for line in printed)


def test_real_main_block_invokes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(llm, "main", lambda: calls.append("main"))

    source_lines = Path(llm.__file__).read_text(encoding="utf-8").splitlines()
    main_index = next(i for i, line in enumerate(source_lines) if line.startswith('if __name__ == "__main__":'))
    main_block = "\n" * main_index + textwrap.dedent("\n".join(source_lines[main_index:])) + "\n"
    code = compile(main_block, llm.__file__, "exec")
    globals_dict = dict(llm.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert calls == ["main"]
