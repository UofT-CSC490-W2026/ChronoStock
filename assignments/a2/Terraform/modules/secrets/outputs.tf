output "secret_arn" {
  value = aws_secretsmanager_secret.rds_secret.arn
}