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
SECRET_JSON=$(aws secretsmanager get-secret-value \
  --secret-id ${secret_name} \
  --region ${aws_region} \
  --query SecretString \
  --output text)

DB_USER=$(echo "$SECRET_JSON" | jq -r '.username')
DB_PASS=$(echo "$SECRET_JSON" | jq -r '.password')
DB_HOST=$(echo "$SECRET_JSON" | jq -r '.host')
DB_NAME=$(echo "$SECRET_JSON" | jq -r '.dbname')
DB_PORT=$(echo "$SECRET_JSON" | jq -r '.port')
JWT_SECRET=$(echo "$SECRET_JSON" | jq -r '.jwt_secret_key')

DATABASE_URL="postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME"

cat <<EOT > /home/ec2-user/backend.env
DB_BACKEND=postgres
DATABASE_URL=$DATABASE_URL
JWT_SECRET_KEY=$JWT_SECRET
FRONTEND_URL=${frontend_url}
EOT

chown ec2-user:ec2-user /home/ec2-user/backend.env

############################################
# Log file
############################################
touch /home/ec2-user/backend.log
chown ec2-user:ec2-user /home/ec2-user/backend.log
touch /home/ec2-user/daily_update.log
chown ec2-user:ec2-user /home/ec2-user/daily_update.log

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
  -e DAILY_UPDATE_TICKERS="AAPL,MSFT,NVDA,TSLA" \
  zihan123/chronostock-backend:latest \
  python -m app.run_daily_update
EOF
chmod +x /home/ec2-user/run_daily_update.sh
chown ec2-user:ec2-user /home/ec2-user/run_daily_update.sh

############################################
# Initial backend deploy
############################################
/home/ec2-user/run_backend.sh >> /home/ec2-user/backend.log 2>&1

touch /var/lib/cloud/instance/.user_data_done
