resource "aws_db_instance" "db" {
  identifier             = "stock-pipeline-db"

  engine                 = "postgres"
  engine_version         = "17.6"

  instance_class         = var.db_instance_class
  allocated_storage      = var.db_allocated_storage

  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password

  publicly_accessible    = true
  storage_encrypted      = true
  auto_minor_version_upgrade = true

  backup_retention_period    = 7
  skip_final_snapshot        = false
  final_snapshot_identifier = "stock-pipeline-final-snapshot-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  vpc_security_group_ids = [var.rds_sg_id]
  db_subnet_group_name   = var.db_subnet_group_name
}
