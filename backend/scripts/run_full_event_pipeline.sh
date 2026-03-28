#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/home/ec2-user/backend.env}"
IMAGE="${IMAGE:-zihan123/chronostock-backend:latest}"
BENCHMARK_TICKER="${BENCHMARK_TICKER:-^DJI}"
DEFAULT_TICKERS="AMZN,TSLA,GOOGL,META,AAPL,MSFT,NVDA"
TICKERS="${TICKERS:-${MONTHLY_EVENT_TICKERS:-$DEFAULT_TICKERS}}"
START_DATE="${START_DATE:-$(date -u -d '5 years ago' +%F)}"
END_DATE="${END_DATE:-$(date -u +%F)}"
POLYGON_TIMEOUT_SECONDS="${POLYGON_TIMEOUT_SECONDS:-60}"
POLYGON_MAX_RETRIES="${POLYGON_MAX_RETRIES:-3}"
POLYGON_RETRY_SLEEP_SECONDS="${POLYGON_RETRY_SLEEP_SECONDS:-15}"

echo "Pulling latest image: $IMAGE"
docker pull "$IMAGE"

echo "Refreshing benchmark price history for $BENCHMARK_TICKER"
docker run --rm \
  --env-file "$ENV_FILE" \
  "$IMAGE" \
  python -c "from app.pipelines.data_ingestion import get_stockprice; get_stockprice('$BENCHMARK_TICKER', '$START_DATE', '$END_DATE', save_db=False, save_local=True)"

echo "Running ingestion for: $TICKERS"
docker run --rm \
  --env-file "$ENV_FILE" \
  -e POLYGON_TIMEOUT_SECONDS="$POLYGON_TIMEOUT_SECONDS" \
  -e POLYGON_MAX_RETRIES="$POLYGON_MAX_RETRIES" \
  -e POLYGON_RETRY_SLEEP_SECONDS="$POLYGON_RETRY_SLEEP_SECONDS" \
  "$IMAGE" \
  python -u -m app.pipelines.data_ingestion --tickers "$TICKERS" --start-date "$START_DATE" --end-date "$END_DATE"

echo "Running cleaning for: $TICKERS"
docker run --rm \
  --env-file "$ENV_FILE" \
  "$IMAGE" \
  python -u -m app.pipelines.data_cleaning --tickers "$TICKERS"

IFS=',' read -r -a TICKER_ARRAY <<< "$TICKERS"
for ticker in "${TICKER_ARRAY[@]}"; do
  ticker="${ticker//[[:space:]]/}"
  if [[ -z "$ticker" ]]; then
    continue
  fi

  echo "Running event pipeline for: $ticker"
  docker run --rm \
    --env-file "$ENV_FILE" \
    "$IMAGE" \
    python -m app.pipelines.run_s3_event_pipeline --ticker "$ticker" --start-date "$START_DATE" --end-date "$END_DATE"
done

echo "Full event pipeline run completed for: $TICKERS"
