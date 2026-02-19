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

variable "db_user" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}
