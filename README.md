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
| `strategies/l3_sequencer_mev` | 🚧 In progress | L3 sequencer sandwich and reorg arbitrage |
| `strategies/nft_liquidation` | 🚧 In progress | NFT lending liquidation sniping |
| `strategies/rwa_settlement` | 🚧 In progress | Cross-venue RWA settlement |
| `infra/sim_harness` | ✅ | Simulates forks, chaos, and tx latency/failure |
| `ai/mutator` | ✅ | Self-prunes, mutates, and re-tunes strategies |
| `ai/mutator/main.py` | ✅ | Orchestrates AI mutation cycles and audit-driven promotion |
| `ai/promote.py` | ✅ | Handles founder-gated promotion and rollback |
| `core/tx_engine` | 🚧 | Gas/timing-safe tx builder with kill switch logic |
| `core/oracles` | ✅ | Price, intention, and RWA feeds |
| `core/metrics` | ✅ | Prometheus-style metrics server |
| `agents/ops_agent.py` | ✅ | Health monitoring and alerts |
| `agents/capital_lock.py` | ✅ | Drawdown and loss gating |
| `agents/agent_registry.py` | ✅ | Inter-agent shared state |
| `adapters/cex_adapter.py` | ✅ | Sample CEX HTTP adapter |
| `adapters/dex_adapter.py` | ✅ | DEX aggregator interface |
| `adapters/bridge_adapter.py` | ✅ | Token bridge API wrapper |

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
If `METRICS_TOKEN` is set, include `Authorization: Bearer $METRICS_TOKEN` in
requests.

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
METRICS_TOKEN=<optional-token>            # Require auth header if set
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

All environment variables recognised by MEV-OG are listed below. Defaults match
the values used in tests and the simulation harness:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARB_ALERT_WEBHOOK` | `<none>` | Alert URL for cross_domain_arb |
| `ARB_EXECUTOR_ADDR` | `0x000...` | Executor address for cross_domain_arb |
| `BRIDGE_LATENCY_MAX` | `30` | Max seconds for bridge to finalize |
| `CROSS_ARB_LOG` | `logs/cross_domain_arb.json` | cross_domain_arb log |
| `CROSS_ARB_STATE_POST` | `state/cross_arb_post.json` | DRP snapshot after execution |
| `CROSS_ARB_STATE_PRE` | `state/cross_arb_pre.json` | DRP snapshot before execution |
| `CROSS_ARB_TX_POST` | `state/tx_post.json` | Tx builder snapshot after |
| `CROSS_ARB_TX_PRE` | `state/tx_pre.json` | Tx builder snapshot before |
| `CROSS_ROLLUP_LOG` | `logs/cross_rollup_superbot.json` | cross_rollup_superbot log |
| `ERROR_LOG_FILE` | `logs/errors.log` | Shared error log |
| `DRP_ENC_KEY` | `<none>` | Optional key to encrypt DRP archives |
| `FORK_BLOCK` | `19741234` | Fork block for sim harness |
| `FOUNDER_APPROVED` | `0` | 1 allows promote to production |
| `INTENT_FEED_URL` | `http://localhost:9000` | L3 intent feed |
| `KILL_SWITCH_FLAG_FILE` | `./flags/kill_switch.txt` | Kill switch trigger file |
| `KILL_SWITCH_LOG_FILE` | `/logs/kill_log.json` | Kill switch audit log |
| `L3_APP_EXECUTOR` | `0x000...` | Executor for l3_app_rollup_mev |
| `L3_APP_ROLLUP_LOG` | `logs/l3_app_rollup_mev.json` | l3_app_rollup_mev log |
| `L3_APP_STATE_POST` | `state/l3_app_post.json` | Post DRP snapshot |
| `L3_APP_STATE_PRE` | `state/l3_app_pre.json` | Pre DRP snapshot |
| `L3_APP_TX_POST` | `state/l3_app_tx_post.json` | Tx builder post snapshot |
| `L3_APP_TX_PRE` | `state/l3_app_tx_pre.json` | Tx builder pre snapshot |
| `L3_SEQ_EXECUTOR` | `0x000...` | Executor for l3_sequencer_mev |
| `L3_SEQ_LOG` | `logs/l3_sequencer_mev.json` | l3_sequencer_mev log |
| `L3_SEQ_STATE_POST` | `state/l3_seq_post.json` | Post DRP snapshot |
| `L3_SEQ_STATE_PRE` | `state/l3_seq_pre.json` | Pre DRP snapshot |
| `L3_SEQ_TX_POST` | `state/l3_seq_tx_post.json` | Tx builder post snapshot |
| `L3_SEQ_TX_PRE` | `state/l3_seq_tx_pre.json` | Tx builder pre snapshot |
| `METRICS_PORT` | `8000` | Port for Prometheus metrics |
| `MUTATION_ID` | `dev` | Tag for current mutation cycle |
| `NFT_FEED_URL` | `http://localhost:9000` | NFT liquidation feed |
| `NFT_LIQ_EXECUTOR` | `0x000...` | Executor for nft_liquidation |
| `NFT_LIQ_LOG` | `logs/nft_liquidation.json` | nft_liquidation log |
| `NFT_LIQ_STATE_POST` | `state/nft_liq_post.json` | Post DRP snapshot |
| `NFT_LIQ_STATE_PRE` | `state/nft_liq_pre.json` | Pre DRP snapshot |
| `NFT_LIQ_TX_POST` | `state/nft_liq_tx_post.json` | Tx builder post snapshot |
| `NFT_LIQ_TX_PRE` | `state/nft_liq_tx_pre.json` | Tx builder pre snapshot |
| `OPENAI_API_KEY` | `<none>` | Required for online GPT audits |
| `OPS_ALERT_WEBHOOK` | `<none>` | Webhook for OpsAgent alerts |
| `POOL_ARBITRUM` | `0xb3f8e426...` | Arbitrum pool address |
| `POOL_ETHEREUM` | `0x8ad599c3...` | Ethereum pool address |
| `POOL_L3` | `0x0000000...` | L3 test pool |
| `POOL_OPTIMISM` | `0x8514924...` | Optimism pool address |
| `POOL_ZKSYNC` | `0x0000000...` | zkSync test pool |
| `PRICE_FRESHNESS_SEC` | `30` | Allowed staleness for price feeds |
| `RPC_ARBITRUM_URL` | `http://localhost:8547` | Arbitrum RPC |
| `RPC_ETHEREUM_URL` | `http://localhost:8545` | Ethereum RPC |
| `RPC_OPTIMISM_URL` | `http://localhost:8548` | Optimism RPC |
| `RPC_ZKSYNC_URL` | `http://localhost:8550` | zkSync RPC |
| `RWA_EXECUTOR` | `0x000...` | Executor for rwa_settlement |
| `RWA_FEED_URL` | `http://localhost:9100` | RWA pricing feed |
| `RWA_SETTLE_LOG` | `logs/rwa_settlement.json` | rwa_settlement log |
| `RWA_STATE_POST` | `state/rwa_post.json` | Post DRP snapshot |
| `RWA_STATE_PRE` | `state/rwa_pre.json` | Pre DRP snapshot |
| `RWA_TX_POST` | `state/rwa_tx_post.json` | Tx builder post snapshot |
| `RWA_TX_PRE` | `state/rwa_tx_pre.json` | Tx builder pre snapshot |
| `SUPERBOT_EXECUTOR` | `0x000...` | Executor for cross_rollup_superbot |
| `SUPERBOT_STATE_POST` | `state/superbot_post.json` | Post DRP snapshot |
| `SUPERBOT_STATE_PRE` | `state/superbot_pre.json` | Pre DRP snapshot |
| `SUPERBOT_TX_POST` | `state/superbot_tx_post.json` | Tx builder post snapshot |
| `SUPERBOT_TX_PRE` | `state/superbot_tx_pre.json` | Tx builder pre snapshot |
| `TX_LOG_FILE` | `logs/tx_log.json` | Transaction builder log |
| `ORCH_CONFIG` | `config.yaml` | Orchestrator config file |
| `ORCH_LOGS_DIR` | `logs` | Directory for orchestrator logs |
| `ORCH_MODE` | `dry-run` | Default run mode |
| `WALLET_OPS_LOG` | `logs/wallet_ops.log` | Wallet operations audit log |

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
- `CROSS_ROLLUP_LOG` – log file (defaults to `logs/cross_rollup_superbot.json`)
- `SUPERBOT_STATE_PRE` – pre-trade snapshot (defaults to `state/superbot_pre.json`)
- `SUPERBOT_STATE_POST` – post-trade snapshot (defaults to `state/superbot_post.json`)
- `SUPERBOT_TX_PRE` – pre-bundle TX snapshot (defaults to `state/superbot_tx_pre.json`)
- `SUPERBOT_TX_POST` – post-bundle TX snapshot (defaults to `state/superbot_tx_post.json`)

Paths default under `logs/` or `state/` unless overridden.
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
- `L3_APP_ROLLUP_LOG` – log file (defaults to `logs/l3_app_rollup_mev.json`)
- `L3_APP_STATE_PRE` – pre-trade snapshot (defaults to `state/l3_app_pre.json`)
- `L3_APP_STATE_POST` – post-trade snapshot (defaults to `state/l3_app_post.json`)
- `L3_APP_TX_PRE` – pre-bundle TX snapshot (defaults to `state/l3_app_tx_pre.json`)
- `L3_APP_TX_POST` – post-bundle TX snapshot (defaults to `state/l3_app_tx_post.json`)
Paths default under `logs/` or `state/` unless overridden.

### l3_sequencer_mev Runbook

```bash
# Start metrics server
python -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/l3_sequencer_mev
# Run a mutation and audit cycle
python ai/mutator/main.py --logs-dir logs
# Export DRP snapshot and rollback if needed
bash scripts/export_state.sh
bash scripts/rollback.sh --archive=<exported-archive>
```
- `L3_SEQ_LOG` – log file (defaults to `logs/l3_sequencer_mev.json`)
- `L3_SEQ_STATE_PRE` – pre-trade snapshot (defaults to `state/l3_seq_pre.json`)
- `L3_SEQ_STATE_POST` – post-trade snapshot (defaults to `state/l3_seq_post.json`)
- `L3_SEQ_TX_PRE` – pre-bundle TX snapshot (defaults to `state/l3_seq_tx_pre.json`)
- `L3_SEQ_TX_POST` – post-bundle TX snapshot (defaults to `state/l3_seq_tx_post.json`)
Paths default under `logs/` or `state/` unless overridden.

### nft_liquidation Runbook

```bash
# Start metrics server
python -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/nft_liquidation
# Run a mutation and audit cycle
python ai/mutator/main.py --logs-dir logs
# Export DRP snapshot and rollback if needed
bash scripts/export_state.sh
bash scripts/rollback.sh --archive=<exported-archive>
```
- `NFT_LIQ_LOG` – log file (defaults to `logs/nft_liquidation.json`)
- `NFT_LIQ_STATE_PRE` – pre-bid snapshot (defaults to `state/nft_liq_pre.json`)
- `NFT_LIQ_STATE_POST` – post-bid snapshot (defaults to `state/nft_liq_post.json`)
- `NFT_LIQ_TX_PRE` – pre-bundle TX snapshot (defaults to `state/nft_liq_tx_pre.json`)
- `NFT_LIQ_TX_POST` – post-bundle TX snapshot (defaults to `state/nft_liq_tx_post.json`)
Paths default under `logs/` or `state/` unless overridden.

### rwa_settlement Runbook

```bash
# Start metrics server
python -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/rwa_settlement
# Run a mutation and audit cycle
python ai/mutator/main.py --logs-dir logs
# Export DRP snapshot and rollback if needed
bash scripts/export_state.sh
bash scripts/rollback.sh --archive=<exported-archive>
```
- `RWA_SETTLE_LOG` – log file (defaults to `logs/rwa_settlement.json`)
- `RWA_STATE_PRE` – pre-settlement snapshot (defaults to `state/rwa_pre.json`)
- `RWA_STATE_POST` – post-settlement snapshot (defaults to `state/rwa_post.json`)
- `RWA_TX_PRE` – pre-bundle TX snapshot (defaults to `state/rwa_tx_pre.json`)
- `RWA_TX_POST` – post-bundle TX snapshot (defaults to `state/rwa_tx_post.json`)
Paths default under `logs/` or `state/` unless overridden.

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
`l3_sequencer_mev` logs to `logs/l3_sequencer_mev.json` and shares the common error log `logs/errors.log`.
`nft_liquidation` logs to `logs/nft_liquidation.json` and shares the common error log `logs/errors.log`.
`rwa_settlement` logs to `logs/rwa_settlement.json` and shares the common error log `logs/errors.log`.

## Mutation Workflow

Run automated mutation cycles and promote only after all checks pass.

```bash
python ai/mutator/main.py
python ai/promote.py  # requires FOUNDER_APPROVED=1
```

main

## CI/CD & Canary Deployment

GitHub Actions workflow `main.yml` runs linting, typing, tests, fork simulations and DRP checks on every push and pull request. Each batch is tagged `canary-<sha>-<date>` and must pass the full suite. Promotion to production requires `FOUNDER_APPROVED=1`.
Type checking uses `mypy --strict` and CI fails on any reported type error.

## DRP Recovery

Run `scripts/rollback.sh` to restore logs, keys and active strategies from the latest archive in `export/`. The script now validates archive contents and extracts in a temporary directory to block path traversal attacks. All events are logged to `logs/rollback.log` and `logs/errors.log`.

## kill_switch.sh Usage

`scripts/kill_switch.sh` manually toggles the system kill switch. By default it
creates a flag file at `./flags/kill_switch.txt` and writes audit entries to
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

## OpsAgent & CapitalLock

`agents/ops_agent.py` runs periodic health checks and pauses all strategies if
any fail. Alerts are sent via `OPS_ALERT_WEBHOOK` and counted by the metrics
server. `agents/capital_lock.py` enforces drawdown and loss limits; founder must
approve unlock actions by setting `FOUNDER_APPROVED=1`.


Each strategy receives a `CapitalLock` instance from the orchestrator. Before
dispatching any transaction it calls `capital_lock.trade_allowed()`. When the
lock is engaged the strategy aborts, logging a structured error entry with the
message "capital lock: trade not allowed" to both its strategy log and
`logs/errors.log`.

## Strategy Orchestrator

`core/orchestrator.py` boots all enabled strategies from `config.yaml` and
enforces kill switch, capital lock and founder approval on every iteration.

```bash
python -m core.orchestrator --config=config.yaml --dry-run   # single cycle
python -m core.orchestrator --config=config.yaml --live      # continuous
```

Use `--health` to run only OpsAgent checks. Live mode requires
`FOUNDER_APPROVED=1`.

## Batch Operations

`scripts/batch_ops.py` manages groups of strategies. It supports three actions:

- `promote` – move a strategy from a source directory into the active set.
- `pause` – move a live strategy into the paused directory.
- `rollback` – restore a strategy from the destination directory using the audit trail.

All actions require `FOUNDER_APPROVED=1`. Control where strategies are read from
and written to with `--source-dir`, `--dest-dir` and `--paused-dir`.
See the example call at the end of this README for a typical promotion command.

Example usage:

```bash
python scripts/batch_ops.py promote cross_rollup_superbot --source-dir staging --dest-dir active
```

## Wallet Operations

`scripts/wallet_ops.py` provides gated funding and withdrawal utilities. Every
action logs to `logs/wallet_ops.json` and snapshots state via
`scripts/export_state.sh` before and after execution.

```
python scripts/wallet_ops.py fund --from 0xabc --to 0xdef --amount 1 --dry-run
python scripts/wallet_ops.py withdraw-all --from 0xhot --to 0xbank
python scripts/wallet_ops.py drain-to-cold --from 0xhot --to 0xcold
```

Set `FOUNDER_APPROVED=1` or confirm interactively when prompted. On failure the
script aborts and logs the error.

## Orchestrator CLI

`ai/mutator/main.py` orchestrates dry runs and live trading. Key options:

```
--logs-dir <path>   # strategy log directory
--config <file>     # config path
--dry-run           # run validations only
--mode live|dry-run # override config mode
```

Dry-run example:

```bash
python ai/mutator/main.py --logs-dir logs --dry-run
```

After verifying results, remove `--dry-run` and set `mode: live` in
`config.yaml`. A DRP archive is created automatically.

## Wallet Ops CLI

Use `scripts/wallet_ops.py` to safely fund or drain wallets.

```bash
python scripts/wallet_ops.py deposit 1.0   # fund 1 ETH
python scripts/wallet_ops.py withdraw 0.5  # withdraw 0.5 ETH
```

Actions append to `logs/wallet_ops.log` for auditing.

## Live Trade Checklist

1. `poetry install` and `docker compose up -d`
2. Copy `.env.example` to `.env` and fill RPC keys
3. Copy `config.example.yaml` to `config.yaml`
4. Run `pytest -v` and `foundry test`
5. `bash scripts/simulate_fork.sh --target=strategies/<module>`
6. `python ai/mutator/main.py --dry-run`
7. Review `logs/errors.log` and DRP archive
8. Set `FOUNDER_APPROVED=1` and run `python ai/mutator/main.py --mode live`
9. Check metrics at `http://localhost:$METRICS_PORT/metrics`
10. Drain funds with `wallet_ops.py` if needed

## Troubleshooting / FAQ

- **RPC failures:** confirm endpoints in `config.yaml` and ensure nodes are live.
- **Metrics missing:** run `python -m core.metrics --port $METRICS_PORT`.
- **Promotion blocked:** check `FOUNDER_APPROVED=1` and read `logs/errors.log`.
- **Rollback:** `bash scripts/rollback.sh --archive=<archive>`.

## Green-light Checklist

- Tests and fork simulations pass
- DRP snapshot exported
- Metrics endpoint live
- Wallet balances checked via `wallet_ops.py`

