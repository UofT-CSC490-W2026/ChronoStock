#!/bin/bash
set -e

# Exit if user data has already run
[ -f /var/lib/cloud/instance/.user_data_done ] && exit 0

############################################
# Install all packages before starting services
############################################
dnf install -y docker jq amazon-cloudwatch-agent amazon-ssm-agent

# Start services
systemctl enable --now docker
systemctl enable --now amazon-ssm-agent

# Wait for Docker to be ready
until docker info > /dev/null 2>&1; do
  sleep 2
done

usermod -aG docker ec2-user

############################################
# Fetch DB credentials from Secrets Manager
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

cat <<EOT > /home/ec2-user/pipeline.env
RDS_HOST=$DB_HOST
RDS_DB=$DB_NAME
RDS_PORT=$DB_PORT
RDS_USER=$DB_USER
RDS_PASS=$DB_PASS
AWS_REGION=${aws_region}
EOT

chown ec2-user:ec2-user /home/ec2-user/pipeline.env

############################################
# Log file
############################################
touch /home/ec2-user/pipeline.log
chown ec2-user:ec2-user /home/ec2-user/pipeline.log

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
            "file_path": "/home/ec2-user/pipeline.log",
            "log_group_name": "${log_group_name}",
            "log_stream_name": "{instance_id}"
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
# Pull Docker image
############################################
docker pull zihan123/stock-pipeline:latest

############################################
# Create pipeline runner script for SSM
############################################
cat <<'EOF' > /home/ec2-user/run_pipeline.sh
#!/bin/bash
/usr/bin/docker pull zihan123/stock-pipeline:latest
/usr/bin/docker run --rm --network host \
  --env-file /home/ec2-user/pipeline.env \
  zihan123/stock-pipeline:latest
EOF
chmod +x /home/ec2-user/run_pipeline.sh
chown ec2-user:ec2-user /home/ec2-user/run_pipeline.sh

############################################
# Initial load: ingestion → cleaning
############################################
docker run --rm --network host \
  --env-file /home/ec2-user/pipeline.env \
  zihan123/stock-pipeline:latest python data_ingestion.py \
  >> /home/ec2-user/pipeline.log 2>&1 || true

docker run --rm --network host \
  --env-file /home/ec2-user/pipeline.env \
  zihan123/stock-pipeline:latest python data_cleaning.py \
  >> /home/ec2-user/pipeline.log 2>&1 || true

touch /var/lib/cloud/instance/.user_data_done
