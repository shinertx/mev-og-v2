# mev-og-v2

## Mission

MEV-OG is an AI-native, adversarial crypto trading system built to compound $5K → $10M+ via simulation-first Maximal Extractable Value (MEV), cross-domain arbitrage, liquidations, and flash loan exploitation.

> Fully autonomous. AI-CTO operated. Founder-controlled capital gates only.

> NOTE: All operational law, workflow, and validation in this file derive from PROJECT_BIBLE.md.  
> Any contradiction: PROJECT_BIBLE.md is the source of truth.

**Python 3.11 Required**

You must use Python 3.11 and activate your virtual environment before running any `python` or `pip` command.


## Table of Contents

- [System Architecture](#system-architecture)
- [Modules](#modules)
- [Environment Configuration](#environment-configuration)
- [Strategy Runbooks](#strategy-runbooks)
- [Mutation Workflow](#mutation-workflow)
- [DRP Recovery](#drp-recovery)
- [CI/CD](#cicd--canary-deployment)
- [AI/LLM Safety](docs/AI_LLM_SAFETY.md)

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
- AI consensus vote logs are stored in `telemetry/ai_votes/`.

---

## Founder Runbook

Follow this sequence to operate MEV-OG locally.

1. **Install dependencies**
   ```bash
   poetry install
   pre-commit install
   docker compose build
   docker compose up -d
   # Python deps pinned in requirements.txt
   # eth-typing==3.0.0, web3>=6.0.0, openai>=1.0.0
   ```
   Makefile shortcuts are available:
   ```bash
   make build
   make up
   ```
2. **Fetch secrets from Vault** – run `python3.11 scripts/load_vault_secrets.py` 
   to populate environment variables before starting services.
3. **Copy and customize `config.example.yaml`**
   ```bash
   cp config.example.yaml config.yaml
   # edit config.yaml to match your environment
   ```
4. **Provision dev VM (optional)**
   ```bash
   cd infra/terraform
   terraform init
   terraform apply -var="ami=<ami-id>" -var="key_name=<ssh-key>"
   cd ../..
   ```
5. **Run fork simulations for each strategy**
   ```bash
   bash scripts/simulate_fork.sh --target=strategies/<module>
   # or
   make simulate
   ```
6. **Run tests**
   ```bash
   pytest -v
   foundry test
   # or simply
   make test
   ```
7. **Execute the mutation workflow**
   ```bash
   python3.11 ai/mutator/main.py
   # or
   make mutate
   ```
8. **Promote when checks pass**
   ```bash
   python3.11 ai/promote.py
   # or
   make promote
   ```
9. **Export state**
   ```bash
   bash scripts/export_state.sh
   # or
   make export
   ```
10. **Roll back if needed**
   ```bash
   bash scripts/rollback.sh
   # stop containers with
   make down
   ```

The metrics server now starts automatically when you launch the Docker stack:
```bash
make up  # or `docker compose up -d`
```
Verify it is running by visiting `http://localhost:8000/metrics`. If
`METRICS_TOKEN` is set, include
`Authorization: Bearer $METRICS_TOKEN` when scraping.
Import `grafana/strategy_scoreboard.json` into Grafana to visualize scores and pruning history.

Key metrics exposed on `/metrics` include:
- `opportunities_found` – count of arbitrage opportunities detected
- `arb_profit` – total profit from recorded opportunities (ETH)
- `arb_latency` – average seconds between detection and submission
- `error_count` – total number of errors logged

### Environment & Configuration

MEV-OG reads settings from environment variables loaded via Vault using
`scripts/load_vault_secrets.py` and from `config.yaml`. Use `config.example.yaml`
as a template. Key variables include:

```
OPENAI_API_KEY=<your-openai-key>          # Enables online audits
FOUNDER_TOKEN=                            # approval token
KILL_SWITCH=0                             # 1 halts all trading
RPC_ETHEREUM_URL=<https://mainnet.ethereum.org>
RPC_ARBITRUM_URL=<https://arbitrum.rpc>
RPC_OPTIMISM_URL=<https://optimism.rpc>
KILL_SWITCH_FLAG_FILE=./flags/kill_switch.txt  # File trigger for halt
METRICS_PORT=9102                         # Prometheus server port
METRICS_TOKEN=<optional-token>            # Require auth header if set
FLASHBOTS_AUTH_KEY=<hex-private-key>      # Required for bundle submission
FLASHBOTS_RPC_URL=https://relay.flashbots.net
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
| `ARB_ERROR_LIMIT` | `3` | Consecutive error threshold before kill |
| `ARB_LATENCY_THRESHOLD` | `30` | Average latency threshold in seconds |
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
| `FOUNDER_TOKEN` | `<none>` | token or path for founder approval |
| `INTENT_FEED_URL` | `http://localhost:9000` | L3 intent feed |
| `KILL_SWITCH_FLAG_FILE` | `./flags/kill_switch.txt` | Kill switch trigger file |
| `KILL_SWITCH_LOG_FILE` | `logs/kill_log.json` | Kill switch audit log |
| `KILL_DRP_DIR` | `/telemetry/drp` | Directory for kill event snapshots |
| `KILL_SWITCH` | `0` | Set to 1 to halt all trading |
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
| `DUNE_API_KEY` | `<none>` | Enable Dune Analytics adapter |
| `DUNE_QUERY_ID` | `<none>` | Dune query ID for signals |
| `WHALE_ALERT_KEY` | `<none>` | Whale Alert API key |
| `COINBASE_WS_URL` | `<none>` | Coinbase WebSocket URL |
| `MUTATION_ID` | `dev` | Tag for current mutation cycle |
| `TRACE_ID` | `<auto>` | Unique approval trace ID |
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
| `POOL_L3` | `0x6b3d1a6...` | Scroll ETH/USDC pool |
| `POOL_OPTIMISM` | `0x8514924...` | Optimism pool address |
| `POOL_ZKSYNC` | `0x8e5ce2f...` | zkSync ETH/USDC pool |
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
| `NONCE_CACHE_FILE` | `state/nonce_cache.json` | NonceManager cache |
| `NONCE_LOG_FILE` | `logs/nonce_log.json` | NonceManager audit log |
| `TX_LOG_FILE` | `logs/tx_log.json` | Transaction builder log |
| `ORCH_CONFIG` | `config.yaml` | Orchestrator config file |
| `ORCH_LOGS_DIR` | `logs` | Directory for orchestrator logs |
| `ORCH_MODE` | `dry-run` | Default run mode |
| `WALLET_OPS_LOG` | `logs/wallet_ops.log` | Wallet operations audit log |
| `EXPORT_DIR` | `export` | DRP export directory |
| `EXPORT_LOG_FILE` | `logs/export_state.json` | DRP export audit log |
| `ROLLBACK_LOG_FILE` | `logs/rollback.log` | Rollback audit log |
| `FLASHBOTS_AUTH_KEY` | `<none>` | Private key for Flashbots bundles |
| `FLASHBOTS_RPC_URL` | `https://relay.flashbots.net` | Flashbots/SUAVE relay |
| `PRIORITY_FEE_GWEI` | `2` | Default EIP-1559 priority fee |
| `CHAOS_INTERVAL` | `600` | Seconds between scheduled chaos runs |
| `CHAOS_ADAPTERS` | `dex,bridge,cex,flashloan` | Adapters to target |
| `CHAOS_MODES` | `network,rpc,downtime,data_poison` | Failure modes injected |
| `CHAOS_SCHED_LOG` | `logs/chaos_scheduler.json` | Chaos scheduler log path |

### cross_domain_arb Runbook

```bash
# Start metrics server
python3.11 -m core.metrics &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/cross_domain_arb
# Run mutation cycle (updates threshold)
python3.11 ai/mutator/main.py --logs-dir logs
# Export DRP snapshot
bash scripts/export_state.sh
```

`cross_domain_arb` writes structured logs to `logs/cross_domain_arb.json` and
errors to `logs/errors.log`. Each entry includes
`timestamp`, `tx_id`, `strategy_id`, `mutation_id`, `risk_level`, `block` and a
unique `trace_id`.
DRP state files are controlled by the
`CROSS_ARB_STATE_PRE`, `CROSS_ARB_STATE_POST`, `CROSS_ARB_TX_PRE` and
`CROSS_ARB_TX_POST` environment variables.
Metrics are served on
`http://localhost:8000/metrics` for Prometheus to scrape.
Import the JSON dashboards in `grafana/` into Grafana for real-time score trends.

Example log:

```json
{"timestamp":"2025-01-01T00:00:00Z","event":"trade","tx_id":"0xabc","strategy_id":"cross_domain_arb","mutation_id":"42","risk_level":"low","block":123,"trace_id":"XYZ123"}
```
All logs and DRP exports are sanitized with `make_json_safe()` so that every entry is valid JSON and audit-ready.

### cross_rollup_superbot Runbook

```bash
# Start metrics server
python3.11 -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/cross_rollup_superbot
# Run a mutation and audit cycle
python3.11 ai/mutator/main.py --logs-dir logs
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
python3.11 -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/l3_app_rollup_mev
# Run a mutation and audit cycle
python3.11 ai/mutator/main.py --logs-dir logs
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
python3.11 -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/l3_sequencer_mev
# Run a mutation and audit cycle
python3.11 ai/mutator/main.py --logs-dir logs
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
python3.11 -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/nft_liquidation
# Run a mutation and audit cycle
python3.11 ai/mutator/main.py --logs-dir logs
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
python3.11 -m core.metrics --port $METRICS_PORT &
# Run fork simulation
bash scripts/simulate_fork.sh --target=strategies/rwa_settlement
# Run a mutation and audit cycle
python3.11 ai/mutator/main.py --logs-dir logs
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
5. Provide a valid `FOUNDER_TOKEN` and export a `TRACE_ID` when running
   `ai/promote.py` to move updated strategies into `active/`.
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
python3.11 ai/mutator/main.py
python3.11 ai/promote.py  # requires FOUNDER_TOKEN
```

main

## CI/CD & Canary Deployment

GitHub Actions workflow `main.yml` runs linting, typing, tests, fork simulations and DRP checks on every push and pull request. Each batch is tagged `canary-<sha>-<date>` and must pass the full suite. Promotion to production requires a valid `FOUNDER_TOKEN` and records the run under `TRACE_ID` in the uploaded artifacts.
Type checking uses `mypy --strict` and CI fails on any reported type error.

Local checks can be invoked via Poetry:
```bash
poetry run lint
poetry run typecheck
poetry run test
poetry run sim     # uses $SIM_TARGET if set
```

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

Environment variables `KILL_SWITCH_FLAG_FILE`, `KILL_SWITCH_LOG_FILE` and
`KILL_DRP_DIR` control the flag, log and DRP snapshot paths.


## Chaos/DR Drill

Run the automated chaos/disaster recovery drill harness:

```bash
python3.11 infra/sim_harness/chaos_drill.py
```

This triggers the kill switch, pauses capital via OpsAgent, simulates a lost agent, and forces failure across every supported adapter (DEX, bridge, CEX, flashloan, intent, sequencer and node). After each event the drill exports state with `scripts/export_state.sh`, restores it with `scripts/rollback.sh`, and scans all logs/archives for secrets or PII. Any secret causes an immediate failure. Export archives are stored in `export/`, drill logs in `logs/chaos_drill.json`, and per-module failure counts in `logs/drill_metrics.json`.

Validate locally with:

```bash
pytest tests/test_chaos_drill.py
```

### Adapter Chaos Simulation

Each adapter implements failure injection and fallback logic. Run targeted chaos tests with:

```bash
pytest tests/test_adapters_chaos.py
```

Manual simulation example:

```bash
python3.11 tests/test_adapters_chaos.py --simulate bridge_downtime
```

During a network outage the logs include entries like:

```json
{"event":"fallback_success","module":"dex_adapter","risk_level":"low"}
```

Metrics from the chaos run are written to `logs/drill_metrics.json` and OpsAgent dispatches alerts for each failure.

### Chaos Scheduler

Run scheduled chaos injections that randomly target adapters and failure modes:

```bash
CHAOS_ONCE=1 python3.11 infra/sim_harness/chaos_scheduler.py
```

Set `CHAOS_INTERVAL` (seconds), `CHAOS_ADAPTERS`, and `CHAOS_MODES` to control frequency and scope. Scheduler logs to `logs/chaos_scheduler.json` and updates `logs/drill_metrics.json` on each run.

## OpsAgent & CapitalLock

`agents/ops_agent.py` runs periodic health checks and pauses all strategies if
any fail. Alerts are sent via `OPS_ALERT_WEBHOOK` and counted by the metrics
server. `agents/capital_lock.py` enforces drawdown and loss limits; founder must
approve unlock actions by supplying a valid `FOUNDER_TOKEN` and providing a
unique `TRACE_ID` for audit.


Each strategy receives a `CapitalLock` instance from the orchestrator. Before
dispatching any transaction it calls `capital_lock.trade_allowed()`. When the
lock is engaged the strategy aborts, logging a structured error entry with the
message "capital lock: trade not allowed" to both its strategy log and
`logs/errors.log`.

## Gas/Latency Runbook

All bundle-based strategies share a common gas and latency tuning flow.

- Set `PRIORITY_FEE_GWEI` to adjust the EIP-1559 priority fee used when
  building Flashbots bundles.
- Bundles are created via `_bundle_and_send` which returns the bundle hash
  and observed latency. If bundle submission fails, the strategy falls back
  to `TransactionBuilder.send_transaction`.
- Latency is recorded in Prometheus metrics for each opportunity.

Example:

```bash
PRIORITY_FEE_GWEI=3 python3.11 -m core.orchestrator --config=config.yaml --dry-run
```

## Strategy Orchestrator

`core/orchestrator.py` boots all enabled strategies from `config.yaml` and
enforces kill switch, capital lock and founder approval on every iteration.

```bash
python3.11 -m core.orchestrator --config=config.yaml --dry-run   # single cycle
python3.11 -m core.orchestrator --config=config.yaml --live      # continuous
```

Use `--health` to run only OpsAgent checks. Live mode requires
`FOUNDER_TOKEN` to be present.

## Batch Operations

`scripts/batch_ops.py` manages groups of strategies. It supports three actions:

- `promote` – move a strategy from a source directory into the active set.
- `pause` – move a live strategy into the paused directory.
- `rollback` – restore a strategy from the destination directory using the audit trail.

All actions require a valid `FOUNDER_TOKEN`. Control where strategies are read from
and written to with `--source-dir`, `--dest-dir` and `--paused-dir`.
See the example call at the end of this README for a typical promotion command.

Example usage:

```bash
python3.11 scripts/batch_ops.py promote cross_rollup_superbot --source-dir staging --dest-dir active
```
## Strategy Review & Pruning

Use `core.strategy_scoreboard.StrategyScoreboard` to benchmark live strategies against real-time DEX/CEX gaps, whale alerts, Dune queries and Coinbase order flow. Adapters are enabled via `DUNE_API_KEY`, `WHALE_ALERT_KEY` and `COINBASE_WS_URL`. `prune_and_score()` requires multi-sig founder approval. Rankings are written to `logs/scoreboard.json` and all prune events are appended to `logs/mutation_log.json` with alerts sent via the Ops agent and Prometheus metrics.


## Wallet Operations

`scripts/wallet_ops.py` provides gated funding and withdrawal utilities. Every
action logs to `logs/wallet_ops.json` and snapshots state via
`scripts/export_state.sh` before and after execution.

```
python3.11 scripts/wallet_ops.py fund --from 0xabc --to 0xdef --amount 1 --dry-run
python3.11 scripts/wallet_ops.py withdraw-all --from 0xhot --to 0xbank
python3.11 scripts/wallet_ops.py drain-to-cold --from 0xhot --to 0xcold
```

Set `FOUNDER_TOKEN` and export a unique `TRACE_ID` or confirm interactively
when prompted. On failure the script aborts and logs the error.

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
python3.11 ai/mutator/main.py --logs-dir logs --dry-run
```

After verifying results, remove `--dry-run` and set `mode: live` in
`config.yaml`. A DRP archive is created automatically.

## Wallet Ops CLI

Use `scripts/wallet_ops.py` to safely fund or drain wallets.

```bash
python3.11 scripts/wallet_ops.py deposit 1.0   # fund 1 ETH
python3.11 scripts/wallet_ops.py withdraw 0.5  # withdraw 0.5 ETH
```

Actions append to `logs/wallet_ops.log` for auditing.

## Live Trade Checklist

1. `poetry install` and `docker compose up -d`
2. `python3.11 scripts/load_vault_secrets.py` to fetch secrets
3. Copy `config.example.yaml` to `config.yaml`
4. Run `pytest -v` and `foundry test`
5. `bash scripts/simulate_fork.sh --target=strategies/<module>`
6. `python3.11 ai/mutator/main.py --dry-run`
7. Review `logs/errors.log` and DRP archive
8. Set `FOUNDER_TOKEN` and export a `TRACE_ID` then run `python3.11 ai/mutator/main.py --mode live`
9. Check metrics at `http://localhost:$METRICS_PORT/metrics`
10. Drain funds with `wallet_ops.py` if needed

## Troubleshooting / FAQ

- **RPC failures:** confirm endpoints in `config.yaml` and ensure nodes are live.
- **Metrics missing:** run `python3.11 -m core.metrics --port $METRICS_PORT`.
- **Promotion blocked:** ensure `FOUNDER_TOKEN` is valid, a `TRACE_ID` is set and read `logs/errors.log`.
- **Rollback:** `bash scripts/rollback.sh --archive=<archive>`.

## Green-light Checklist

- Tests and fork simulations pass
- DRP snapshot exported
- Metrics endpoint live
- Wallet balances checked via `wallet_ops.py`

