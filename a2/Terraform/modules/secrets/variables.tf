variable "db_username" {}
variable "db_password" {
  sensitive = true
}
variable "db_host" {}
variable "db_name" {}
variable "polygon_api_key" {
  sensitive = true
}