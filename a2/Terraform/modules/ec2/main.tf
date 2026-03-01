resource "aws_iam_role" "ec2_role" {
  name = "stock-pipeline-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "stock-pipeline-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

resource "aws_instance" "app" {
  ami           = var.ami
  instance_type = var.instance_type
  key_name      = var.key_name
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name

  vpc_security_group_ids = var.security_group_ids

  root_block_device {
    volume_size = var.root_block.size
    volume_type = var.root_block.type
    encrypted   = var.root_block.encrypted
  }

  user_data = templatefile("${path.module}/scripts/user_data.sh", {
    db_port = var.db_port
    db_host = var.db_host
    db_name = var.db_name
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
