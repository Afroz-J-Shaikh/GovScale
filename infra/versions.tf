terraform {
  required_version = ">= 1.10"

  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }

  # Remote state so GitHub Actions and your laptop share one source of truth.
  # Create the bucket once (see infra/README.md step 0), then edit the name below.
  backend "s3" {
    bucket       = "govscale-tfstate"
    key          = "govscale/terraform.tfstate"
    region       = "ap-south-1"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "govscale"
      ManagedBy = "terraform"
    }
  }
}
