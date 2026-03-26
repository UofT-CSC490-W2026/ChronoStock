from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.pipelines.core.event_detection import EventDetector


@pytest.fixture
def detector(tmp_path):
    return EventDetector(
        ticker="NVDA",
        stock_path="stock.csv",
        market_path="market.csv",
        news_path="news.csv",
        results_dir=str(tmp_path),
    )


@pytest.fixture
def price_df():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    return pd.DataFrame(
        {
            "Date": dates,
            "stock_return": [0.02, -0.03, 0.01, 0.04, -0.02, 0.03],
            "volatility": [0.2, 0.3, 0.25, 0.5, 0.45, 0.4],
        }
    )


def make_detector(tmp_path, **kwargs):
    defaults = {
        "ticker": "NVDA",
        "stock_path": "stock.csv",
        "market_path": "market.csv",
        "news_path": "news.csv",
        "results_dir": str(tmp_path),
    }
    defaults.update(kwargs)
    return EventDetector(**defaults)


# Positive test: None is an allowed optional time input.
def test_normalize_time_arg_returns_none_for_none(detector):
    assert detector._normalize_time_arg(None, "start_time") is None


# Negative test: malformed date input should be rejected clearly.
def test_normalize_time_arg_rejects_invalid_value(detector):
    with pytest.raises(ValueError, match="Invalid start_time"):
        detector._normalize_time_arg("not-a-date", "start_time")


# Positive test: timezone-aware inputs are normalized into naive timestamps.
def test_normalize_time_arg_removes_timezone(detector):
    normalized = detector._normalize_time_arg("2024-01-01T12:00:00Z", "start_time")
    assert normalized.tzinfo is None
    assert normalized == pd.Timestamp("2024-01-01 12:00:00")


# Negative test: reversed time bounds should fail fast during initialization.
def test_init_rejects_start_time_after_end_time(tmp_path):
    with pytest.raises(ValueError, match="start_time must be earlier"):
        make_detector(tmp_path, start_time="2024-02-01", end_time="2024-01-01")


# Positive test: valid date filters should keep only rows inside the requested range.
def test_get_detection_df_filters_by_date_range(tmp_path, price_df):
    detector = make_detector(tmp_path, start_time="2024-01-02", end_time="2024-01-04")
    detector.price_df = price_df

    filtered = detector._get_detection_df()

    expected_dates = list(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))
    assert filtered["Date"].tolist() == expected_dates


# Negative test: filtering to an empty time range should raise a clear error.
def test_get_detection_df_raises_for_empty_range(tmp_path, price_df):
    detector = make_detector(tmp_path, start_time="2025-01-01", end_time="2025-01-03")
    detector.price_df = price_df

    with pytest.raises(ValueError, match="No price data available"):
        detector._get_detection_df()


# Positive test: event windows should be clamped to valid dataset boundaries.
def test_build_windows_clamps_to_dataset_bounds(tmp_path, price_df):
    detector = make_detector(tmp_path, window_left=2, window_right=2)
    detector.price_df = price_df

    windows = detector.build_windows([0, 5])

    assert windows == [(0, 2), (3, 5)]


# Negative test: empty input should be handled gracefully without crashing.
def test_merge_windows_returns_empty_for_empty_input(detector):
    assert detector.merge_windows([]) == []


# Positive test: overlapping windows should merge into combined ranges.
def test_merge_windows_merges_overlapping_ranges(detector):
    merged = detector.merge_windows([(1, 4), (3, 6), (8, 10)])
    assert merged == [[1, 6], [8, 10]]


# Negative test: invalid changepoint indices should be ignored safely.
def test_detect_change_points_ignores_out_of_range_indices(detector, price_df):
    detector.price_df = price_df

    with patch.object(detector, "run_pelt", side_effect=[[1, 99, -1], [0, 2]]):
        cp_returns, cp_vol = detector.detect_change_points()

    assert cp_returns == [1]
    assert cp_vol == [0, 2]


# Negative test: a CAR computation failure should be skipped while valid events remain ranked.
def test_score_events_skips_failures_and_sorts_by_absolute_car(tmp_path):
    detector = make_detector(tmp_path)
    detector.price_df = pd.DataFrame(
        {"Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])}
    )
    detector.car_model = MagicMock()

    def compute_car_side_effect(event_date, window_before, window_after):
        event_date = pd.Timestamp(event_date)
        if event_date == pd.Timestamp("2024-01-03"):
            raise ValueError("synthetic CAR failure")
        if event_date == pd.Timestamp("2024-01-02"):
            return -1.5, None
        return 0.8, None

    detector.car_model.compute_car.side_effect = compute_car_side_effect

    events_df = detector.score_events([(0, 2), (1, 3), (3, 4)])

    assert events_df["event_date"].tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04")]
    assert events_df["abs_car"].tolist() == [1.5, 0.8]


# Negative test: if all CAR calculations fail, the method should return an empty result safely.
def test_score_events_returns_empty_dataframe_when_all_car_calls_fail(tmp_path):
    detector = make_detector(tmp_path)
    detector.price_df = pd.DataFrame(
        {"Date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])}
    )
    detector.car_model = MagicMock()
    detector.car_model.compute_car.side_effect = RuntimeError("always fails")

    events_df = detector.score_events([(0, 0), (1, 1), (2, 2)])

    assert events_df.empty
    assert list(events_df.columns) == ["event_date", "start_idx", "end_idx", "car", "abs_car"]


# Positive test: only news within the configured event window should be attached.
def test_attach_news_only_keeps_articles_inside_news_window(tmp_path):
    detector = make_detector(tmp_path, news_window_days=1)
    detector.news_df = pd.DataFrame(
        {
            "published_utc": pd.to_datetime(["2024-01-09", "2024-01-10", "2024-01-11", "2024-01-14"]),
            "headline": ["before", "same-day", "after", "too-late"],
        }
    )
    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-10"]),
            "abs_car": [2.5],
        }
    )

    results_df = detector.attach_news(events_df)

    assert results_df["headline"].tolist() == ["before", "same-day", "after"]


# Positive test: the full pipeline should keep the top-k events and write an output file.
def test_run_limits_to_top_k_and_writes_output(tmp_path):
    detector = make_detector(tmp_path, top_k_events=1)
    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-03", "2024-01-01"]),
            "abs_car": [2.0, 1.0],
        }
    )
    results_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-03", "2024-01-01"]),
            "headline": ["kept", "dropped"],
        }
    )

    with patch.object(detector, "load_data"), \
         patch.object(detector, "setup_car"), \
         patch.object(detector, "detect_change_points", return_value=([1], [2])), \
         patch.object(detector, "build_windows", side_effect=[[(0, 1)], [(2, 3)]]), \
         patch.object(detector, "merge_windows", return_value=[(0, 1), (2, 3)]), \
         patch.object(detector, "score_events", return_value=events_df), \
         patch.object(detector, "attach_news", return_value=results_df) as attach_news_mock:
        final_events, final_results = detector.run()

    output_path = Path(tmp_path) / "NVDA.csv"
    assert output_path.exists()
    assert final_events["event_date"].tolist() == [pd.Timestamp("2024-01-03")]
    assert final_results["event_date"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-03")]
    truncated_events = attach_news_mock.call_args.args[0]
    assert truncated_events["event_date"].tolist() == [pd.Timestamp("2024-01-03")]


# Negative test: constant series should degrade to no detected changepoints instead of a crash.
def test_detect_change_points_with_constant_series_returns_no_points(detector):
    detector.price_df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=5, freq="D"),
            "stock_return": [0.01, 0.01, 0.01, 0.01, 0.01],
            "volatility": [0.2, 0.2, 0.2, 0.2, 0.2],
        }
    )

    with patch.object(detector, "run_pelt", side_effect=[[], []]):
        cp_returns, cp_vol = detector.detect_change_points()

    assert cp_returns == []
    assert cp_vol == []


# Negative test: invalid negative window configuration reveals a risky edge case in window building.
def test_build_windows_with_negative_window_values_produces_invalid_ranges(tmp_path, price_df):
    detector = make_detector(tmp_path, window_left=-1, window_right=-2)
    detector.price_df = price_df

    windows = detector.build_windows([2])

    assert windows == [(3, 0)]
    assert windows[0][0] > windows[0][1]


# Negative test: a negative news window currently produces no matches and documents undefined behavior.
def test_attach_news_with_negative_news_window_days_returns_no_matches(tmp_path):
    detector = make_detector(tmp_path, news_window_days=-1)
    detector.news_df = pd.DataFrame(
        {
            "published_utc": pd.to_datetime(["2024-01-09", "2024-01-10", "2024-01-11"]),
            "headline": ["before", "same-day", "after"],
        }
    )
    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-10"]),
            "abs_car": [1.2],
        }
    )

    results_df = detector.attach_news(events_df)

    assert results_df.empty


# Negative test: a zero top-k setting should not crash the pipeline and should propagate empty results.
def test_run_with_zero_top_k_returns_no_events_but_still_writes_output(tmp_path):
    detector = make_detector(tmp_path, top_k_events=0)
    detector.load_data = MagicMock()
    detector.setup_car = MagicMock()
    detector.detect_change_points = MagicMock(return_value=([1], [2]))
    detector.build_windows = MagicMock(side_effect=[[(0, 1)], [(2, 3)]])
    detector.merge_windows = MagicMock(return_value=[(0, 1), (2, 3)])
    detector.score_events = MagicMock(
        return_value=pd.DataFrame(
            {
                "event_date": pd.to_datetime(["2024-01-03", "2024-01-01"]),
                "abs_car": [2.0, 1.0],
            }
        )
    )
    detector.attach_news = MagicMock(return_value=pd.DataFrame(columns=["event_date", "headline"]))

    final_events, final_results = detector.run()

    assert final_events.empty
    assert final_results.empty
    attached_events = detector.attach_news.call_args.args[0]
    assert attached_events.empty
    assert (Path(tmp_path) / "NVDA.csv").exists()


# Negative test: malformed price data missing Close should raise a column error.
@patch("app.pipelines.core.event_detection.pd.read_csv")
def test_load_data_raises_when_close_column_is_missing(mock_read_csv, tmp_path):
    detector = make_detector(tmp_path)
    stock_df = pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=3, freq="D"), "Open": [1, 2, 3]})
    market_df = pd.DataFrame({"Date": pd.date_range("2024-01-01", periods=3, freq="D"), "Close": [10, 11, 12]})
    mock_read_csv.side_effect = [stock_df, market_df]

    with pytest.raises(KeyError, match="Close"):
        detector.load_data()


# Negative test: malformed news data missing published_utc should raise a column error.
@patch("app.pipelines.core.event_detection.pd.read_csv")
def test_load_data_raises_when_news_published_utc_column_is_missing(mock_read_csv, tmp_path):
    detector = make_detector(tmp_path)
    stock_dates = pd.date_range("2024-01-01", periods=20, freq="D")
    stock_df = pd.DataFrame({"Date": stock_dates, "Close": range(100, 120)})
    market_df = pd.DataFrame({"Date": stock_dates, "Close": range(200, 220)})
    news_df = pd.DataFrame({"headline": ["missing published utc"]})
    mock_read_csv.side_effect = [stock_df, market_df, news_df]

    with pytest.raises(KeyError, match="published_utc"):
        detector.load_data()


# Negative test: non-overlapping stock and market dates should leave no usable detection data.
@patch("app.pipelines.core.event_detection.pd.read_csv")
def test_load_data_with_no_overlapping_dates_leaves_detection_df_empty(mock_read_csv, tmp_path):
    detector = make_detector(tmp_path)
    stock_df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=15, freq="D"),
            "Close": range(100, 115),
        }
    )
    market_df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-02-01", periods=15, freq="D"),
            "Close": range(200, 215),
        }
    )
    news_df = pd.DataFrame({"published_utc": ["2024-01-01"], "headline": ["ok"]})
    mock_read_csv.side_effect = [stock_df, market_df, news_df]

    detector.load_data()

    assert detector.price_df.empty
    with pytest.raises(ValueError, match="No price data available"):
        detector._get_detection_df()


# Positive test: the saved CSV should contain the same rows returned by the pipeline output.
def test_run_writes_expected_csv_contents(tmp_path):
    detector = make_detector(tmp_path, top_k_events=2)
    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-03", "2024-01-01"]),
            "abs_car": [2.0, 1.0],
        }
    )
    results_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-01", "2024-01-03"]),
            "headline": ["first", "second"],
            "published_utc": pd.to_datetime(["2024-01-01", "2024-01-03"]),
        }
    )

    with patch.object(detector, "load_data"), \
         patch.object(detector, "setup_car"), \
         patch.object(detector, "detect_change_points", return_value=([1], [2])), \
         patch.object(detector, "build_windows", side_effect=[[(0, 1)], [(2, 3)]]), \
         patch.object(detector, "merge_windows", return_value=[(0, 1), (2, 3)]), \
         patch.object(detector, "score_events", return_value=events_df), \
         patch.object(detector, "attach_news", return_value=results_df):
        _, final_results = detector.run()

    output_path = Path(tmp_path) / "NVDA.csv"
    written_df = pd.read_csv(output_path, parse_dates=["event_date", "published_utc"])

    assert output_path.exists()
    assert written_df["headline"].tolist() == ["first", "second"]
    assert written_df["event_date"].tolist() == final_results["event_date"].tolist()


# Negative test: truly empty CSV inputs should degrade to empty dataframes instead of crashing.
@patch("app.pipelines.core.event_detection.pd.read_csv")
def test_load_data_with_empty_csv_files_does_not_crash(mock_read_csv, tmp_path):
    detector = make_detector(tmp_path)
    mock_read_csv.side_effect = [
        pd.errors.EmptyDataError("stock csv is empty"),
        pd.errors.EmptyDataError("market csv is empty"),
        pd.errors.EmptyDataError("news csv is empty"),
    ]

    detector.load_data()

    assert detector.price_df.empty
    assert detector.news_df.empty
    assert list(detector.news_df.columns) == ["published_utc"]


# Positive test: run should create the output CSV even when the target directory does not exist yet.
def test_run_creates_missing_results_directory_and_output_file(tmp_path):
    results_dir = tmp_path / "missing" / "nested" / "events"
    detector = EventDetector(
        ticker="NVDA",
        stock_path="stock.csv",
        market_path="market.csv",
        news_path="news.csv",
        results_dir=str(results_dir),
        top_k_events=1,
    )
    events_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-03"]),
            "abs_car": [2.0],
        }
    )
    results_df = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-03"]),
            "headline": ["kept"],
        }
    )

    with patch.object(detector, "load_data"), \
         patch.object(detector, "setup_car"), \
         patch.object(detector, "detect_change_points", return_value=([1], [2])), \
         patch.object(detector, "build_windows", side_effect=[[(0, 1)], [(2, 3)]]), \
         patch.object(detector, "merge_windows", return_value=[(0, 1), (2, 3)]), \
         patch.object(detector, "score_events", return_value=events_df), \
         patch.object(detector, "attach_news", return_value=results_df):
        final_events, final_results = detector.run()

    output_path = results_dir / "NVDA.csv"
    assert output_path.exists()
    assert final_events["event_date"].tolist() == [pd.Timestamp("2024-01-03")]
    assert final_results["headline"].tolist() == ["kept"]
