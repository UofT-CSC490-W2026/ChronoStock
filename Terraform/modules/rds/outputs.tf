output "db_instance_id" {
  description = "RDS instance ID"
  value       = aws_db_instance.db.id
}

output "db_endpoint" {
  description = "RDS endpoint address"
  value       = aws_db_instance.db.endpoint
}

output "db_port" {
  description = "RDS port"
  value       = aws_db_instance.db.port
}

output "db_name" {
  description = "Database name"
  value       = aws_db_instance.db.db_name
}

output "db_username" {
  description = "Database master username"
  value       = aws_db_instance.db.username
}

output "db_arn" {
  description = "RDS ARN"
  value       = aws_db_instance.db.arn
}
