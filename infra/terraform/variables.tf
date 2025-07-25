variable "region" { default = "us-east-1" }
variable "ami" { description = "AMI ID" }
variable "instance_type" { default = "t3.micro" }
variable "key_name" { description = "SSH key name" }
variable "environment" { default = "dev" }
variable "prometheus_token" { sensitive = true }
variable "vault_addr" { description = "Vault server address" }
variable "vault_token" { sensitive = true }
