# mev-og-v2

## Mission

MEV-OG is an AI-native, adversarial crypto trading system built to compound $5K → $10M+ via simulation-first Maximal Extractable Value (MEV), cross-domain arbitrage, liquidations, and flash loan exploitation.

> Fully autonomous. AI-CTO operated. Founder-controlled capital gates only.

---

## System Architecture

- **Language:** Rust (execution bots), Python (AI orchestration, analysis)
- **Infra:** Docker, Terraform, GitHub Actions CI/CD
- **Simulation/Test:** Foundry/Hardhat, Anvil forked-mainnet, chaos sim
- **Monitoring:** Prometheus, Grafana, Discord/Telegram bot alerts
- **AI/LLM:** Codex (codegen, mutation), GPT (audit, anomaly detection)
- **Online Audit:** `AuditAgent.run_online_audit` uses OpenAI GPT when `OPENAI_API_KEY` is set
- **Security:** Kill switch, circuit breakers, replay defense, key rotation
- **Recovery:** DRP + 1-hour restore snapshot from logs/state

---

## Modules

| Module | Status | Description |
|--------|--------|-------------|
| `strategies/cross_domain_arb` | 🚧 In progress | Cross-rollup + L1-L2 arbitrage execution bot |
| `strategies/cross_rollup_superbot` | 🚧 In progress | Advanced cross-rollup sandwich/arb with DRP and mutation |
| `infra/sim_harness` | ✅ | Simulates forks, chaos, and tx latency/failure |
| `ai/mutator` | ✅ | Self-prunes, mutates, and re-tunes strategies |
| `ai/mutator/main.py` | ✅ | Orchestrates AI mutation cycles and audit-driven promotion |
| `ai/promote.py` | ✅ | Handles founder-gated promotion and rollback |
| `core/tx_engine` | 🚧 | Gas/timing-safe tx builder with kill switch logic |

---

## Live Rules & Guarantees

- No code deploys without passing forked sim + chaos test.
- All modules are self-logging, hot-swappable, and DRP-recoverable.
- No key access, scaling, or mutation without founder sign-off.
- One-command audit export available (`scripts/export_state.sh`).

---

## How to Run

```bash
# Install dependencies
poetry install
docker compose up

# Run local fork simulation
foundry anvil --fork-url $MAINNET_RPC --fork-block-number <block>

# Run tests
pytest -v
# Run a mutation cycle
python ai/mutator/main.py --logs-dir logs
```

### Environment Configuration

Set the following variables before running cross-domain arbitrage modules and `cross_rollup_superbot`:

```
RPC_ETHEREUM_URL=<https://mainnet.ethereum.org>
RPC_ARBITRUM_URL=<https://arbitrum.rpc>
RPC_OPTIMISM_URL=<https://optimism.rpc>
POOL_ETHEREUM=0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8
POOL_ARBITRUM=0xb3f8e4262c5bfcc0a304143cfb33c7a9a64e0fe0
POOL_OPTIMISM=0x85149247691df622eaf1a8bd0c4bd90d38a83a1f
ARB_ALERT_WEBHOOK=<https://discord-or-telegram-webhook>
BRIDGE_COST_ETHEREUM_ARBITRUM=0.0005
```

Update these values when integrating new assets or networks.
Bridge cost variables (e.g., ``BRIDGE_COST_ETHEREUM_ARBITRUM``) control the assumed fee when moving funds across rollups for `cross_rollup_superbot`.

### cross_domain_arb Runbook

```bash
# Start metrics server
python -m core.metrics &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/cross_domain_arb
# Run mutation cycle (updates threshold)
python ai/mutator/main.py --logs-dir logs
# Export DRP snapshot
bash scripts/export_state.sh
```

`cross_domain_arb` writes structured logs to `logs/cross_domain_arb.json` and
errors to `logs/errors.log`. DRP state files are controlled by the
`CROSS_ARB_STATE_PRE`, `CROSS_ARB_STATE_POST`, `CROSS_ARB_TX_PRE` and
`CROSS_ARB_TX_POST` environment variables. Metrics are served on
`http://localhost:8000/metrics` for Prometheus to scrape.

### cross_rollup_superbot Runbook

```bash
# Start metrics server
python -m core.metrics &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/cross_rollup_superbot
# Run a mutation and audit cycle
python ai/mutator/main.py --logs-dir logs
# Export DRP snapshot and rollback if needed
bash scripts/export_state.sh
bash scripts/rollback.sh --archive=<exported-archive>
```

`cross_rollup_superbot` logs to `logs/cross_rollup_superbot.json` and shares the
common error log `logs/errors.log`. Metrics are scraped from the same
`/metrics` endpoint.

## CI/CD & Canary Deployment

GitHub Actions workflow `main.yml` runs linting, typing, tests, fork simulations and DRP checks on every push and pull request. Each batch is tagged `canary-<sha>-<date>` and must pass the full suite. Promotion to production requires `FOUNDER_APPROVED=1`.

## DRP Rollback

Run `scripts/rollback.sh` to restore logs, keys and active strategies from the latest archive in `export/`. All events are logged to `logs/rollback.log` and `logs/errors.log`.

## kill_switch.sh Usage

`scripts/kill_switch.sh` manually toggles the system kill switch. By default it
creates a flag file at `/flags/kill_switch.txt` and writes audit entries to
`logs/kill_log.json`.

```bash
# Trigger the kill switch
bash scripts/kill_switch.sh

# Preview actions without modifying state
bash scripts/kill_switch.sh --dry-run

# Remove kill flag and clear environment variable
bash scripts/kill_switch.sh --clean
```

Environment variables `KILL_SWITCH_FLAG_FILE` and `KILL_SWITCH_LOG_FILE` control
the flag and log paths.
