resource "aws_secretsmanager_secret" "rds_secret" {
  name = var.secret_name
}

resource "aws_secretsmanager_secret_version" "rds_secret_value" {
  secret_id = aws_secretsmanager_secret.rds_secret.id

  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
    host     = var.db_host
    port     = "5432"
    dbname   = var.db_name
    polygon_api_key = var.polygon_api_key
  })
}