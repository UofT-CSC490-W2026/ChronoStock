#!/bin/bash
set -e

[ -f /var/lib/cloud/instance/.user_data_done ] && exit 0

dnf install -y docker jq amazon-cloudwatch-agent amazon-ssm-agent

systemctl enable --now docker
systemctl enable --now amazon-ssm-agent

until docker info > /dev/null 2>&1; do
  sleep 2
done

usermod -aG docker ec2-user

############################################
# Fetch app secrets from Secrets Manager
############################################
SECRET_JSON=""
for attempt in $(seq 1 30); do
  if SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id ${secret_name} \
    --region ${aws_region} \
    --query SecretString \
    --output text 2>/tmp/get-secret.err); then
    break
  fi

  echo "Secrets Manager value not ready yet for ${secret_name} (attempt $${attempt}/30)." >&2
  sleep 10
done

if [ -z "$SECRET_JSON" ]; then
  echo "Failed to fetch secret ${secret_name} after retries." >&2
  cat /tmp/get-secret.err >&2 || true
  exit 1
fi

DB_USER=$(echo "$SECRET_JSON" | jq -r '.username')
DB_PASS=$(echo "$SECRET_JSON" | jq -r '.password')
DB_HOST=$(echo "$SECRET_JSON" | jq -r '.host')
DB_NAME=$(echo "$SECRET_JSON" | jq -r '.dbname')
DB_PORT=$(echo "$SECRET_JSON" | jq -r '.port')
JWT_SECRET=$(echo "$SECRET_JSON" | jq -r '.jwt_secret_key')
POLYGON_API_KEY=$(echo "$SECRET_JSON" | jq -r '.polygon_api_key')
LLM_API_KEY=$(echo "$SECRET_JSON" | jq -r '.llm_api_key')

DATABASE_URL="postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME"

cat <<EOT > /home/ec2-user/backend.env
DB_BACKEND=postgres
DATABASE_URL=$DATABASE_URL
JWT_SECRET_KEY=$JWT_SECRET
FRONTEND_URL=${frontend_url}
SEC_USER_AGENT_EMAIL=${certbot_email}
PIPELINE_S3_BUCKET=${bucket_name}
AWS_REGION=${aws_region}
POLYGON_API_KEY=$POLYGON_API_KEY
LLM_API_KEY=$LLM_API_KEY
LLM_MODEL=${llm_model}
LLM_BASE_URL=${llm_base_url}
MONTHLY_EVENT_TICKERS=${monthly_event_tickers}
EOT

chown ec2-user:ec2-user /home/ec2-user/backend.env

############################################
# Log file
############################################
touch /home/ec2-user/backend.log
chown ec2-user:ec2-user /home/ec2-user/backend.log
touch /home/ec2-user/daily_update.log
chown ec2-user:ec2-user /home/ec2-user/daily_update.log
touch /home/ec2-user/hourly_update.log
chown ec2-user:ec2-user /home/ec2-user/hourly_update.log
touch /home/ec2-user/monthly_event_pipeline.log
chown ec2-user:ec2-user /home/ec2-user/monthly_event_pipeline.log
touch /home/ec2-user/full_event_pipeline.log
chown ec2-user:ec2-user /home/ec2-user/full_event_pipeline.log

############################################
# Configure CloudWatch Agent
############################################
cat <<EOT > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/home/ec2-user/backend.log",
            "log_group_name": "${log_group_name}",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/home/ec2-user/daily_update.log",
            "log_group_name": "${log_group_name}",
            "log_stream_name": "{instance_id}-daily-update"
          },
          {
            "file_path": "/home/ec2-user/hourly_update.log",
            "log_group_name": "${log_group_name}",
            "log_stream_name": "{instance_id}-hourly-update"
          },
          {
            "file_path": "/home/ec2-user/monthly_event_pipeline.log",
            "log_group_name": "${log_group_name}",
            "log_stream_name": "{instance_id}-monthly-event-pipeline"
          },
          {
            "file_path": "/home/ec2-user/full_event_pipeline.log",
            "log_group_name": "${log_group_name}",
            "log_stream_name": "{instance_id}-full-event-pipeline"
          }
        ]
      }
    }
  }
}
EOT

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s

############################################
# Create backend runner script for SSM/scheduler
############################################
cat <<'EOF' > /home/ec2-user/run_backend.sh
#!/bin/bash
/usr/bin/docker pull zihan123/chronostock-backend:latest
/usr/bin/docker rm -f chronostock-backend || true
/usr/bin/docker run -d \
  --name chronostock-backend \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file /home/ec2-user/backend.env \
  zihan123/chronostock-backend:latest
EOF
chmod +x /home/ec2-user/run_backend.sh
chown ec2-user:ec2-user /home/ec2-user/run_backend.sh

cat <<'EOF' > /home/ec2-user/run_daily_update.sh
#!/bin/bash
set -e
/usr/bin/docker pull zihan123/chronostock-backend:latest
/usr/bin/docker run --rm \
  --env-file /home/ec2-user/backend.env \
  -e DAILY_UPDATE_TICKERS="AMZN,TSLA,GOOGL,META,AAPL,MSFT,NVDA" \
  zihan123/chronostock-backend:latest \
  python -m app.pipelines.run_daily_update
EOF
chmod +x /home/ec2-user/run_daily_update.sh
chown ec2-user:ec2-user /home/ec2-user/run_daily_update.sh

cat <<'EOF' > /home/ec2-user/run_hourly_update.sh
#!/bin/bash
set -e
/usr/bin/docker pull zihan123/chronostock-backend:latest
/usr/bin/docker run --rm \
  --env-file /home/ec2-user/backend.env \
  -e DAILY_UPDATE_TICKERS="AMZN,TSLA,GOOGL,META,AAPL,MSFT,NVDA" \
  zihan123/chronostock-backend:latest \
  python -m app.pipelines.run_hourly_update
EOF
chmod +x /home/ec2-user/run_hourly_update.sh
chown ec2-user:ec2-user /home/ec2-user/run_hourly_update.sh

cat <<'EOF' > /home/ec2-user/run_monthly_event_pipeline.sh
#!/bin/bash
set -e
set -a
source /home/ec2-user/backend.env
set +a
/usr/bin/docker pull zihan123/chronostock-backend:latest
/usr/bin/docker run --rm \
  --env-file /home/ec2-user/backend.env \
  -e PIPELINE_END_DATE="$(date -u +%F)" \
  zihan123/chronostock-backend:latest \
  python -m app.pipelines.run_monthly_event_pipeline --tickers "$${MONTHLY_EVENT_TICKERS}"
EOF
chmod +x /home/ec2-user/run_monthly_event_pipeline.sh
chown ec2-user:ec2-user /home/ec2-user/run_monthly_event_pipeline.sh

cat <<'EOF' > /home/ec2-user/run_full_event_pipeline.sh
#!/bin/bash
set -euo pipefail
set -a
source /home/ec2-user/backend.env
set +a

ENV_FILE="$${ENV_FILE:-/home/ec2-user/backend.env}"
IMAGE="$${IMAGE:-zihan123/chronostock-backend:latest}"
BENCHMARK_TICKER="$${BENCHMARK_TICKER:-^DJI}"
DEFAULT_TICKERS="AMZN,TSLA,GOOGL,META,AAPL,MSFT,NVDA"
TICKERS="$${TICKERS:-$${MONTHLY_EVENT_TICKERS:-$DEFAULT_TICKERS}}"
START_DATE="$${START_DATE:-$(date -u -d '5 years ago' +%F)}"
END_DATE="$${END_DATE:-$(date -u +%F)}"
POLYGON_TIMEOUT_SECONDS="$${POLYGON_TIMEOUT_SECONDS:-60}"
POLYGON_MAX_RETRIES="$${POLYGON_MAX_RETRIES:-3}"
POLYGON_RETRY_SLEEP_SECONDS="$${POLYGON_RETRY_SLEEP_SECONDS:-15}"

/usr/bin/docker pull "$IMAGE"

/usr/bin/docker run --rm \
  --env-file "$ENV_FILE" \
  "$IMAGE" \
  python -c "from app.pipelines.data_ingestion import get_stockprice; get_stockprice('$BENCHMARK_TICKER', '$START_DATE', '$END_DATE', save_db=False, save_local=True)"

/usr/bin/docker run --rm \
  --env-file "$ENV_FILE" \
  -e POLYGON_TIMEOUT_SECONDS="$POLYGON_TIMEOUT_SECONDS" \
  -e POLYGON_MAX_RETRIES="$POLYGON_MAX_RETRIES" \
  -e POLYGON_RETRY_SLEEP_SECONDS="$POLYGON_RETRY_SLEEP_SECONDS" \
  "$IMAGE" \
  python -u -m app.pipelines.data_ingestion --tickers "$TICKERS" --start-date "$START_DATE" --end-date "$END_DATE"

/usr/bin/docker run --rm \
  --env-file "$ENV_FILE" \
  "$IMAGE" \
  python -u -m app.pipelines.data_cleaning --tickers "$TICKERS"

IFS=',' read -r -a TICKER_ARRAY <<< "$TICKERS"
for ticker in "$${TICKER_ARRAY[@]}"; do
  ticker="$${ticker//[[:space:]]/}"
  if [[ -z "$ticker" ]]; then
    continue
  fi

  /usr/bin/docker run --rm \
    --env-file "$ENV_FILE" \
    "$IMAGE" \
    python -m app.pipelines.run_s3_event_pipeline --ticker "$ticker" --start-date "$START_DATE" --end-date "$END_DATE"
done
EOF
chmod +x /home/ec2-user/run_full_event_pipeline.sh
chown ec2-user:ec2-user /home/ec2-user/run_full_event_pipeline.sh

cat <<'EOF' > /etc/systemd/system/full-event-pipeline.service
[Unit]
Description=Run ChronoStock full event pipeline on boot
After=docker.service network-online.target
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=ec2-user
Group=ec2-user
ExecStart=/home/ec2-user/run_full_event_pipeline.sh
StandardOutput=append:/home/ec2-user/full_event_pipeline.log
StandardError=append:/home/ec2-user/full_event_pipeline.log

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable full-event-pipeline.service

cat <<'EOF' > /home/ec2-user/setup_hourly_cloudwatch.sh
#!/bin/bash
set -e

LOG_GROUP="/stock-pipeline/app"
CW_CONFIG="/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json"
CW_CTL="/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl"

echo "Ensuring hourly log file exists..."
touch /home/ec2-user/hourly_update.log
chown ec2-user:ec2-user /home/ec2-user/hourly_update.log

echo "Writing CloudWatch Agent config..."
sudo tee "$CW_CONFIG" > /dev/null <<EOF_INNER
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/home/ec2-user/backend.log",
            "log_group_name": "$${LOG_GROUP}",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/home/ec2-user/daily_update.log",
            "log_group_name": "$${LOG_GROUP}",
            "log_stream_name": "{instance_id}-daily-update"
          },
          {
            "file_path": "/home/ec2-user/hourly_update.log",
            "log_group_name": "$${LOG_GROUP}",
            "log_stream_name": "{instance_id}-hourly-update"
          }
        ]
      }
    }
  }
}
EOF_INNER

echo "Reloading CloudWatch Agent..."
sudo "$CW_CTL" \
  -a fetch-config \
  -m ec2 \
  -c "file:$${CW_CONFIG}" \
  -s

echo "Running hourly update once for verification..."
bash /home/ec2-user/run_hourly_update.sh

echo "Done."
echo "Check CloudWatch Logs group: $${LOG_GROUP}"
echo "Expected stream name suffix: -hourly-update"
EOF
chmod +x /home/ec2-user/setup_hourly_cloudwatch.sh
chown ec2-user:ec2-user /home/ec2-user/setup_hourly_cloudwatch.sh

cat <<'EOF' > /home/ec2-user/setup_https.sh
#!/bin/bash
set -e

DOMAIN="api.chronostock.shop"
UPSTREAM="http://127.0.0.1:8000"

echo "Installing nginx and certbot..."
sudo dnf install -y nginx certbot python3-certbot-nginx

echo "Enabling nginx..."
sudo systemctl enable --now nginx

echo "Writing nginx config..."
sudo tee /etc/nginx/conf.d/chronostock.conf > /dev/null <<EOF_INNER
server {
    listen 80;
    server_name $${DOMAIN};

    location / {
        proxy_pass $${UPSTREAM};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF_INNER

echo "Testing nginx config..."
sudo nginx -t

echo "Reloading nginx..."
sudo systemctl reload nginx

echo "Requesting HTTPS certificate..."
sudo certbot --nginx -d $${DOMAIN} --non-interactive --agree-tos -m ${certbot_email} --redirect

echo "Done."
echo "Test these URLs:"
echo "http://$${DOMAIN}/docs"
echo "https://$${DOMAIN}/docs"
EOF
chmod +x /home/ec2-user/setup_https.sh
chown ec2-user:ec2-user /home/ec2-user/setup_https.sh

############################################
# Initial backend deploy
############################################
/home/ec2-user/run_backend.sh >> /home/ec2-user/backend.log 2>&1

touch /var/lib/cloud/instance/.user_data_done
