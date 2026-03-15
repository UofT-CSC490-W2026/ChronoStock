terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.32"
    }
  }

  required_version = ">= 1.2"

  backend "s3" {
    bucket         = "s3-stock-pipeline-data-dev"
    key            = "terraform/terraform.tfstate"
    region         = "ca-central-1"
    dynamodb_table = "terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = "ca-central-1"
}