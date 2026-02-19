#!/bin/bash
set -e

# Update system
dnf update -y

# Install Docker
dnf install -y docker
systemctl enable docker
systemctl start docker

# Wait for Docker
until docker info > /dev/null 2>&1; do
  sleep 2
done

usermod -aG docker ec2-user

# Create env file
cat <<EOT > /home/ec2-user/pipeline.env
RDS_HOST=${db_host}
RDS_DB=${db_name}
RDS_USER=${db_user}
RDS_PASS=${db_password}
RDS_PORT=5432
EOT

chown ec2-user:ec2-user /home/ec2-user/pipeline.env

# Pull image
docker pull zihan123/stock-pipeline:latest

# Install cron
dnf install -y cronie
systemctl enable crond
systemctl start crond

# Setup cron job
crontab -l -u ec2-user 2>/dev/null | grep -v stock-pipeline > /tmp/mycron || true
echo "0 17 * * * /usr/bin/docker run --rm --env-file /home/ec2-user/pipeline.env zihan123/stock-pipeline:latest >> /home/ec2-user/pipeline.log 2>&1" >> /tmp/mycron
crontab -u ec2-user /tmp/mycron
rm /tmp/mycron
