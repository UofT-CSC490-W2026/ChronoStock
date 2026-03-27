import argparse
import ast
import json
import os

import pandas as pd
from openai import OpenAI

DEFAULT_LLM_MODEL = "deepseek-chat"
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"


PROMPT_TEMPLATE = """
You are a financial event analyst.

Your job is to identify news that are **strong indicators of core historical events** for the company.
These include mergers & acquisitions, product launches, regulatory approvals, major leadership changes, or other events that could explain stock price movement.

Rules:
- Keep only factual news
- Remove opinion pieces
- Remove speculation
- Remove advertisements
- Remove quarterly financial report
- Remove "best stocks to buy" articles
- Keep news that describes real events (earnings, acquisitions, product launches, regulations, partnerships, lawsuits, etc.)
- Keep at most 1 news per date

Return ONLY a Python list of IDs.

Example output:
[
"KceCO36NPaFNq3BPrtjbqgaji6_UuOuOivwkfJpIUM4",
"8mc0L7JAqaTBcl49AWKiZOYkFiCNM5l98kw1aVSMiAU",
"qDKZ5wQaYaVTe7NQ_I2jyq9IuVo2V0H2t0s60U0qoJg",
]

News:
{news_block}
""".strip()


class ChatCompletionsLLM:
    def __init__(self, api_key, model, base_url=None, max_tokens=256, temperature=0.0):
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        self.client = OpenAI(**client_kwargs)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def __call__(self, prompt):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return [{"generated_text": response.choices[0].message.content or ""}]


class NewsLLMFilter:
    def __init__(self, llm, batch_size=100, max_retries=3):
        self.llm = llm
        self.batch_size = batch_size
        self.max_retries = max_retries

    def format_news_block(self, df):
        lines = []
        for _, row in df.iterrows():
            lines.append(
                "\n".join(
                    [
                        f"ID: {row['id']}",
                        f"Date: {row['event_date']}",
                        f"Title: {row.get('title', '')}",
                        f"Description: {row.get('description', '')}",
                    ]
                )
            )
        return "\n\n".join(lines)

    def build_date_batches(self, df):
        batches = []
        current_batch = []
        current_size = 0

        for _, group in df.groupby(df["published_utc"].dt.date, sort=False):
            group_list = list(group.index)
            group_size = len(group_list)

            if current_size > 0 and current_size + group_size > self.batch_size:
                batches.append(df.loc[current_batch])
                current_batch = []
                current_size = 0

            current_batch.extend(group_list)
            current_size += group_size

        if current_batch:
            batches.append(df.loc[current_batch])

        return batches

    def keep_one_per_day(self, df, selected_ids):
        filtered = df[df["id"].isin(selected_ids)].copy()
        filtered = filtered.sort_values(["event_date", "abs_car"], ascending=[True, False])
        filtered = filtered.drop_duplicates(subset="event_date", keep="first")
        return filtered["id"].tolist()

    def extract_ids(self, text):
        start = text.find("[")
        end = text.rfind("]") + 1
        if start == -1 or end <= start:
            return []

        payload = text[start:end]
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(payload)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, str)]
            except Exception:
                continue
        return []

    def call_llm_with_retries(self, prompt, batch_index, total_batches):
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self.llm(prompt)[0]["generated_text"]
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    print(
                        f"Retrying failed batch {batch_index}/{total_batches} "
                        f"(attempt {attempt + 1}/{self.max_retries}): {exc}"
                    )
        raise last_error

    def run(self, df, start_date=None, end_date=None):
        if start_date is not None:
            df = df[df["published_utc"] >= pd.Timestamp(start_date)]
        if end_date is not None:
            df = df[df["published_utc"] <= pd.Timestamp(end_date)]

        df = df.sort_values("event_date")
        batches = self.build_date_batches(df)
        selected_ids = []
        failed_batches = []

        for index, batch in enumerate(batches, start=1):
            print(f"Processing batch {index}/{len(batches)} ({len(batch)} rows)")
            news_block = self.format_news_block(batch)
            prompt = PROMPT_TEMPLATE.format(news_block=news_block)
            try:
                output = self.call_llm_with_retries(prompt, index, len(batches))
            except Exception as exc:
                failed_batches.append(
                    {
                        "batch": index,
                        "rows": len(batch),
                        "error": str(exc),
                    }
                )
                print(f"Skipping failed batch {index}/{len(batches)}: {exc}")
                continue
            selected_ids.extend(self.extract_ids(output))

        selected_ids = list(set(selected_ids))
        if failed_batches:
            print(f"LLM filtering skipped {len(failed_batches)} failed batch(es).")
        return self.keep_one_per_day(df, selected_ids)


def load_events(path):
    df = pd.read_csv(path)
    required_columns = {"id", "event_date", "published_utc", "title", "description", "abs_car"}
    missing = required_columns - set(df.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns in {path}: {missing_str}")

    df["published_utc"] = pd.to_datetime(df["published_utc"], errors="coerce")
    df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    df = df.dropna(subset=["published_utc", "event_date", "id"])
    return df.sort_values("event_date").reset_index(drop=True)


def resolve_default_output(input_path, output_dir):
    ticker = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_dir, f"{ticker}.csv")


def build_llm_from_args(args):
    api_key = args.api_key or os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError("Missing API key. Set --api-key or LLM_API_KEY.")

    return ChatCompletionsLLM(
        api_key=api_key,
        model=args.model,
        base_url=args.base_url,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Filter event news with a designated LLM.")
    parser.add_argument("input_path", help="Path to an event CSV, for example ./data/events/NVDA.csv")
    parser.add_argument("--output-dir", default="./data/results", help="Directory for filtered CSV output")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL))
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY"))
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    return parser.parse_args()


def main():
    args = parse_args()
    df = load_events(args.input_path)
    llm = build_llm_from_args(args)
    filter_pipeline = NewsLLMFilter(llm, batch_size=args.batch_size)

    selected_ids = filter_pipeline.run(
        df,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    filtered_df = df[df["id"].isin(selected_ids)].copy()
    filtered_df.sort_values("event_date", inplace=True)

    os.makedirs(args.output_dir, exist_ok=True)
    output_path = resolve_default_output(args.input_path, args.output_dir)
    filtered_df.to_csv(output_path, index=False)

    print(f"Selected news: {len(selected_ids)}")
    print(f"Saved filtered results to: {output_path}")


if __name__ == "__main__":
    main()
