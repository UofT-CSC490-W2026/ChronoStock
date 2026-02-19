resource "aws_instance" "app" {
  ami           = var.ami
  instance_type = var.instance_type
  key_name      = var.key_name

  vpc_security_group_ids = var.security_group_ids

  root_block_device {
    volume_size = var.root_block.size
    volume_type = var.root_block.type
    encrypted   = var.root_block.encrypted
  }

  user_data = templatefile("${path.module}/scripts/user_data.sh", {
    db_host     = var.db_host
    db_name     = var.db_name
    db_user     = var.db_user
    db_password = var.db_password
  })

  tags = var.tags
}

resource "aws_eip" "app_eip" {
  domain = "vpc"
}

resource "aws_eip_association" "app_eip_assoc" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app_eip.id
}
