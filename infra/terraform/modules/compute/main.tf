variable "region" {}
variable "ami" {}
variable "instance_type" { default = "t3.micro" }
variable "key_name" {}
variable "environment" { default = "dev" }
variable "prometheus_token" { sensitive = true }
variable "secret_env" { sensitive = true }

resource "aws_security_group" "mevog" {
  name        = "mevog-${var.environment}"
  description = "MEV-OG access"

  ingress {
    description = "RPC"
    from_port   = 8545
    to_port     = 8545
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Prometheus"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "mevog" {
  ami           = var.ami
  instance_type = var.instance_type
  key_name      = var.key_name
  security_groups = [aws_security_group.mevog.id]
  tags = {
    Name = "mevog-${var.environment}"
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    PROMETHEUS_TOKEN = var.prometheus_token
    SECRET_ENV       = var.secret_env
  })
}

output "instance_ip" {
  value = aws_instance.mevog.public_ip
}
