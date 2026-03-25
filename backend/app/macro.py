"""
Macro-economic data fetcher.

Sources:
  - FRED API  (Federal Reserve Bank of St. Louis) — economic releases
  - Yahoo Finance via yfinance                    — real-time market prices
"""

import os
from datetime import datetime, timezone, timedelta

import httpx
import yfinance as yf

from .models import MacroCategory, IndicatorDataPoint, IndicatorHistory, MacroIndicator, MarketSummary

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


# ── FRED helpers ──────────────────────────────────────────────────────────────

def _fred_obs(series_id: str, limit: int, sort_order: str = "desc", observation_start: str | None = None) -> list[dict]:
    """Return `limit` valid observations for a FRED series (desc = latest first)."""
    params: dict = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "sort_order": sort_order,
        "limit": limit,
        "file_type": "json",
    }
    if observation_start:
        params["observation_start"] = observation_start
    r = httpx.get(FRED_BASE, params=params, timeout=15)
    r.raise_for_status()
    return [o for o in r.json().get("observations", []) if o.get("value") not in (".", None, "")]


def _fred_level(series_id: str, name: str, unit: str, description: str) -> MacroIndicator | None:
    """Indicator whose headline figure is the current level (e.g. Fed Funds Rate, Unemployment)."""
    try:
        obs = _fred_obs(series_id, limit=2)
        if not obs:
            return None
        val = float(obs[0]["value"])
        prev = float(obs[1]["value"]) if len(obs) > 1 else None
        change = round(val - prev, 4) if prev is not None else None
        return MacroIndicator(
            name=name,
            value=round(val, 4),
            previousValue=round(prev, 4) if prev is not None else None,
            change=change,
            changePct=None,
            unit=unit,
            description=description,
            source="FRED",
            asOf=obs[0]["date"],
        )
    except Exception:
        return None


def _fred_monthly_change(series_id: str, name: str, unit: str, description: str) -> MacroIndicator | None:
    """Indicator whose headline figure is the MoM delta (e.g. Non-Farm Payroll)."""
    try:
        obs = _fred_obs(series_id, limit=3)
        if len(obs) < 2:
            return None
        latest_chg = round(float(obs[0]["value"]) - float(obs[1]["value"]), 1)
        prev_chg = round(float(obs[1]["value"]) - float(obs[2]["value"]), 1) if len(obs) >= 3 else None
        change = round(latest_chg - prev_chg, 1) if prev_chg is not None else None
        return MacroIndicator(
            name=name,
            value=latest_chg,
            previousValue=prev_chg,
            change=change,
            changePct=None,
            unit=unit,
            description=description,
            source="FRED",
            asOf=obs[0]["date"],
        )
    except Exception:
        return None


def _fred_yoy(series_id: str, name: str, description: str) -> MacroIndicator | None:
    """Indicator whose headline is the YoY % change of a price index (e.g. CPI, PCE)."""
    try:
        obs = _fred_obs(series_id, limit=15)  # 13 months + buffer
        if len(obs) < 13:
            return None
        yoy = round((float(obs[0]["value"]) / float(obs[12]["value"]) - 1) * 100, 2)
        prev_yoy = None
        if len(obs) >= 14:
            prev_yoy = round((float(obs[1]["value"]) / float(obs[13]["value"]) - 1) * 100, 2)
        change = round(yoy - prev_yoy, 2) if prev_yoy is not None else None
        return MacroIndicator(
            name=name,
            value=yoy,
            previousValue=prev_yoy,
            change=change,
            changePct=None,
            unit="% YoY",
            description=description,
            source="FRED",
            asOf=obs[0]["date"],
        )
    except Exception:
        return None


# ── yfinance helper ───────────────────────────────────────────────────────────

def _yf_level(ticker: str, name: str, unit: str, description: str) -> MacroIndicator | None:
    """Indicator from Yahoo Finance (last close vs prior close)."""
    try:
        hist = yf.Ticker(ticker).history(period="5d", interval="1d").dropna(subset=["Close"])
        if hist.empty:
            return None
        val = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
        change = round(val - prev, 4) if prev is not None else None
        change_pct = round((change / prev) * 100, 2) if prev and change is not None else None
        return MacroIndicator(
            name=name,
            value=round(val, 2),
            previousValue=round(prev, 2) if prev is not None else None,
            change=round(change, 4) if change is not None else None,
            changePct=change_pct,
            unit=unit,
            description=description,
            source="Yahoo Finance",
            asOf=hist.index[-1].strftime("%Y-%m-%d"),
        )
    except Exception:
        return None


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_market_summary() -> MarketSummary:
    def collect(*indicators: MacroIndicator | None) -> list[MacroIndicator]:
        return [i for i in indicators if i is not None]

    categories = [
        MacroCategory(
            name="Interest Rates & Yield Curve",
            indicators=collect(
                _fred_level("DFF", "Fed Funds Rate", "%",
                            "Effective Federal Funds Rate — the Fed's primary policy lever"),
                _yf_level("^TNX", "10Y Treasury Yield", "%",
                          "10-Year US Treasury yield — benchmark for mortgages and long-term debt"),
                _yf_level("^FVX", "5Y Treasury Yield", "%",
                          "5-Year US Treasury yield — midpoint of the curve"),
                _fred_level("T10Y2Y", "Yield Curve (10Y-2Y)", "pp",
                            "10Y minus 2Y Treasury spread — inversion signals recession risk"),
            ),
        ),
        MacroCategory(
            name="Inflation",
            indicators=collect(
                _fred_yoy("CPIAUCSL", "CPI (YoY)",
                          "Consumer Price Index — headline inflation including food and energy"),
                _fred_yoy("CPILFESL", "Core CPI (YoY)",
                          "CPI excluding food and energy — less volatile signal the Fed watches closely"),
                _fred_yoy("PCEPI", "PCE (YoY)",
                          "Personal Consumption Expenditures price index"),
                _fred_yoy("PCEPILFE", "Core PCE (YoY)",
                          "PCE excluding food and energy — the Fed's preferred inflation gauge"),
                _fred_level("T10YIE", "10Y Breakeven Inflation", "%",
                            "Market-implied 10-year inflation expectation derived from TIPS spreads"),
            ),
        ),
        MacroCategory(
            name="Labor Market",
            indicators=collect(
                _fred_monthly_change("PAYEMS", "Non-Farm Payroll", "K jobs",
                                     "Monthly change in total nonfarm employees — the headline jobs number"),
                _fred_level("UNRATE", "Unemployment Rate", "%",
                            "U-3 unemployment rate — share of labor force actively seeking work"),
                _fred_level("ICSA", "Initial Jobless Claims", "K",
                            "Weekly new unemployment filings — leading indicator of labor market stress"),
                _fred_level("JTSJOL", "JOLTS Job Openings", "K",
                            "Total job openings from the JOLTS survey — measures unfilled labor demand"),
            ),
        ),
        MacroCategory(
            name="Market Sentiment",
            indicators=collect(
                _yf_level("^VIX", "VIX", "pts",
                          "CBOE Volatility Index — 30-day implied volatility of S&P 500 options (the 'fear gauge')"),
                _yf_level("^GSPC", "S&P 500", "pts",
                          "S&P 500 index — benchmark for US large-cap equities"),
                _fred_level("BAMLH0A0HYM2", "HY Credit Spread", "pp",
                            "High Yield OAS spread over Treasuries — elevated spread = risk aversion in credit markets"),
            ),
        ),
        MacroCategory(
            name="Commodities & Currency",
            indicators=collect(
                _yf_level("DX-Y.NYB", "US Dollar (DXY)", "pts",
                          "US Dollar Index — USD vs basket of major currencies; strong dollar pressures multinational earnings"),
                _yf_level("GC=F", "Gold", "$/oz",
                          "Gold futures — safe haven asset and inflation hedge"),
                _yf_level("CL=F", "WTI Crude Oil", "$/bbl",
                          "West Texas Intermediate crude oil futures — energy cost benchmark"),
                _yf_level("HG=F", "Copper", "$/lb",
                          "'Dr. Copper' — copper demand leads economic cycles due to broad industrial use"),
            ),
        ),
    ]

    return MarketSummary(
        categories=[c for c in categories if c.indicators],
        cachedAt=datetime.now(timezone.utc).isoformat(),
    )


# ── Indicator history ──────────────────────────────────────────────────────────

# Maps indicator name → (source_type, series_id, unit)
# source_type: "fred_level" | "fred_yoy" | "fred_monthly_change" | "yf"
INDICATOR_MAP: dict[str, tuple[str, str, str]] = {
    "Fed Funds Rate":          ("fred_level",          "DFF",           "%"),
    "10Y Treasury Yield":      ("yf",                  "^TNX",          "%"),
    "5Y Treasury Yield":       ("yf",                  "^FVX",          "%"),
    "Yield Curve (10Y-2Y)":    ("fred_level",          "T10Y2Y",        "pp"),
    "CPI (YoY)":               ("fred_yoy",            "CPIAUCSL",      "% YoY"),
    "Core CPI (YoY)":          ("fred_yoy",            "CPILFESL",      "% YoY"),
    "PCE (YoY)":               ("fred_yoy",            "PCEPI",         "% YoY"),
    "Core PCE (YoY)":          ("fred_yoy",            "PCEPILFE",      "% YoY"),
    "10Y Breakeven Inflation":  ("fred_level",          "T10YIE",        "%"),
    "Non-Farm Payroll":        ("fred_monthly_change", "PAYEMS",        "K jobs"),
    "Unemployment Rate":       ("fred_level",          "UNRATE",        "%"),
    "Initial Jobless Claims":  ("fred_level",          "ICSA",          "K"),
    "JOLTS Job Openings":      ("fred_level",          "JTSJOL",        "K"),
    "VIX":                     ("yf",                  "^VIX",          "pts"),
    "S&P 500":                 ("yf",                  "^GSPC",         "pts"),
    "HY Credit Spread":        ("fred_level",          "BAMLH0A0HYM2",  "pp"),
    "US Dollar (DXY)":         ("yf",                  "DX-Y.NYB",      "pts"),
    "Gold":                    ("yf",                  "GC=F",          "$/oz"),
    "WTI Crude Oil":           ("yf",                  "CL=F",          "$/bbl"),
    "Copper":                  ("yf",                  "HG=F",          "$/lb"),
}


def fetch_indicator_history(name: str) -> IndicatorHistory:
    """Fetch 5-year historical time-series for a single macro indicator."""
    if name not in INDICATOR_MAP:
        raise ValueError(f"Unknown indicator: {name}")

    source_type, series_id, unit = INDICATOR_MAP[name]
    data: list[IndicatorDataPoint] = []

    # Start date for 5 years of output data
    five_years_ago = (datetime.now(timezone.utc) - timedelta(days=5 * 365)).strftime("%Y-%m-%d")
    # YoY/monthly-change calculations need extra leading observations
    yoy_start = (datetime.now(timezone.utc) - timedelta(days=5 * 365 + 400)).strftime("%Y-%m-%d")

    if source_type == "fred_level":
        obs = _fred_obs(series_id, limit=10_000, sort_order="asc", observation_start=five_years_ago)
        data = [IndicatorDataPoint(time=o["date"], value=round(float(o["value"]), 4)) for o in obs]

    elif source_type == "fred_yoy":
        # Fetch 13+ extra months so YoY can be computed for the full 5Y window
        obs = _fred_obs(series_id, limit=200, sort_order="asc", observation_start=yoy_start)
        for i in range(12, len(obs)):
            if obs[i]["date"] >= five_years_ago:
                yoy = round((float(obs[i]["value"]) / float(obs[i - 12]["value"]) - 1) * 100, 2)
                data.append(IndicatorDataPoint(time=obs[i]["date"], value=yoy))

    elif source_type == "fred_monthly_change":
        obs = _fred_obs(series_id, limit=62, sort_order="asc", observation_start=yoy_start)
        for i in range(1, len(obs)):
            if obs[i]["date"] >= five_years_ago:
                chg = round(float(obs[i]["value"]) - float(obs[i - 1]["value"]), 1)
                data.append(IndicatorDataPoint(time=obs[i]["date"], value=chg))

    elif source_type == "yf":
        hist = yf.Ticker(series_id).history(period="5y").dropna(subset=["Close"])
        data = [
            IndicatorDataPoint(
                time=row.Index.strftime("%Y-%m-%d"),
                value=round(float(row.Close), 4),
            )
            for row in hist.itertuples()
        ]

    return IndicatorHistory(
        name=name,
        unit=unit,
        data=data,
        cachedAt=datetime.now(timezone.utc).isoformat(),
    )
