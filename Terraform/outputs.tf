output "ec2_public_ip" {
  value = module.ec2.public_ip
}

output "rds_host" {
  value = module.rds.db_host
}

output "rds_port" {
  value = module.rds.db_port
}
