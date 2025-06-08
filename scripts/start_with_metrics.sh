#!/bin/bash

# Start metrics server in background and launch orchestrator.
# Metrics server listens on METRICS_PORT (default 8000).

set -euo pipefail

python3.11 -m core.metrics --port "${METRICS_PORT:-8000}" &
python3.11 -m core.orchestrator --config=config.yaml "$@"
