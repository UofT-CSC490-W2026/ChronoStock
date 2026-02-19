terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.32"
    }
  }

  required_version = ">= 1.2"
}

provider "aws" {
  region = "ca-central-1"
}
