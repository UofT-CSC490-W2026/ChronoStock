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

# RDS Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "stock-pipeline-db-subnet"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name = "stock-pipeline-db-subnet"
  }
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

}

# ----------------------
# RDS Module
# ----------------------

module "rds" {
  source = "./modules/rds"

  rds_sg_id             = module.security_group.rds_sg_id
  db_subnet_group_name  = aws_db_subnet_group.main.name

  db_password = var.db_password
}

# ----------------------
# EC2 Module
# ----------------------

module "ec2" {
  source = "./modules/ec2"

  ami                = data.aws_ami.amazon_linux.id
  key_name           = var.key_name
  security_group_ids = [module.security_group.ec2_sg_id]

  db_host     = module.rds.endpoint
  db_name     = var.db_name
  db_user     = var.db_user
  db_password = var.db_password

  tags = {
    Name = "stock-pipeline-app"
  }
}
