terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region = var.region
}

module "compute" {
  source           = "./modules/compute"
  region           = var.region
  ami              = var.ami
  instance_type    = var.instance_type
  key_name         = var.key_name
  environment      = var.environment
  prometheus_token = var.prometheus_token
  vault_addr       = var.vault_addr
  vault_token      = var.vault_token
}

output "instance_ip" {
  value = module.compute.instance_ip
}
