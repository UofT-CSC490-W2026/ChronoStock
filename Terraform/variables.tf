variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "key_name" {
  description = "SSH key name"
  type        = string
}

variable "ec2_instance_type" {
  description = "EC2 instance type for the backend host"
  type        = string
  default     = "t2.micro"
}

variable "ec2_root_volume_size" {
  description = "EC2 root volume size in GB"
  type        = number
  default     = 8
}

variable "ec2_root_volume_type" {
  description = "EC2 root volume type"
  type        = string
  default     = "gp3"
}

variable "ec2_root_volume_encrypted" {
  description = "Whether the EC2 root volume is encrypted"
  type        = bool
  default     = true
}

variable "db_name" {
  type = string
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "bucket_name" {
  type = string
}

variable "pipeline_source_bucket_name" {
  description = "Optional extra S3 bucket that EC2 pipeline jobs can read/write."
  type        = string
  default     = ""
}

variable "db_username" {
  type = string
}

variable "polygon_api_key" {
  sensitive = true
}

variable "llm_api_key" {
  description = "API key used by the monthly event LLM pipeline"
  type        = string
  sensitive   = true
}

variable "fred_api_key" {
  description = "FRED API key used by macro endpoints"
  type        = string
  sensitive   = true
}

variable "aws_bearer_token_bedrock" {
  description = "AWS Bedrock API key used by market analysis"
  type        = string
  sensitive   = true
}

variable "bedrock_model_id" {
  description = "Bedrock model or inference profile ID used by market analysis"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "llm_model" {
  description = "LLM model used by the monthly event pipeline"
  type        = string
  default     = "deepseek-chat"
}

variable "llm_base_url" {
  description = "OpenAI-compatible base URL used by the monthly event pipeline"
  type        = string
  default     = "https://api.deepseek.com"
}

variable "monthly_event_tickers" {
  description = "Comma-separated ticker list for the monthly event pipeline"
  type        = string
  default     = "AMZN,TSLA,GOOGL,META,AAPL,MSFT,NVDA"
}

variable "jwt_secret_key" {
  description = "JWT signing secret for backend auth"
  type        = string
  sensitive   = true
}

variable "secret_name" {
  type = string
}

variable "aws_region" {
  description = "AWS region for deployed resources and EC2 runtime config"
  type        = string
  default     = "ca-central-1"
}

variable "frontend_url" {
  description = "Allowed frontend origin for backend CORS"
  type        = string
}

variable "certbot_email" {
  description = "Email address used by certbot for HTTPS certificate registration"
  type        = string
}
