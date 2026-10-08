terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Vollständig ephemer: Lokaler State, kein S3-Backend-Overhead, 0,00 € Kosten im Ruhezustand
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "gitops-chaos-research"
      Environment = "ephemeral-lab"
      ManagedBy   = "Terraform"
    }
  }
}
