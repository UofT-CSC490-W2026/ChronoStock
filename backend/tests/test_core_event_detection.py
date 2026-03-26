import pandas as pd
import pytest
import textwrap
from pathlib import Path

from app.pipelines.core import event_detection
from app.pipelines.core.event_detection import EventDetector


def _build_detector(tmp_path, **kwargs) -> EventDetector:
    return EventDetector(
        ticker="NVDA",
        stock_path=str(tmp_path / "stock.csv"),
        market_path=str(tmp_path / "market.csv"),
        news_path=str(tmp_path / "news.csv"),
        results_dir=str(tmp_path / "results"),
        **kwargs,
    )


def test_init_raises_when_start_after_end(tmp_path) -> None:
    with pytest.raises(ValueError, match="start_time must be earlier"):
        _build_detector(tmp_path, start_time="2026-01-05", end_time="2026-01-01")


def test_normalize_time_arg_rejects_invalid_value(tmp_path) -> None:
    detector = _build_detector(tmp_path)
    with pytest.raises(ValueError, match="Invalid start_time"):
        detector._normalize_time_arg("not-a-date", "start_time")


def test_normalize_time_arg_strips_timezone(tmp_path) -> None:
    detector = _build_detector(tmp_path)
    out = detector._normalize_time_arg("2026-01-01T00:00:00Z", "start_time")
    assert out == pd.Timestamp("2026-01-01 00:00:00")


def test_get_detection_df_applies_time_range_and_raises_if_empty(tmp_path) -> None:
    detector = _build_detector(tmp_path, start_time="2026-01-02", end_time="2026-01-03")
    detector.price_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "stock_return": [0.1, 0.2, 0.3],
            "volatility": [0.1, 0.2, 0.3],
        }
    )
    filtered = detector._get_detection_df()
    assert list(filtered["Date"]) == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")]

    detector.start_time = pd.Timestamp("2030-01-01")
    detector.end_time = pd.Timestamp("2030-01-02")
    with pytest.raises(ValueError, match="No price data available"):
        detector._get_detection_df()


def test_detect_change_points_maps_to_original_index(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    detector = _build_detector(tmp_path)
    detector.price_df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "stock_return": [0.1, 0.2, 0.3],
            "volatility": [0.2, 0.3, 0.4],
        },
        index=[10, 11, 12],
    )
    monkeypatch.setattr(detector, "run_pelt", lambda series: [1, 5])

    cp_returns, cp_vol = detector.detect_change_points()
    assert cp_returns == [11]
    assert cp_vol == [11]


def test_build_windows_and_merge_windows(tmp_path) -> None:
    detector = _build_detector(tmp_path, window_left=2, window_right=2)
    detector.price_df = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=10)})

    windows = detector.build_windows([1, 3, 8])
    assert windows == [(0, 3), (1, 5), (6, 9)]
    assert detector.merge_windows(windows) == [[0, 5], [6, 9]]
    assert detector.merge_windows([]) == []


def test_run_pelt_removes_final_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    detector = _build_detector(tmp_path)

    class FakePelt:
        def fit(self, values):
            return self

        def predict(self, pen):
            return [2, 5]

    monkeypatch.setattr("app.pipelines.core.event_detection.rpt.Pelt", lambda model: FakePelt())
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert detector.run_pelt(series) == [2]


def test_score_events_skips_failed_car_and_sorts(tmp_path) -> None:
    detector = _build_detector(tmp_path)
    detector.price_df = pd.DataFrame({"Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])})

    class FakeCar:
        def compute_car(self, event_date, window_before, window_after):
            if pd.Timestamp(event_date) == pd.Timestamp("2026-01-01"):
                raise RuntimeError("fail one")
            if pd.Timestamp(event_date) == pd.Timestamp("2026-01-02"):
                return -1.5, None
            return 0.4, None

    detector.car_model = FakeCar()
    events_df = detector.score_events([(0, 0), (1, 1), (2, 2)])
    assert list(events_df["event_date"]) == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")]
    assert list(events_df["abs_car"]) == [1.5, 0.4]


def test_attach_news_empty_and_non_empty(tmp_path) -> None:
    detector = _build_detector(tmp_path, news_window_days=1)
    detector.news_df = pd.DataFrame(
        {
            "published_utc": pd.to_datetime(["2026-01-02", "2026-01-10"]),
            "title": ["near", "far"],
        }
    )

    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2026-01-01"]),
            "start_idx": [0],
            "end_idx": [1],
            "car": [0.2],
            "abs_car": [0.2],
        }
    )
    attached = detector.attach_news(events_df)
    assert len(attached) == 1
    assert attached.iloc[0]["title"] == "near"

    detector.news_df = pd.DataFrame({"published_utc": pd.to_datetime(["2027-01-01"]), "title": ["none"]})
    empty_attached = detector.attach_news(events_df)
    assert list(empty_attached.columns) == list(events_df.columns) + list(detector.news_df.columns)
    assert empty_attached.empty


def test_score_events_returns_empty_df_when_all_car_calls_fail(tmp_path) -> None:
    detector = _build_detector(tmp_path)
    detector.price_df = pd.DataFrame({"Date": pd.to_datetime(["2026-01-01"])})

    class FakeCar:
        def compute_car(self, event_date, window_before, window_after):
            raise RuntimeError("always fail")

    detector.car_model = FakeCar()
    events_df = detector.score_events([(0, 0)])
    assert events_df.empty
    assert list(events_df.columns) == ["event_date", "start_idx", "end_idx", "car", "abs_car"]


def test_score_events_skips_center_index_out_of_bounds(tmp_path) -> None:
    detector = _build_detector(tmp_path)
    detector.price_df = pd.DataFrame({"Date": pd.to_datetime(["2026-01-01"])})

    class FakeCar:
        def compute_car(self, event_date, window_before, window_after):
            return 0.5, None

    detector.car_model = FakeCar()
    events_df = detector.score_events([(2, 2)])
    assert events_df.empty


def test_run_sorts_empty_results_without_error(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    detector = _build_detector(tmp_path, top_k_events=1)
    detector.price_df = pd.DataFrame({"Date": pd.to_datetime(["2026-01-01"])})
    monkeypatch.setattr(detector, "load_data", lambda: None)
    monkeypatch.setattr(detector, "setup_car", lambda: None)
    monkeypatch.setattr(detector, "detect_change_points", lambda: ([], []))
    monkeypatch.setattr(detector, "build_windows", lambda cp: [])
    monkeypatch.setattr(detector, "merge_windows", lambda windows: [])
    monkeypatch.setattr(detector, "score_events", lambda windows: pd.DataFrame(columns=["event_date", "start_idx", "end_idx", "car", "abs_car"]))
    monkeypatch.setattr(detector, "attach_news", lambda events: pd.DataFrame())

    out_capture = {}

    def fake_to_csv(self, path, index=False):
        out_capture["path"] = path
        out_capture["index"] = index

    monkeypatch.setattr(pd.DataFrame, "to_csv", fake_to_csv, raising=False)

    out_events, out_results = detector.run()
    assert out_events.empty
    assert out_results.empty
    assert out_capture["path"].endswith("NVDA.csv")


def test_run_orchestrates_pipeline_and_writes_output(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    detector = _build_detector(tmp_path, top_k_events=1)

    price_df = pd.DataFrame({"Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"])})
    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2026-01-03", "2026-01-01"]),
            "start_idx": [0, 1],
            "end_idx": [1, 2],
            "car": [0.5, 1.0],
            "abs_car": [0.5, 1.0],
        }
    )
    results_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2026-01-03", "2026-01-01"]),
            "title": ["b", "a"],
        }
    )

    monkeypatch.setattr(detector, "load_data", lambda: None)
    monkeypatch.setattr(detector, "setup_car", lambda: None)
    monkeypatch.setattr(detector, "detect_change_points", lambda: ([1], [2]))
    monkeypatch.setattr(detector, "build_windows", lambda cp: [(cp[0] - 1, cp[0])])
    monkeypatch.setattr(detector, "merge_windows", lambda windows: windows)
    monkeypatch.setattr(detector, "score_events", lambda windows: events_df.copy())
    monkeypatch.setattr(detector, "attach_news", lambda events: results_df.copy())
    detector.price_df = price_df

    out_capture = {}

    def fake_to_csv(self, path, index=False):
        out_capture["path"] = path
        out_capture["index"] = index
        out_capture["rows"] = len(self)

    monkeypatch.setattr(pd.DataFrame, "to_csv", fake_to_csv, raising=False)

    out_events, out_results = detector.run()
    assert len(out_events) == 1
    assert out_events.iloc[0]["event_date"] == pd.Timestamp("2026-01-03")
    assert out_results.iloc[0]["event_date"] == pd.Timestamp("2026-01-01")
    assert out_capture["path"].endswith("NVDA.csv")
    assert out_capture["index"] is False


def test_load_data_reads_and_normalizes_price_and_news(tmp_path) -> None:
    detector = _build_detector(tmp_path)
    pd.DataFrame(
        {
            "Date": pd.date_range("2026-01-01", periods=12, tz="UTC"),
            "Close": [100 + i for i in range(12)],
        }
    ).to_csv(tmp_path / "stock.csv", index=False)
    pd.DataFrame(
        {
            "Date": pd.date_range("2026-01-01", periods=12, tz="UTC"),
            "Close": [200 + i for i in range(12)],
        }
    ).to_csv(tmp_path / "market.csv", index=False)
    pd.DataFrame(
        {
            "published_utc": ["2026-01-05T00:00:00Z", "bad-date"],
            "title": ["good", "bad"],
        }
    ).to_csv(tmp_path / "news.csv", index=False)

    detector.load_data()

    assert not detector.price_df.empty
    assert list(detector.price_df.columns) == ["Date", "stock_price", "market_price", "stock_return", "market_return", "volatility"]
    assert len(detector.news_df) == 1
    assert str(detector.news_df.iloc[0]["published_utc"]) == "2026-01-05 00:00:00"


def test_setup_car_calls_model_methods_in_order(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    detector = _build_detector(tmp_path)
    calls = []

    class FakeCAR:
        def __init__(self, stock_path, market_path):
            calls.append(("init", stock_path, market_path))

        def load_data(self):
            calls.append(("load_data",))

        def fit_market_model(self):
            calls.append(("fit_market_model",))

        def compute_abnormal_returns(self):
            calls.append(("compute_abnormal_returns",))

    monkeypatch.setattr("app.pipelines.core.event_detection.CARCalculator", FakeCAR)

    detector.setup_car()

    assert calls[0][0] == "init"
    assert calls[1:] == [("load_data",), ("fit_market_model",), ("compute_abnormal_returns",)]


def test_attach_news_returns_all_matches_for_window(tmp_path) -> None:
    detector = _build_detector(tmp_path, news_window_days=2)
    detector.news_df = pd.DataFrame(
        {
            "published_utc": pd.to_datetime(["2026-01-01", "2026-01-03", "2026-01-07"]),
            "title": ["before", "during", "outside"],
        }
    )
    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2026-01-03"]),
            "start_idx": [0],
            "end_idx": [1],
            "car": [0.4],
            "abs_car": [0.4],
        }
    )

    attached = detector.attach_news(events_df)

    assert list(attached["title"]) == ["before", "during"]


def test_real_main_block_executes_file_lines(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    created = {}

    class FakeDetector:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def run(self):
            return "events", "news"

    monkeypatch.setattr(event_detection, "EventDetector", FakeDetector)
    printed = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    source_lines = Path(event_detection.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 329 + textwrap.dedent("\n".join(source_lines[329:])) + "\n"
    code = compile(main_block, event_detection.__file__, "exec")
    globals_dict = dict(event_detection.__dict__)
    globals_dict["__name__"] = "__main__"
    exec(code, globals_dict, {})

    assert created["ticker"] == "NVDA"
    assert created["top_k_events"] == 25
    assert printed[-1] == "events"
