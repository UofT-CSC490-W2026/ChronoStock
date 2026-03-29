variable "db_username" {}
variable "db_password" {
  sensitive = true
}
variable "db_host" {}
variable "db_name" {}
variable "polygon_api_key" {
  sensitive = true
}
variable "llm_api_key" {
  sensitive = true
}
variable "fred_api_key" {
  sensitive = true
}
variable "aws_bearer_token_bedrock" {
  sensitive = true
}
variable "bedrock_model_id" {}
variable "jwt_secret_key" {
  sensitive = true
}

variable "secret_name" {
  description = "Name of the RDS secret"
  type        = string
}
