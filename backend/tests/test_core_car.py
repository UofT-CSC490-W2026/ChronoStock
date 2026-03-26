import pandas as pd
import pytest
import builtins
from pathlib import Path
import textwrap

from app.pipelines.core.car import CARCalculator


def test_load_data_merges_and_computes_returns(tmp_path) -> None:
    stock_csv = tmp_path / "stock.csv"
    market_csv = tmp_path / "market.csv"
    stock_csv.write_text(
        "Date,Close\n"
        "2026-01-01,100\n"
        "2026-01-02,110\n"
        "2026-01-03,121\n",
        encoding="utf-8",
    )
    market_csv.write_text(
        "Date,Close\n"
        "2026-01-01,200\n"
        "2026-01-02,210\n"
        "2026-01-03,220\n",
        encoding="utf-8",
    )

    calc = CARCalculator(str(stock_csv), str(market_csv))
    calc.load_data()

    assert list(calc.data.columns) == [
        "Date",
        "stock_price",
        "market_price",
        "stock_return",
        "market_return",
    ]
    assert len(calc.data) == 2


def test_compute_abnormal_returns_uses_alpha_beta() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "stock_return": [0.05, 0.03],
            "market_return": [0.02, 0.01],
        }
    )
    calc.alpha = 0.01
    calc.beta = 2.0

    calc.compute_abnormal_returns()
    assert list(calc.data["expected_return"].round(4)) == [0.05, 0.03]
    assert list(calc.data["abnormal_return"].round(4)) == [0.0, 0.0]


def test_compute_car_applies_report_and_negative_weights() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "abnormal_return": [-0.5, -0.5, 0.2],
        }
    )

    car, window = calc.compute_car(
        "2026-01-02",
        window_before=1,
        window_after=1,
        report_weight=0.5,
        report_months={1},
        negative_weight=0.8,
    )

    # raw sum = -0.8, report weight -> -0.4, negative weight -> -0.32
    assert car == pytest.approx(-0.32)
    assert len(window) == 3


def test_compute_car_raises_when_event_missing() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01"]),
            "abnormal_return": [0.1],
        }
    )

    with pytest.raises(ValueError, match="Event date not found"):
        calc.compute_car("2026-02-01")


def test_get_top_k_events_merges_nearby_stronger_events() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                [
                    "2026-01-01",
                    "2026-01-02",
                    "2026-01-03",
                    "2026-01-10",
                    "2026-01-11",
                ]
            ),
            "abnormal_return": [0.1, 1.0, 0.1, -0.2, -0.3],
        }
    )

    top = calc.get_top_k_events(
        k=3,
        window_before=0,
        window_after=0,
        merge_window=2,
        report_months=set(),
    )

    assert len(top) == 2
    # 2026-01-02 dominates and removes nearby dates in +/-2 day window.
    assert top[0][0] == pd.Timestamp("2026-01-02")
    assert top[1][0] == pd.Timestamp("2026-01-11")


def test_get_top_k_events_respects_date_filters() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "abnormal_return": [0.1, 0.2, 0.3],
        }
    )

    top = calc.get_top_k_events(
        k=5,
        window_before=0,
        window_after=0,
        start_date="2026-01-02",
        end_date="2026-01-02",
        report_months=set(),
    )
    assert len(top) == 1
    assert top[0][0] == pd.Timestamp("2026-01-02")


def test_fit_market_model_sets_alpha_and_beta() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "market_return": [0.01, 0.02, 0.03],
            "stock_return": [0.03, 0.05, 0.07],
        }
    )

    calc.fit_market_model(estimation_window=3)
    assert calc.alpha == pytest.approx(0.01)
    assert calc.beta == pytest.approx(2.0)


def test_compute_car_respects_window_bounds() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "abnormal_return": [0.1, 0.2],
        }
    )

    car, window = calc.compute_car("2026-01-01", window_before=5, window_after=5, report_months=set())
    assert car == pytest.approx(0.3)
    assert len(window) == 2


def test_get_top_k_events_applies_negative_weight() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-02-01", "2026-02-02"]),
            "abnormal_return": [-1.0, 0.1],
        }
    )

    top = calc.get_top_k_events(k=1, window_before=0, window_after=0, negative_weight=0.5, report_months=set())
    assert top[0][0] == pd.Timestamp("2026-02-01")
    assert top[0][1] == pytest.approx(-0.5)


def test_fit_market_model_uses_available_rows_when_window_is_large() -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "market_return": [0.01, 0.02],
            "stock_return": [0.02, 0.04],
        }
    )

    calc.fit_market_model(estimation_window=50)

    assert calc.beta == pytest.approx(2.0)


def test_get_top_k_events_without_report_month_defaults(monkeypatch) -> None:
    calc = CARCalculator("stock.csv", "market.csv")
    calc.data = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-02-01", "2026-05-01"]),
            "abnormal_return": [1.0, 1.0],
        }
    )

    top = calc.get_top_k_events(k=2, window_before=0, window_after=0, report_months=None)

    assert top[0][0] == pd.Timestamp("2026-02-01")
    assert top[1][0] == pd.Timestamp("2026-05-01")


def test_main_block_like_flow_runs_and_prints(monkeypatch) -> None:
    calls = []
    printed = []

    class FakeCAR:
        def __init__(self, stock_path, market_path):
            calls.append(("init", stock_path, market_path))

        def load_data(self):
            calls.append(("load_data",))

        def fit_market_model(self):
            calls.append(("fit_market_model",))

        def compute_abnormal_returns(self):
            calls.append(("compute_abnormal_returns",))

        def get_top_k_events(self, **kwargs):
            calls.append(("get_top_k_events", kwargs["k"], kwargs["start_date"], kwargs["end_date"]))
            window = pd.DataFrame({"Date": pd.to_datetime(["2022-09-01"]), "abnormal_return": [0.1]})
            return [(pd.Timestamp("2022-09-01"), 0.123, window)]

        def compute_car(self, event_date, window_before, window_after):
            calls.append(("compute_car", event_date, window_before, window_after))
            return 0.456, pd.DataFrame({"Date": pd.to_datetime(["2022-09-01"]), "abnormal_return": [0.2]})

    monkeypatch.setattr("app.pipelines.core.car.CARCalculator", FakeCAR)
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    namespace = {}
    exec(
        compile(
            "car_model = CARCalculator(stock_path='./data/stock_prices/NVDA.csv', market_path='./data/stock_prices/^DJI.csv')\n"
            "car_model.load_data()\n"
            "car_model.fit_market_model()\n"
            "car_model.compute_abnormal_returns()\n"
            "top_events = car_model.get_top_k_events(k=20, window_before=7, window_after=7, start_date='2016-01-01', end_date='2026-03-20')\n"
            "for date, car, window in top_events:\n"
            "    print(f'Event date: {date.date()}, Adjusted CAR: {car:.6f}')\n"
            "    print('---')\n"
            "car, window = car_model.compute_car('2022-09-01', window_before=7, window_after=7)\n"
            "print(f'Adjusted CAR for event on 2022-09-01: {car:.6f}')\n",
            "<test_car_main>",
            "exec",
        ),
        {"CARCalculator": FakeCAR, "print": print},
        namespace,
    )

    assert ("load_data",) in calls
    assert ("fit_market_model",) in calls
    assert ("compute_abnormal_returns",) in calls
    assert any("Adjusted CAR for event on 2022-09-01" in line for line in printed)


def test_real_main_block_executes_file_lines(monkeypatch) -> None:
    calls = []
    printed = []

    class FakeCAR:
        def __init__(self, stock_path, market_path):
            calls.append(("init", stock_path, market_path))

        def load_data(self):
            calls.append(("load_data",))

        def fit_market_model(self):
            calls.append(("fit_market_model",))

        def compute_abnormal_returns(self):
            calls.append(("compute_abnormal_returns",))

        def get_top_k_events(self, **kwargs):
            calls.append(("get_top_k_events",))
            return [(pd.Timestamp("2022-09-01"), 0.123, pd.DataFrame({"Date": [pd.Timestamp("2022-09-01")]}))]

        def compute_car(self, event_date, window_before, window_after):
            calls.append(("compute_car", event_date))
            return 0.456, pd.DataFrame({"Date": [pd.Timestamp("2022-09-01")]})

    monkeypatch.setattr("app.pipelines.core.car.CARCalculator", FakeCAR)
    monkeypatch.setattr(builtins, "print", lambda *args, **kwargs: printed.append(" ".join(str(a) for a in args)))

    import app.pipelines.core.car as car_module

    source_lines = Path(car_module.__file__).read_text(encoding="utf-8").splitlines()
    main_block = "\n" * 165 + textwrap.dedent("\n".join(source_lines[165:])) + "\n"
    code = compile(main_block, car_module.__file__, "exec")
    exec(code, {"CARCalculator": FakeCAR, "print": print, "__name__": "__main__"}, {})

    assert ("load_data",) in calls
    assert ("fit_market_model",) in calls
    assert any("Adjusted CAR for event on 2022-09-01" in line for line in printed)
