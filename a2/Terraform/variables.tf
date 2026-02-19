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

variable "db_user" {
  type = string
}


