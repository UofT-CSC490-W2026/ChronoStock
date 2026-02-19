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

      # user_data = <<-EOF
      #   #!/bin/bash

      #   yum update -y
      #   yum install -y docker

      #   systemctl start docker
      #   systemctl enable docker

      #   usermod -aG docker ec2-user

      #   docker pull zihan123/stock-pipeline:latest

      #   docker run -d \
      #     --name stock-pipeline \
      #     --restart unless-stopped \
      #     -p 8000:8000 \
      #     -e RDS_HOST=${var.db_host} \
      #     -e RDS_DB=${var.db_name} \
      #     -e RDS_USER=${var.db_user} \
      #     -e RDS_PASS=${var.db_password} \
      #     -e RDS_PORT=5432 \
      #     zihan123/stock-pipeline:latest
      #   EOF

  tags = var.tags
}
