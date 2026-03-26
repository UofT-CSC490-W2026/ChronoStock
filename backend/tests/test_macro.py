from datetime import datetime

import pandas as pd
import pytest

from app import macro


class FakeResponse:
    def __init__(self, observations):
        self._observations = observations

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {"observations": self._observations}


def test_fred_obs_filters_invalid_values(monkeypatch) -> None:
    monkeypatch.setattr(
        macro.httpx,
        "get",
        lambda url, params, timeout: FakeResponse(
            [
                {"date": "2026-01-01", "value": "."},
                {"date": "2026-01-02", "value": None},
                {"date": "2026-01-03", "value": ""},
                {"date": "2026-01-04", "value": "5.25"},
            ]
        ),
    )

    obs = macro._fred_obs("DFF", limit=5)
    assert obs == [{"date": "2026-01-04", "value": "5.25"}]


def test_fred_obs_passes_observation_start_param(monkeypatch) -> None:
    captured = {}

    def fake_get(url, params, timeout):
        captured.update(params)
        return FakeResponse([])

    monkeypatch.setattr(macro.httpx, "get", fake_get)

    macro._fred_obs("DFF", limit=5, observation_start="2020-01-01")

    assert captured["observation_start"] == "2020-01-01"


def test_fred_level_builds_indicator(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda series_id, limit, sort_order="desc", observation_start=None: [
            {"date": "2026-03-01", "value": "5.25"},
            {"date": "2026-02-01", "value": "5.00"},
        ],
    )

    item = macro._fred_level("DFF", "Fed Funds Rate", "%", "Rates")

    assert item is not None
    assert item.value == 5.25
    assert item.previousValue == 5.0
    assert item.change == 0.25
    assert item.asOf == "2026-03-01"


def test_fred_level_handles_single_observation(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda *args, **kwargs: [{"date": "2026-03-01", "value": "5.25"}],
    )

    item = macro._fred_level("DFF", "Fed Funds Rate", "%", "Rates")

    assert item is not None
    assert item.previousValue is None
    assert item.change is None


def test_fred_level_returns_none_when_no_observations(monkeypatch) -> None:
    monkeypatch.setattr(macro, "_fred_obs", lambda *args, **kwargs: [])

    assert macro._fred_level("DFF", "Fed Funds Rate", "%", "Rates") is None


def test_fred_level_returns_none_on_parse_error(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda *args, **kwargs: [{"date": "2026-03-01", "value": "bad"}],
    )

    assert macro._fred_level("DFF", "Fed Funds Rate", "%", "Rates") is None


def test_fred_monthly_change_returns_none_when_not_enough_observations(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda series_id, limit, sort_order="desc", observation_start=None: [
            {"date": "2026-03-01", "value": "100.0"}
        ],
    )
    assert macro._fred_monthly_change("PAYEMS", "Non-Farm Payroll", "K jobs", "Payrolls") is None


def test_fred_monthly_change_handles_two_observations(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda *args, **kwargs: [
            {"date": "2026-03-01", "value": "105.0"},
            {"date": "2026-02-01", "value": "100.0"},
        ],
    )

    item = macro._fred_monthly_change("PAYEMS", "Non-Farm Payroll", "K jobs", "Payrolls")

    assert item is not None
    assert item.value == 5.0
    assert item.previousValue is None
    assert item.change is None


def test_fred_yoy_builds_indicator(monkeypatch) -> None:
    observations = [
        {"date": f"2026-{month:02d}-01", "value": str(value)}
        for month, value in zip(
            range(1, 15),
            [126, 125, 124, 123, 122, 121, 120, 119, 118, 117, 116, 115, 114, 113],
        )
    ]
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda series_id, limit, sort_order="desc", observation_start=None: observations,
    )

    item = macro._fred_yoy("CPIAUCSL", "CPI (YoY)", "Inflation")

    assert item is not None
    assert item.unit == "% YoY"
    assert item.value == round((126 / 114 - 1) * 100, 2)
    assert item.previousValue == round((125 / 113 - 1) * 100, 2)


def test_fred_yoy_returns_none_when_not_enough_observations(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda *args, **kwargs: [{"date": "2026-03-01", "value": "100.0"}] * 12,
    )

    assert macro._fred_yoy("CPIAUCSL", "CPI (YoY)", "Inflation") is None


def test_yf_level_builds_indicator(monkeypatch) -> None:
    hist = pd.DataFrame(
        {"Close": [100.0, 105.0]},
        index=pd.to_datetime(["2026-03-01", "2026-03-02"]),
    )

    class FakeTicker:
        def history(self, period, interval="1d"):
            assert period == "5d"
            return hist

    monkeypatch.setattr(macro.yf, "Ticker", lambda ticker: FakeTicker())

    item = macro._yf_level("^GSPC", "S&P 500", "pts", "Index")

    assert item is not None
    assert item.value == 105.0
    assert item.previousValue == 100.0
    assert item.change == 5.0
    assert item.changePct == 5.0
    assert item.asOf == "2026-03-02"


def test_yf_level_returns_none_for_empty_or_single_row(monkeypatch) -> None:
    class FakeTickerEmpty:
        def history(self, period, interval="1d"):
            return pd.DataFrame(columns=["Close"])

    class FakeTickerSingle:
        def history(self, period, interval="1d"):
            return pd.DataFrame({"Close": [100.0]}, index=pd.to_datetime(["2026-03-02"]))

    monkeypatch.setattr(macro.yf, "Ticker", lambda ticker: FakeTickerEmpty())
    assert macro._yf_level("^GSPC", "S&P 500", "pts", "Index") is None

    monkeypatch.setattr(macro.yf, "Ticker", lambda ticker: FakeTickerSingle())
    item = macro._yf_level("^GSPC", "S&P 500", "pts", "Index")
    assert item is not None
    assert item.previousValue is None
    assert item.change is None
    assert item.changePct is None


def test_fetch_market_summary_filters_empty_categories(monkeypatch) -> None:
    monkeypatch.setattr(macro, "_fred_level", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro, "_fred_yoy", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro, "_fred_monthly_change", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        macro,
        "_yf_level",
        lambda ticker, name, unit, description: None
        if ticker != "^GSPC"
        else macro.MacroIndicator(
            name=name,
            value=5000.0,
            previousValue=4990.0,
            change=10.0,
            changePct=0.2,
            unit=unit,
            description=description,
            source="Yahoo Finance",
            asOf="2026-03-01",
        ),
    )

    summary = macro.fetch_market_summary()

    assert len(summary.categories) == 1
    assert summary.categories[0].name == "Market Sentiment"
    assert summary.categories[0].indicators[0].name == "S&P 500"


def test_fetch_market_summary_keeps_multiple_categories(monkeypatch) -> None:
    fred = macro.MacroIndicator(
        name="Fed Funds Rate",
        value=5.0,
        previousValue=4.5,
        change=0.5,
        changePct=None,
        unit="%",
        description="Rates",
        source="FRED",
        asOf="2026-03-01",
    )
    yf_item = macro.MacroIndicator(
        name="S&P 500",
        value=5000.0,
        previousValue=4990.0,
        change=10.0,
        changePct=0.2,
        unit="pts",
        description="Index",
        source="Yahoo Finance",
        asOf="2026-03-01",
    )

    monkeypatch.setattr(macro, "_fred_level", lambda *args, **kwargs: fred)
    monkeypatch.setattr(macro, "_fred_yoy", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro, "_fred_monthly_change", lambda *args, **kwargs: None)
    monkeypatch.setattr(macro, "_yf_level", lambda *args, **kwargs: yf_item)

    summary = macro.fetch_market_summary()

    assert len(summary.categories) >= 2
    assert all(category.indicators for category in summary.categories)


def test_fetch_indicator_history_raises_for_unknown_indicator() -> None:
    with pytest.raises(ValueError, match="Unknown indicator"):
        macro.fetch_indicator_history("Nope")


def test_fetch_indicator_history_fred_level(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda series_id, limit, sort_order="asc", observation_start=None: [
            {"date": "2024-01-01", "value": "4.0"},
            {"date": "2025-01-01", "value": "5.0"},
        ],
    )

    history = macro.fetch_indicator_history("Fed Funds Rate")

    assert history.unit == "%"
    assert [point.value for point in history.data] == [4.0, 5.0]


def test_fetch_indicator_history_fred_yoy(monkeypatch) -> None:
    current_year = datetime.now().year
    obs = [
        {"date": f"{current_year - 1}-01-{day:02d}", "value": str(100 + day)}
        for day in range(1, 14)
    ]
    obs.append({"date": f"{current_year}-01-20", "value": "130"})
    monkeypatch.setattr(macro, "_fred_obs", lambda *args, **kwargs: obs)

    history = macro.fetch_indicator_history("CPI (YoY)")

    assert history.name == "CPI (YoY)"
    assert len(history.data) >= 1
    assert history.data[-1].value == round((130 / 102 - 1) * 100, 2)


def test_fetch_indicator_history_fred_monthly_change(monkeypatch) -> None:
    current_year = datetime.now().year
    obs = [
        {"date": f"{current_year}-01-01", "value": "100.0"},
        {"date": f"{current_year}-02-01", "value": "105.0"},
        {"date": f"{current_year}-03-01", "value": "111.0"},
    ]
    monkeypatch.setattr(macro, "_fred_obs", lambda *args, **kwargs: obs)

    history = macro.fetch_indicator_history("Non-Farm Payroll")

    assert [point.value for point in history.data] == [5.0, 6.0]


def test_fetch_indicator_history_monthly_change_filters_old_rows(monkeypatch) -> None:
    current_year = datetime.now().year
    obs = [
        {"date": f"{current_year - 6}-01-01", "value": "90.0"},
        {"date": f"{current_year - 5}-04-01", "value": "100.0"},
        {"date": f"{current_year - 5}-05-01", "value": "101.0"},
    ]
    monkeypatch.setattr(macro, "_fred_obs", lambda *args, **kwargs: obs)

    history = macro.fetch_indicator_history("Non-Farm Payroll")

    assert [point.time for point in history.data] == [
        f"{current_year - 5}-04-01",
        f"{current_year - 5}-05-01",
    ]
    assert [point.value for point in history.data] == [10.0, 1.0]


def test_fetch_indicator_history_yf(monkeypatch) -> None:
    hist = pd.DataFrame(
        {"Close": [20.12345, 21.98765]},
        index=pd.to_datetime(["2026-03-01", "2026-03-02"]),
    )

    class FakeTicker:
        def history(self, period):
            assert period == "5y"
            return hist

    monkeypatch.setattr(macro.yf, "Ticker", lambda ticker: FakeTicker())

    history = macro.fetch_indicator_history("Gold")

    assert history.unit == "$/oz"
    assert history.data[0].time == "2026-03-01"
    assert history.data[0].value == 20.1234


def test_fetch_indicator_history_yf_skips_nan_close(monkeypatch) -> None:
    hist = pd.DataFrame(
        {"Close": [20.12345, None, 21.98765]},
        index=pd.to_datetime(["2026-03-01", "2026-03-02", "2026-03-03"]),
    )

    class FakeTicker:
        def history(self, period):
            return hist

    monkeypatch.setattr(macro.yf, "Ticker", lambda ticker: FakeTicker())

    history = macro.fetch_indicator_history("Gold")

    assert [point.time for point in history.data] == ["2026-03-01", "2026-03-03"]


def test_fred_monthly_change_returns_none_on_parse_error(monkeypatch) -> None:
    monkeypatch.setattr(
        macro,
        "_fred_obs",
        lambda *args, **kwargs: [
            {"date": "2026-03-01", "value": "bad"},
            {"date": "2026-02-01", "value": "100.0"},
        ],
    )

    assert macro._fred_monthly_change("PAYEMS", "Non-Farm Payroll", "K jobs", "Payrolls") is None


def test_fred_yoy_returns_none_on_parse_error(monkeypatch) -> None:
    obs = [{"date": f"2026-{month:02d}-01", "value": "100.0"} for month in range(1, 13)]
    obs.append({"date": "2027-01-01", "value": "bad"})
    monkeypatch.setattr(macro, "_fred_obs", lambda *args, **kwargs: obs)

    assert macro._fred_yoy("CPIAUCSL", "CPI (YoY)", "Inflation") is None


def test_yf_level_returns_none_on_history_error(monkeypatch) -> None:
    class FakeTicker:
        def history(self, *args, **kwargs):
            raise RuntimeError("yfinance down")

    monkeypatch.setattr(macro.yf, "Ticker", lambda ticker: FakeTicker())

    assert macro._yf_level("^GSPC", "S&P 500", "pts", "Index") is None
