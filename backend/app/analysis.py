"""
AI-powered market analysis via AWS Bedrock (Claude).

Takes the current MacroSummary snapshot and produces a structured narrative:
  - Market regime & sentiment
  - What happened + why (narrative)
  - Key drivers with directional sentiment
  - Historical context / prior cycle comparisons
  - Forward-looking watchlist
"""

import json  # still needed for parsing the LLM's JSON response
import os
from datetime import datetime, timezone

import boto3

from .models import KeyDriver, MarketAnalysis, MarketSummary, WatchIndicator

BEDROCK_REGION = os.environ.get("AWS_REGION", "ca-central-1")
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
)
# boto3 picks up AWS_BEARER_TOKEN_BEDROCK automatically (botocore >= 1.37.0)


def _build_macro_context(summary: MarketSummary) -> str:
    lines: list[str] = []
    for category in summary.categories:
        lines.append(f"\n{category.name}:")
        for ind in category.indicators:
            change_str = ""
            if ind.change is not None:
                sign = "+" if ind.change >= 0 else ""
                change_str = f" (change: {sign}{ind.change:.4g} {ind.unit})"
            lines.append(
                f"  - {ind.name}: {ind.value:.4g} {ind.unit}{change_str}"
                f" [as of {ind.asOf}]"
            )
    return "\n".join(lines)


_bedrock_client = None


def _get_bedrock_client():
    """Reuse a single Bedrock client instead of creating one per request."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _bedrock_client


def generate_market_analysis(summary: MarketSummary) -> MarketAnalysis:
    macro_context = _build_macro_context(summary)

    prompt = f"""You are a macro-financial analyst. Analyze this data and return ONLY a JSON object.

DATA:
{macro_context}

JSON schema:
{{"regime":"1-2 sentences on current regime","regimeSentiment":"bullish|bearish|neutral|mixed","summary":"one sentence","narrative":"3-4 paragraphs citing data values","keyDrivers":[{{"title":"3-5 words","explanation":"2-3 sentences","sentiment":"positive|negative|neutral"}}],"historicalContext":"1-2 paragraphs comparing to prior cycles","watchlist":[{{"indicator":"name","currentSignal":"signal","whyItMatters":"reason"}}]}}

Rules: 3-5 key drivers, 3-4 watchlist items. Connect cause and effect. Plain English. JSON only."""

    client = _get_bedrock_client()

    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        inferenceConfig={"maxTokens": 4096},
    )

    stop_reason = response.get("stopReason", "")
    if stop_reason == "max_tokens":
        raise RuntimeError("Bedrock response truncated (hit max_tokens limit)")

    text: str = response["output"]["message"]["content"][0]["text"]

    # Tolerate any leading/trailing text around the JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    data = json.loads(text[start:end])

    return MarketAnalysis(
        regime=data["regime"],
        regimeSentiment=data["regimeSentiment"],
        summary=data["summary"],
        narrative=data["narrative"],
        keyDrivers=[KeyDriver(**d) for d in data["keyDrivers"]],
        historicalContext=data["historicalContext"],
        watchlist=[WatchIndicator(**w) for w in data["watchlist"]],
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )
