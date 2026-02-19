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

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y docker
              systemctl start docker
              systemctl enable docker

              # pull Docker image from ECR (replace with your actual image URI)
              docker pull zihan123/stock-pipeline:latest

              # run Docker container with environment variables for DB connection
              docker run -d \
                -p 8000:8000 \
                -e DB_HOST=${var.db_host} \
                -e DB_NAME=${var.db_name} \
                -e DB_USER=${var.db_user} \
                -e DB_PASSWORD=${var.db_password} \
                zihan123/stock-pipeline:latest
              EOF


  tags = var.tags
}
