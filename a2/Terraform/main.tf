# default VPC and subnets
data "aws_subnets" "default" {
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}


data "aws_vpc" "default" {
  default = true
}

# AMI
data "aws_ami" "amazon_linux" {
  most_recent = true

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  owners = ["137112412989"]
}

# ----------------------
# Security Group Module
# ----------------------

module "security_group" {
  source = "./modules/security_group"

  vpc_id = module.vpc.vpc_id
}

# ----------------------
# VPC Module
# ----------------------

module "vpc" {
  source = "./modules/vpc"
}

# ----------------------
# Secrets Module
# ----------------------
module "secrets" {
  source = "./modules/secrets"

  secret_name = var.secret_name

  db_username     = var.db_username
  db_password     = var.db_password
  db_host         = module.rds.db_host
  db_name         = var.db_name
  polygon_api_key = var.polygon_api_key
}

resource "aws_iam_policy" "secrets_policy" {
  name = "chrono-stock-secrets-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = module.secrets.secret_arn
    }]
  })
}


# ----------------------
# S3 Module
# ----------------------
module "s3" {
  source      = "./modules/s3"
  bucket_name = var.bucket_name
}

resource "aws_iam_policy" "s3_limited_policy" {
  name = "stock-pipeline-s3-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = module.s3.bucket_arn
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${module.s3.bucket_arn}/*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "pipeline_logs" {
  name              = "/stock-pipeline/app"
  retention_in_days = 14
}

resource "aws_iam_role" "scheduler_role" {
  name = "stock-pipeline-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_ssm" {
  name = "stock-pipeline-scheduler-ssm"
  role = aws_iam_role.scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:SendCommand"
      Resource = "*"
    }]
  })
}

# ----------------------
# EC2
# ----------------------
module "ec2" {
  source = "./modules/ec2"

  ami      = data.aws_ami.amazon_linux.id
  key_name = var.key_name

  public_subnet_id   = module.vpc.public_subnet_ids[0]
  security_group_ids = [module.security_group.ec2_sg_id]

  db_host        = module.rds.db_host
  db_port        = module.rds.db_port
  db_name        = var.db_name
  aws_region     = var.aws_region
  log_group_name = aws_cloudwatch_log_group.pipeline_logs.name
  secret_name    = var.secret_name
  tags = {
    Name = "stock-pipeline-app"
  }
}

# ----------------------
# RDS
# ----------------------
module "rds" {
  source = "./modules/rds"

  rds_sg_id          = module.security_group.rds_sg_id
  private_subnet_ids = module.vpc.private_subnet_ids

  db_username = var.db_username
  db_password = var.db_password
  db_name     = var.db_name
}

# ----------------------
# Attach IAM Policies
# ----------------------
resource "aws_iam_role_policy_attachment" "attach_secret_policy" {
  role       = module.ec2.ec2_role_name
  policy_arn = aws_iam_policy.secrets_policy.arn
}

resource "aws_iam_role_policy_attachment" "attach_s3_policy" {
  role       = module.ec2.ec2_role_name
  policy_arn = aws_iam_policy.s3_limited_policy.arn
}

resource "aws_iam_role_policy_attachment" "attach_ssm_policy" {
  role       = module.ec2.ec2_role_name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "cloudwatch_logs" {
  name = "stock-pipeline-cloudwatch-logs"
  role = module.ec2.ec2_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:CreateLogGroup",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_cloudwatch_metric_alarm" "high_cpu" {
  alarm_name          = "ec2-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Alarm when EC2 CPU stays above 80 percent"

  dimensions = {
    InstanceId = module.ec2.instance_id
  }
}

resource "aws_scheduler_schedule" "daily_pipeline" {
  name                         = "stock-pipeline-daily"
  schedule_expression          = "cron(30 19 * * ? *)"
  schedule_expression_timezone = "America/Toronto"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ssm:sendCommand"
    role_arn = aws_iam_role.scheduler_role.arn

    input = jsonencode({
      DocumentName = "AWS-RunShellScript"
      InstanceIds  = [module.ec2.instance_id]
      Parameters = {
        commands = [
          "/home/ec2-user/run_pipeline.sh >> /home/ec2-user/pipeline.log 2>&1"
        ]
      }
    })
  }
}
