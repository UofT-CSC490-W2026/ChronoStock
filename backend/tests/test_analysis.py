from datetime import datetime, timezone

import pytest

from app import analysis
from app.models import MacroCategory, MacroIndicator, MarketSummary


def _summary() -> MarketSummary:
    return MarketSummary(
        categories=[
            MacroCategory(
                name="Inflation",
                indicators=[
                    MacroIndicator(
                        name="CPI (YoY)",
                        value=3.1,
                        previousValue=3.3,
                        change=-0.2,
                        changePct=None,
                        unit="% YoY",
                        description="Inflation",
                        source="FRED",
                        asOf="2026-02-01",
                    ),
                    MacroIndicator(
                        name="Fed Funds Rate",
                        value=5.25,
                        previousValue=None,
                        change=None,
                        changePct=None,
                        unit="%",
                        description="Rates",
                        source="FRED",
                        asOf="2026-02-01",
                    ),
                ],
            )
        ],
        cachedAt=datetime.now(timezone.utc).isoformat(),
    )


def test_build_macro_context_includes_change_when_present() -> None:
    context = analysis._build_macro_context(_summary())

    assert "Inflation:" in context
    assert "CPI (YoY): 3.1 % YoY (change: -0.2 % YoY) [as of 2026-02-01]" in context
    assert "Fed Funds Rate: 5.25 % [as of 2026-02-01]" in context


def test_generate_market_analysis_parses_json_with_wrapping_text(monkeypatch) -> None:
    response = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "content": [
                    {
                        "text": (
                            "Preface {"
                            '"regime":"disinflation",'
                            '"regimeSentiment":"bullish",'
                            '"summary":"Markets are stable.",'
                            '"narrative":"Paragraph 1\\n\\nParagraph 2.",'
                            '"keyDrivers":[{"title":"Cooling CPI","explanation":"Inflation eased.","sentiment":"positive"}],'
                            '"historicalContext":"Less restrictive than 2022.",'
                            '"watchlist":[{"indicator":"Payrolls","currentSignal":"Still firm","whyItMatters":"Fed path"}]'
                            "} trailing"
                        )
                    }
                ]
            }
        },
    }

    class FakeClient:
        def converse(self, **kwargs):
            return response

    monkeypatch.setattr(analysis.boto3, "client", lambda service, region_name: FakeClient())

    result = analysis.generate_market_analysis(_summary())

    assert result.regime == "disinflation"
    assert result.regimeSentiment == "bullish"
    assert result.keyDrivers[0].title == "Cooling CPI"
    assert result.watchlist[0].indicator == "Payrolls"
    assert result.generatedAt.endswith("+00:00")


def test_generate_market_analysis_raises_when_bedrock_truncates(monkeypatch) -> None:
    class FakeClient:
        def converse(self, **kwargs):
            return {
                "stopReason": "max_tokens",
                "output": {"message": {"content": [{"text": "{}"}]}},
            }

    monkeypatch.setattr(analysis.boto3, "client", lambda service, region_name: FakeClient())

    with pytest.raises(RuntimeError, match="truncated"):
        analysis.generate_market_analysis(_summary())
