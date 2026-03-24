variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "key_name" {
  description = "SSH key name"
  type        = string
}

variable "db_name" {
  type = string
}

variable "bucket_name" {
  type = string
}

variable "db_username" {
  type = string
}

variable "polygon_api_key" {
  sensitive = true
}

variable "secret_name" {
  type = string
}

variable "aws_region" {
  description = "AWS region for deployed resources and EC2 runtime config"
  type        = string
  default     = "ca-central-1"
}
