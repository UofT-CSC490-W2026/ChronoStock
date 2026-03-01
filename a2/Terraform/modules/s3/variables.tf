variable "bucket_name" {
  description = "Name of the S3 bucket"
  type        = string
}

variable "enable_versioning" {
  description = "Enable versioning for the bucket"
  type        = bool
  default     = true
}

variable "sse_algorithm" {
  description = "Server-side encryption algorithm"
  type        = string
  default     = "AES256"
}

variable "tags" {
  description = "Tags for the S3 bucket"
  type        = map(string)

  default = {
    Project = "stock-pipeline"
    Owner   = "zihan"
  }
}