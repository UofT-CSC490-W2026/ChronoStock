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