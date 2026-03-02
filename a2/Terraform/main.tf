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
  source      = "./modules/secrets"
  
  secret_name = var.secret_name

  db_username = var.db_username
  db_password = var.db_password
  db_host     = module.rds.db_host
  db_name     = var.db_name
  polygon_api_key   = var.polygon_api_key
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
  source = "./modules/s3"
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
        Action   = ["s3:GetObject","s3:PutObject"]
        Resource = "${module.s3.bucket_arn}/*"
      }
    ]
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

  db_host = module.rds.db_host
  db_port = module.rds.db_port
  db_name = var.db_name

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