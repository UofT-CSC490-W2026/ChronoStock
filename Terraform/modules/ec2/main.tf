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

resource "aws_iam_role_policy_attachment" "secret_access" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = var.secret_policy_arn
}

resource "aws_iam_role_policy_attachment" "s3_access" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = var.s3_policy_arn
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "cloudwatch_logs" {
  name = "stock-pipeline-cloudwatch-logs"
  role = aws_iam_role.ec2_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:CreateLogGroup",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "time_sleep" "iam_propagation" {
  depends_on = [
    aws_iam_instance_profile.ec2_profile,
    aws_iam_role_policy_attachment.secret_access,
    aws_iam_role_policy_attachment.s3_access,
    aws_iam_role_policy_attachment.ssm_core,
    aws_iam_role_policy.cloudwatch_logs
  ]

  create_duration = "30s"
}

resource "aws_instance" "app" {
  ami                  = var.ami
  instance_type        = var.instance_type
  key_name             = var.key_name
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name

  subnet_id = var.public_subnet_id

  vpc_security_group_ids = var.security_group_ids

  root_block_device {
    volume_size = var.root_block.size
    volume_type = var.root_block.type
    encrypted   = var.root_block.encrypted
  }

  user_data = templatefile("${path.module}/scripts/user_data.sh", {
    aws_region     = var.aws_region
    log_group_name = var.log_group_name
    secret_name    = var.secret_name
    frontend_url   = var.frontend_url
  })

  tags = var.tags

  depends_on = [
    time_sleep.iam_propagation
  ]
}

resource "aws_eip" "app_eip" {
  domain = "vpc"
}

resource "aws_eip_association" "app_eip_assoc" {
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app_eip.id
}
