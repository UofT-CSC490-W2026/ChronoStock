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


def generate_market_analysis(summary: MarketSummary) -> MarketAnalysis:
    macro_context = _build_macro_context(summary)

    prompt = f"""You are a seasoned macroeconomic and financial markets analyst. \
Analyze the following current macroeconomic indicator data and produce a comprehensive \
market analysis narrative.

CURRENT MACROECONOMIC DATA (as of today):
{macro_context}

Produce a JSON response with exactly this structure — no markdown, no extra text, only valid JSON:
{{
  "regime": "1-2 sentence description of the current market regime",
  "regimeSentiment": "bullish" | "bearish" | "neutral" | "mixed",
  "summary": "One sentence capturing where markets stand right now",
  "narrative": "3-4 paragraphs. Explain what has been happening — what the Fed has done, how inflation has evolved, what the labor market shows, and how risk assets have responded. Be specific: cite actual data values from above.",
  "keyDrivers": [
    {{
      "title": "Short driver name (3-5 words)",
      "explanation": "2-3 sentences on how this force is driving markets and what it means for investors",
      "sentiment": "positive" | "negative" | "neutral"
    }}
  ],
  "historicalContext": "1-2 paragraphs comparing current conditions to prior cycles (e.g. 2022 tightening, 2020 COVID stimulus, 2008 GFC) where relevant. Help the reader understand if this is historically unusual.",
  "watchlist": [
    {{
      "indicator": "Name of the indicator",
      "currentSignal": "What the current reading is signalling",
      "whyItMatters": "Why this indicator is particularly important to watch right now"
    }}
  ]
}}

Rules:
- Include 3-5 key drivers and 3-4 watchlist items.
- Connect cause and effect between indicators — e.g. how rate levels affect credit spreads, how payrolls affect Fed expectations.
- Use plain English; avoid jargon that non-professionals would not understand.
- Return only the JSON object. No preamble, no markdown code fences."""

    client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        inferenceConfig={"maxTokens": 8192},
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
