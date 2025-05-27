# mev-og-v2

## Mission

MEV-OG is an AI-native, adversarial crypto trading system built to compound $5K → $10M+ via simulation-first Maximal Extractable Value (MEV), cross-domain arbitrage, liquidations, and flash loan exploitation.

> Fully autonomous. AI-CTO operated. Founder-controlled capital gates only.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Modules](#modules)
- [Environment Configuration](#environment-configuration)
- [Strategy Runbooks](#strategy-runbooks)
- [Mutation Workflow](#mutation-workflow)
- [DRP Recovery](#drp-recovery)
- [CI/CD](#cicd--canary-deployment)

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
| `strategies/l3_app_rollup_mev` | 🚧 In progress | L3/app-rollup sandwiches and bridge-race MEV |
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

## Founder Runbook

Follow this sequence to operate MEV-OG locally.

1. **Install dependencies**
   ```bash
   poetry install
   docker compose up
   ```
2. **Configure `.env`** – copy `.env.example` then set
   `FOUNDER_APPROVED`, `KILL_SWITCH`, `OPENAI_API_KEY` and `METRICS_PORT`.
3. **Copy and customize `config.example.yaml`**
   ```bash
   cp config.example.yaml config.yaml
   # edit config.yaml to match your environment
   ```
4. **Run fork simulations for each strategy**
   ```bash
   bash scripts/simulate_fork.sh --target=strategies/<module>
   ```
5. **Run tests**
   ```bash
   pytest -v
   foundry test
   ```
6. **Execute the mutation workflow**
   ```bash
   python ai/mutator/main.py
   ```
7. **Promote when checks pass**
   ```bash
   python ai/promote.py
   ```
8. **Export state**
   ```bash
   bash scripts/export_state.sh
   ```
9. **Roll back if needed**
   ```bash
   bash scripts/rollback.sh
   ```

Start the metrics endpoint with:
```bash
python -m core.metrics --port $METRICS_PORT
```
and point Prometheus to `http://localhost:$METRICS_PORT/metrics` for monitoring.

### Environment & Configuration

MEV-OG reads settings from a `.env` file and `config.yaml`. Use
`config.example.yaml` as a template. Key variables include:

```
OPENAI_API_KEY=<your-openai-key>          # Enables online audits
FOUNDER_APPROVED=0                        # 1 allows promotion
RPC_ETHEREUM_URL=<https://mainnet.ethereum.org>
RPC_ARBITRUM_URL=<https://arbitrum.rpc>
RPC_OPTIMISM_URL=<https://optimism.rpc>
KILL_SWITCH_PATH=/tmp/mev_kill            # File trigger for halt
METRICS_PORT=9102                         # Prometheus server port
```

Additional strategy values:
```
POOL_ETHEREUM=0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8
POOL_ARBITRUM=0xb3f8e4262c5bfcc0a304143cfb33c7a9a64e0fe0
POOL_OPTIMISM=0x85149247691df622eaf1a8bd0c4bd90d38a83a1f
ARB_ALERT_WEBHOOK=<https://discord-or-telegram-webhook>
BRIDGE_COST_ETHEREUM_ARBITRUM=0.0005
```

Update these values when integrating new assets or networks. Bridge cost
variables (e.g., ``BRIDGE_COST_ETHEREUM_ARBITRUM``) control the assumed fee when
moving funds across rollups for `cross_rollup_superbot`.

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
python -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/cross_rollup_superbot
# Run a mutation and audit cycle
python ai/mutator/main.py --logs-dir logs
# Export DRP snapshot and rollback if needed
bash scripts/export_state.sh
bash scripts/rollback.sh --archive=<exported-archive>
```

### l3_app_rollup_mev Runbook

```bash
# Start metrics server
python -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/l3_app_rollup_mev
# Run a mutation and audit cycle
python ai/mutator/main.py --logs-dir logs
# Export DRP snapshot and rollback if needed
bash scripts/export_state.sh
bash scripts/rollback.sh --archive=<exported-archive>
```

### AI Mutation Workflow

1. Collect logs from all strategies.
2. Run `ai/audit_agent.py --mode=offline` and review results.
3. If approved, run `ai/audit_agent.py --mode=online` with `OPENAI_API_KEY`.
4. Execute `ai/mutator/main.py` to generate new parameters.
5. Set `FOUNDER_APPROVED=1` and run `ai/promote.py` to move updated strategies
   into `active/`.
6. Roll back with `ai/promote.rollback` or `scripts/rollback.sh` if needed.

Logs must include `timestamp`, `tx_id`, `strategy_id`, `mutation_id`,
`risk_level` and `block`. All metrics should expose Prometheus endpoints.


`cross_rollup_superbot` logs to `logs/cross_rollup_superbot.json` and shares the
common error log `logs/errors.log`. Metrics are scraped from the same
`/metrics` endpoint.

`l3_app_rollup_mev` logs to `logs/l3_app_rollup_mev.json` and shares the common
error log `logs/errors.log`. Metrics use the global `/metrics` endpoint.

## Mutation Workflow

Run automated mutation cycles and promote only after all checks pass.

```bash
python ai/mutator/main.py
python ai/promote.py  # requires FOUNDER_APPROVED=1
```

main

## CI/CD & Canary Deployment

GitHub Actions workflow `main.yml` runs linting, typing, tests, fork simulations and DRP checks on every push and pull request. Each batch is tagged `canary-<sha>-<date>` and must pass the full suite. Promotion to production requires `FOUNDER_APPROVED=1`.

## DRP Recovery

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
