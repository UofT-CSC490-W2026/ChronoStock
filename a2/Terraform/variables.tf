variable "my_ip" {
  description = "Your public IP address in CIDR format"
  type        = string
}

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


