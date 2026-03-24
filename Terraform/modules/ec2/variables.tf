variable "ami" {
  description = "AMI ID for EC2 instance"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t2.micro"
}

variable "key_name" {
  description = "SSH key pair name"
  type        = string
}

variable "security_group_ids" {
  description = "List of security group IDs"
  type        = list(string)
}

variable "root_block" {
  description = "Root block device configuration"
  type = object({
    size      = number
    type      = string
    encrypted = bool
  })

  default = {
    size      = 8
    type      = "gp3"
    encrypted = true
  }
}

variable "tags" {
  description = "Tags for EC2 instance"
  type        = map(string)

  default = {
    Project = "news-pipeline"
    Owner   = "zihan"
  }
}

variable "db_host" {
  type = string
}

variable "db_name" {
  type = string
}

variable "db_port" {
  description = "RDS port"
  type        = number
}

variable "aws_region" {
  description = "AWS region for the EC2 app and CloudWatch agent"
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group name for pipeline logs"
  type        = string
}

output "ec2_role_name" {
  value = aws_iam_role.ec2_role.name
}

variable "public_subnet_id" {
  description = "Public subnet for EC2"
  type        = string
}

variable "secret_name" {
  description = "Secrets Manager secret name for RDS credentials"
  type        = string
}

variable "frontend_url" {
  description = "Frontend origin allowed by backend CORS"
  type        = string
}

variable "secret_policy_arn" {
  description = "IAM policy ARN allowing access to Secrets Manager"
  type        = string
}

variable "s3_policy_arn" {
  description = "IAM policy ARN allowing access to the app S3 bucket"
  type        = string
}
