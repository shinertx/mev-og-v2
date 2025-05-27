# AGENTS.md — Codex & LLM Instructions for MEV-OG
(Synced to PROJECT_BIBLE.md v3.1. All changes must be reconciled before PR or deploy.)

## Objective

Codex/LLM/AI agents are responsible for code mutation, testing, chaos/DRP, red teaming, audit, and automated disaster recovery.  
This file is the single source of truth for mutation, validation, and integration across all code, infra, and strategy layers.

---

## Codex Directives

### Mutation & Strategy Work

- Primary mutation targets:
    - `strategies/`
    - `core/tx_engine/`
    - `infra/sim_harness/`
    - `scripts/`
    - `ai/`
- Strategy mutations must emit:
    - logs to `logs/<strategy>.json`
    - errors to `logs/errors.log`
    - metrics to Prometheus-compatible endpoint
- Mutation cycles are run via `ai/mutator/main.py` and require founder approval
  (`FOUNDER_APPROVED=1`) before any live promotion.
- Every cycle must export an audit trail and DRP snapshot using
  `scripts/export_state.sh`.
- OpsAgent monitors health, pauses on failure, and sends alerts via webhooks.
- CapitalLock enforces drawdown/loss thresholds; unlocks require founder approval.
 - Strategies must call `capital_lock.trade_allowed()` before every trade.
   If False, abort and log "capital lock: trade not allowed" to the strategy log
   and `logs/errors.log` with `risk_level` "high".

---

## Folder Conventions

| Folder        | Purpose                                                      |
|---------------|--------------------------------------------------------------|
| `core/`       | Execution-safe modules: tx engine, nonce, signing, kill/DRP  |
| `strategies/` | MEV bots: cross-domain, sandwich, liquidation, intent        |
| `ai/`         | Orchestration: Codex/LLM prompt logic, mutation, audit, prune|
| `infra/`      | Chaos sim, fork/test harness, disaster recovery              |
| `scripts/`    | CLI tools for halt, export, state snapshot, mutation         |
| `logs/`       | All run/test logs for strategy mutation and DRP exports      |

---

## Validation Requirements

Every PR or batch/module must pass:
- `pytest -v`
- `foundry test`
- `scripts/simulate_fork.sh --target=strategies/<module>`
- `scripts/export_state.sh --dry-run`
 - `python ai/audit_agent.py --mode=offline --logs logs/<module>.json`
 No code is merged without forked-mainnet sim, chaos test, DRP snapshot/restore, and AI/LLM audit.

### cross_rollup_superbot Runbook
- Fork simulation: `bash scripts/simulate_fork.sh --target=strategies/cross_rollup_superbot`
- Export state: `bash scripts/export_state.sh`
- Rollback: `bash scripts/rollback.sh --archive=<path>`
- Mutation cycle: `python ai/mutator/main.py --logs-dir logs`

### cross_domain_arb Runbook
- Fork simulation: `bash scripts/simulate_fork.sh --target=strategies/cross_domain_arb`
- Export state: `bash scripts/export_state.sh`
- Rollback: `bash scripts/rollback.sh --archive=<path>`
- Mutation cycle: `python ai/mutator/main.py --logs-dir logs`
- Env vars: `CROSS_ARB_STATE_PRE`, `CROSS_ARB_STATE_POST`, `CROSS_ARB_TX_PRE`, `CROSS_ARB_TX_POST`, `CROSS_ARB_LOG`

### l3_app_rollup_mev Runbook
- Fork simulation: `bash scripts/simulate_fork.sh --target=strategies/l3_app_rollup_mev`
- Export state: `bash scripts/export_state.sh`
- Rollback: `bash scripts/rollback.sh --archive=<path>`
- Mutation cycle: `python ai/mutator/main.py --logs-dir logs`

### l3_sequencer_mev Runbook
- Fork simulation: `bash scripts/simulate_fork.sh --target=strategies/l3_sequencer_mev`
- Export state: `bash scripts/export_state.sh`
- Rollback: `bash scripts/rollback.sh --archive=<path>`
- Mutation cycle: `python ai/mutator/main.py --logs-dir logs`

### nft_liquidation Runbook
- Fork simulation: `bash scripts/simulate_fork.sh --target=strategies/nft_liquidation`
- Export state: `bash scripts/export_state.sh`
- Rollback: `bash scripts/rollback.sh --archive=<path>`
- Mutation cycle: `python ai/mutator/main.py --logs-dir logs`

### OpsAgent & CapitalLock Runbook
- Start OpsAgent: `python -m agents.ops_agent` (health checks in config)
- Use `scripts/batch_ops.py` to promote, pause or rollback strategies.
- CapitalLock state is shared via `agents.agent_registry` and unpaused only when
  founder sets `FOUNDER_APPROVED=1` and calls `unlock`.
 - Example strategy integration:
   ```python
   from agents.capital_lock import CapitalLock
   lock = CapitalLock(max_drawdown_pct=5, max_loss_usd=100, balance_usd=1000)
   strat = Strategy(..., capital_lock=lock)
   ```

### rwa_settlement Runbook
- Fork simulation: `bash scripts/simulate_fork.sh --target=strategies/rwa_settlement`
- Export state: `bash scripts/export_state.sh`
- Rollback: `bash scripts/rollback.sh --archive=<path>`
- Mutation cycle: `python ai/mutator/main.py --logs-dir logs`

---

## Codex Behavior Log

- v2.1-batch2-goat_upgrade: Adversarial, DRP, sim, metrics, alert, mutation/AI-ready cross-domain MEV stack.
- v3.1-batch3-datetime_aiapi_upgrade: Datetime logging future-proofed, AI audit agent online (OpenAI API ready).
- v3.4-batch123-fullfix: Compliance sweep across modules, unified error logging, updated tests and fork simulation script.
- v4.0-batch4-ai_mutation_promotion: AI-driven self-mutation loop with founder-gated promotion and continuous audit.
- v5.0-batch5-cicd_canary_drp: CI workflow, canary tagging and DRP rollback added.
- v6.0-batch6-superbot_metrics: Improved DRP export/rollback scripts, cross_rollup_superbot deployment, metrics server integration.

---

## Stub Logic Policy

- No stubs, no inlining.
- Never inline or stub logic from another module (e.g., kill_switch, logger).
- Always import shared modules, even if they don’t exist yet.
- If import fails, comment it—do not inline or re-implement logic.

---

## Chaos/Adversarial Testing Policy

- All new strategies, infra, and test harnesses must include at least one adversarial or chaos scenario (e.g., forced error, RPC fail, kill switch activation, stale data, sim reorg, edge risk).
- PR is rejected if only happy path is tested.

---

## AI Online/Offline Audit Policy

- Codex/LLM agents must:
  - Prefer offline mutation/audit by default (`ai/audit_agent.py` in offline mode).
  - For any major PR, refactor, or new live strategy, must run `ai/audit_agent.py` in online mode (OpenAI API, `OPENAI_API_KEY` from ENV).
  - All online audit recommendations must be logged, and key mutation diffs included in PR body.

---

## Audit Trail/Export

- Every batch/module must log:
  - mutation_id, risk_level, DRP snapshot location.
  - State and logs must be exportable for audit/rollback (`scripts/export_state.sh`).
    The export script skips symlinks and paths outside the repo to ensure
    archives are safe to restore.
  - Major audit recommendations must be appended to this file for traceability.

## CI/CD & Canary Deploy

- GitHub Actions workflow `main.yml` runs lint, type check, tests, fork simulation,
  DRP dry run and offline audit on every PR and push.
- New batches are automatically tagged `canary-<sha>-<date>` and verified with the
  same suite.
- Promotion to production requires all checks to pass and `FOUNDER_APPROVED=1`.

## DRP One-Click Rollback

- `scripts/rollback.sh` restores logs, keys and active strategies from the most
  recent export archive. The script validates archive paths and extracts in a
  temporary directory to block path traversal attacks.
Rollback events append to `logs/rollback.log` and `logs/errors.log`.
- Rollback events append to `logs/rollback.log` and `logs/errors.log`.

---

## Log Schema/Telemetry

- Every log/event must include:
  - timestamp (UTC), tx_id, strategy_id, mutation_id, risk_level, block, event
  - where possible, Prometheus metrics hooks.

---

## Optional Batches (GOAT Candidates)

- `strategies/sandwich_attack`          # Cross-domain, L1→L2, intent-based sandwiches (2025 alpha)
- `strategies/bridge_exploit`           # Async bridge arb, settlement race, liquidity manipulation
- `strategies/nft_liquidation`          # NFT lending MEV (liquidations/auctions)
- `strategies/l3_app_rollup_mev`        # L3 builder/sequencer MEV (emerging arms race)
- `strategies/rwa_settlement`           # On-chain RWA/asset-backed MEV
- `infra/real_world_execution`          # CEX/DEX hybrid arb, capital lock-in
- `agents/ops_agent.py`                 # Ops monitoring and alerts
- `agents/capital_lock.py`              # Runtime risk gating
- `adapters/cex_adapter.py`             # Exchange adapter
- `adapters/dex_adapter.py`             # Aggregator adapter
- `adapters/bridge_adapter.py`          # Bridge API adapter


## Changelog

- 2025-05-26T15:24:44Z – DRP export snapshot (dry-run baseline).
- 2025-05-26T17:46:21Z – Export snapshot and rollback restore test.
- 2025-05-26T17:48:56Z – Snapshot after `cross_rollup_superbot` simulation.
- 2025-05-26T18:23:14Z – Post-metrics server integration export.

