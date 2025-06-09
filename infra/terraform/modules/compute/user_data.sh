#!/bin/bash
set -e
apt-get update -y
apt-get install -y docker.io
systemctl enable docker --now
cat <<EOT >/opt/mevog.env
VAULT_ADDR=${VAULT_ADDR}
VAULT_TOKEN=${VAULT_TOKEN}
PROMETHEUS_TOKEN=${PROMETHEUS_TOKEN}
EOT
