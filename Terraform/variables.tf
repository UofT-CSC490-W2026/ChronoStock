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
