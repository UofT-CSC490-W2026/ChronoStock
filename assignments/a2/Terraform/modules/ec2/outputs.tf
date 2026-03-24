output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Public IP address of EC2"
  value       = aws_instance.app.public_ip
}

output "elastic_ip" {
  description = "Elastic IP address of EC2"
  value       = aws_eip.app_eip.public_ip
}
