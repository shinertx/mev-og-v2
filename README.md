# MEV-OG

[![CI](https://img.shields.io/badge/CI-passing-brightgreen)](#)
![SPDX-License](https://img.shields.io/badge/License-MIT-blue.svg)

## Overview
MEV-OG is an AI-driven DeFi trading framework targeting cross-domain arbitrage,
liquidations and intent-based MEV. It couples on-chain bots with off-chain
mutation agents and disaster recovery pipelines.

## Architecture & Core Concepts
- **Strategies** under `strategies/` implement domain specific logic.
- **Agents** in `agents/` handle ops monitoring, founder gating and capital
  locks.
- **Core modules** under `core/` provide the transaction engine and metrics.
- **AI orchestration** lives in `ai/` for strategy mutation and voting.
- **Infrastructure** scripts in `infra/` offer chaos drills and Terraform
  modules.

## Directory Map
| Path | Purpose |
|------|---------|
| `adapters/` | Protocol connectors and scanners |
| `agents/` | Ops, gating and capital lock agents |
| `ai/` | Mutation logic and voting engine |
| `contracts/` | Solidity sources and tests |
| `core/` | Orchestrator, tx engine and metrics |
| `docs/` | Onboarding and safety guidelines |
| `infra/` | Simulation harness and Terraform configs |
| `scripts/` | CLI tools and recovery helpers |
| `sim/` | Scenario configs and fork harness |
| `tests/` | PyTest suite and Foundry wrappers |

## Environment Variables
| Name | Default | Description |
|------|---------|-------------|
| `FOUNDER_TOKEN` | `<none>` | Founder approval token |
| `VAULT_ADDR` | `<none>` | HashiCorp Vault address |
| `VAULT_TOKEN` | `<none>` | Vault API token |
| `VAULT_SECRET_PATH` | `secret/data/mevog` | Vault KV path |
| `ENABLE_METRICS` | `0` | Enable metrics server |
| `EXPORT_DIR` | `export` | DRP export directory |
| `EXPORT_LOG_FILE` | `logs/export_state.json` | Export log location |
| `DRP_ENC_KEY` | `<none>` | Optional key to encrypt exports |
| `GRAFANA_URL` | `http://localhost:3000` | Grafana endpoint |
| `GRAFANA_API_KEY` | `<none>` | Grafana API key |
| `PROMETHEUS_URL` | `http://localhost:9090` | Prometheus endpoint |
| `KILL_SWITCH_FLAG_FILE` | `./flags/kill_switch.txt` | Toggle system halt |
| `KILL_SWITCH_LOG_FILE` | `logs/kill_log.json` | Kill switch audit log |
| `KILL_SWITCH` | `0` | Emergency kill variable |
| `TRACE_ID` | `<none>` | Audit trace identifier |
| `METRICS_PORT` | `8000` | Metrics server port |
| `ERROR_LOG_FILE` | `logs/errors.log` | Error log file |
| `ROLLBACK_LOG_FILE` | `logs/rollback.log` | Rollback audit log |
| `PYTHON` | `python` | Python binary used by scripts |
| `OPENAI_API_KEY` | `<none>` | Enables online LLM audits |
| `FLASHBOTS_AUTH_KEY` | `<none>` | Key for bundle signing |
| `FLASHBOTS_RPC_URL` | `https://relay.flashbots.net` | Flashbots relay URL |
| `PRIVATE_KEY` | `<none>` | Trading key loaded via Vault |
| `PROMETHEUS_TOKEN` | `<none>` | Token for remote Prometheus push |
| `DUNE_API_KEY` | `<none>` | Dune Analytics queries |
| `WHALE_ALERT_KEY` | `<none>` | Whale Alert API key |
| `COINBASE_WS_URL` | `<none>` | Coinbase WebSocket URL |
| `CHAOS_INTERVAL` | `600` | Chaos drill interval in seconds |
| `CHAOS_ADAPTERS` | `<none>` | Target adapters for chaos |
| `CHAOS_MODES` | `<none>` | Chaos modes to enable |
| `CHAOS_SCHED_LOG` | `logs/chaos_scheduler.json` | Scheduler log file |

## Local Dev Setup
```bash
python3.11 -m pip install -r requirements.txt
cp config.example.yaml config.yaml
python3.11 scripts/load_vault_secrets.py > /tmp/env.sh
source /tmp/env.sh
```
Run `pre-commit install` once to enable lint hooks.

## Quick-Start / Testnet Guide
### Poetry
```bash
poetry install
poetry run python orchestrator_ttl.py
```
### Docker Compose
```bash
docker compose up
```
### Pool-Scanner Image
```bash
docker build -f Dockerfile.pool_scanner -t pool-scanner .
docker run -e ENABLE_METRICS=1 pool-scanner
```

## Production Checklist & Liveness
- Prometheus configuration lives in `infra/prometheus.yml`.
- Import `grafana/strategy_scoreboard.json` into Grafana.
- Health checks: `python3.11 core/orchestrator.py --health`.

## Commands Reference
- `make build|up|down|test|chaos|simulate|mutate|export|promote`
- `bash scripts/kill_switch.sh [--dry-run|--clean]`
- `bash scripts/export_state.sh`
- `bash scripts/rollback.sh --archive=<file>`
- `bash scripts/simulate_fork.sh --target=strategies/<module>`
- `python3.11 ai/promote.py`
- `python3.11 scripts/load_vault_secrets.py`

## Post-Deploy Actions
1. `bash scripts/load_vault_secrets.py` to refresh secrets.
2. `terraform apply` in `infra/terraform` if infrastructure changed.
3. `bash scripts/export_state.sh` to snapshot logs and state.

## Risk Warnings / Kill-Switch
> WARN: Operating these bots may lead to fund loss. Review kill switch
> logic in `scripts/kill_switch.sh` and tests under `tests/test_kill_switch*`.
### Audit Status & Legal Disclaimer
This repository is unaudited experimental research. Use at your own risk and
consult legal counsel before live deployment.

## Upgrade Path & Versioning
Contracts use the `PauseKill` pattern for upgrade safety. Follow SemVer for
application releases and run migrations via Foundry scripts.

## Testing & CI Matrix
Run `pytest -v`, `foundry test` and `bash scripts/simulate_fork.sh`. CI workflows
should mirror this matrix when added.

## Contributing & FAQ
Pull requests are welcome. Run `pre-commit run --files <changed>` and ensure all
unit tests pass. See `docs/ONBOARDING.md` for details.

## License
Licensed under the MIT License. See [LICENSE](LICENSE).

✅ README draft complete
