Certainly! Below is the **fully augmented AGENTS.md**, enhanced with the missing Codex compliance points and strict founder gating, audit, chaos testing, and logging standards —
**while preserving every existing instruction and ensuring perfect alignment with your project and phased audit findings.**

This version is **safe to integrate without breaking current flows**, as it only adds explicit compliance, documentation, and enforcement clarity, **no logic or code changes**.

---

# AGENTS.md — Codex & LLM Instructions for MEV-OG

*(Fully reconciled and aligned with PROJECT\_BIBLE.md vX.X — all changes must be synced before PR or deploy.)*

---

## GOVERNANCE & ALIGNMENT NOTICE

This file is the operational agent and mutation handbook for MEV-OG and is **fully aligned with the principles and laws defined in PROJECT\_BIBLE.md**.
All changes here **must maintain compliance with PROJECT\_BIBLE.md mandates**, especially regarding gating, DRP/export, mutation, promotion, and founder approval.
Any contradiction or drift must be reported and remediated immediately before merge or deployment.

**Maintainers MUST reconcile this file with PROJECT\_BIBLE.md and CI workflows on every PR/release to prevent drift or unsafe bypasses.**

---

## OBJECTIVE

Codex/LLM/AI agents are responsible for code mutation, testing, chaos/DRP, red teaming, audit, and automated disaster recovery.
This file is the single source of truth for mutation, validation, and integration across all code, infra, and strategy layers.

---

## CODING & MUTATION DIRECTIVES

### Mutation & Strategy Work

* Primary mutation targets:

  * `strategies/`
  * `core/tx_engine/`
  * `infra/sim_harness/`
  * `scripts/`
  * `ai/`
* Strategy mutations must emit:

  * Logs to `logs/<strategy>.json`
  * Errors to `logs/errors.log`
  * Metrics to Prometheus-compatible endpoint
* Mutation cycles are run via `ai/mutator/main.py` and require **explicit founder approval (`FOUNDER_TOKEN`) and a `TRACE_ID` before any live promotion**.
* Every cycle **must export an audit trail and DRP snapshot** using `scripts/export_state.sh`.
* OpsAgent monitors health, pauses on failure, and sends alerts via webhooks.
* CapitalLock enforces drawdown/loss thresholds; unlocks require **founder approval via `FOUNDER_TOKEN`** and a `TRACE_ID` logged for each event.
* Strategies **must call `capital_lock.trade_allowed()` before every trade**.
  If False, abort and log `"capital lock: trade not allowed"` to strategy log and `logs/errors.log` with risk level `"high"`.

### Mutation & Promotion Enforcement

* No mutation or promotion can proceed without:

  * Passing all tests (unit, integration, fork sim, chaos)
  * Passing audit agent checks (offline and online modes)
  * Producing structured mutation diff logs and audit artifacts
  * Explicit founder gating, logged and archived in CI with a `TRACE_ID`
* All mutation and promotion events **must be traceable by unique IDs (`TRACE_ID`) in logs and CI artifacts**.

---

## FOLDER CONVENTIONS

| Folder        | Purpose                                                       |
| ------------- | ------------------------------------------------------------- |
| `core/`       | Execution-safe modules: tx engine, nonce, signing, kill/DRP   |
| `strategies/` | MEV bots: cross-domain, sandwich, liquidation, intent         |
| `ai/`         | Orchestration: Codex/LLM prompt logic, mutation, audit, prune |
| `infra/`      | Chaos sim, fork/test harness, disaster recovery               |
| `scripts/`    | CLI tools for halt, export, state snapshot, mutation          |
| `logs/`       | All run/test logs for strategy mutation and DRP exports       |

---

## VALIDATION REQUIREMENTS

Every PR or batch/module must pass:

* `pytest -v`
* `foundry test` (or documented alternate if missing)
* `scripts/simulate_fork.sh --target=strategies/<module>`
* `scripts/export_state.sh --dry-run`
* `python ai/audit_agent.py --mode=offline --logs logs/<module>.json`

### Static Type Hygiene

* All functions and classes **must** include type annotations.
* `mypy --strict` and `ruff check` must report zero errors.
* Remove unused `# type: ignore` comments and pin dependency versions
  in `requirements.txt` when updating packages.

**No code is merged without forked-mainnet sim, chaos test, DRP snapshot/restore, and AI/LLM audit.**
**No promotion or live mutation occurs without explicit founder approval (`FOUNDER_TOKEN`) and audit artifact export.**

---

## RUNBOOKS

### cross\_rollup\_superbot

* Fork simulation:
  `bash scripts/simulate_fork.sh --target=strategies/cross_rollup_superbot`
* Export state:
  `bash scripts/export_state.sh`
* Rollback:
  `bash scripts/rollback.sh --archive=<path>`
* Mutation cycle:
  `python ai/mutator/main.py --logs-dir logs`

### cross\_domain\_arb

* Fork simulation:
  `bash scripts/simulate_fork.sh --target=strategies/cross_domain_arb`
* Export state:
  `bash scripts/export_state.sh`
* Rollback:
  `bash scripts/rollback.sh --archive=<path>`
* Mutation cycle:
  `python ai/mutator/main.py --logs-dir logs`
* Env vars:
  `CROSS_ARB_STATE_PRE`, `CROSS_ARB_STATE_POST`, `CROSS_ARB_TX_PRE`, `CROSS_ARB_TX_POST`, `CROSS_ARB_LOG`

### l3\_app\_rollup\_mev

* Fork simulation:
  `bash scripts/simulate_fork.sh --target=strategies/l3_app_rollup_mev`
* Export state:
  `bash scripts/export_state.sh`
* Rollback:
  `bash scripts/rollback.sh --archive=<path>`
* Mutation cycle:
  `python ai/mutator/main.py --logs-dir logs`

### l3\_sequencer\_mev

* Fork simulation:
  `bash scripts/simulate_fork.sh --target=strategies/l3_sequencer_mev`
* Export state:
  `bash scripts/export_state.sh`
* Rollback:
  `bash scripts/rollback.sh --archive=<path>`
* Mutation cycle:
  `python ai/mutator/main.py --logs-dir logs`

### nft\_liquidation

* Fork simulation:
  `bash scripts/simulate_fork.sh --target=strategies/nft_liquidation`
* Export state:
  `bash scripts/export_state.sh`
* Rollback:
  `bash scripts/rollback.sh --archive=<path>`
* Mutation cycle:
  `python ai/mutator/main.py --logs-dir logs`

### chaos_drill

* Run harness:
  `python infra/sim_harness/chaos_drill.py`
* Validate:
  `pytest tests/test_chaos_drill.py`
* Results are written to `logs/chaos_drill.json` with per-adapter failure counts in `logs/drill_metrics.json`.
  CI fails if any secrets/PII are detected in logs or DRP exports.

### adapter_chaos

* Run targeted adapter chaos tests:
  `pytest tests/test_adapters_chaos.py`
* Manual simulation:
  `python tests/test_adapters_chaos.py --simulate bridge_downtime`
* Expect `fallback_success` events in module logs and OpsAgent alerts for each failure.

### chaos_scheduler

* Run scheduler:
  `CHAOS_ONCE=1 python infra/sim_harness/chaos_scheduler.py`
* Configure via ENV:
  `CHAOS_INTERVAL`, `CHAOS_ADAPTERS`, `CHAOS_MODES`, `CHAOS_SCHED_LOG`.
* Scheduler logs to `logs/chaos_scheduler.json` and updates `logs/drill_metrics.json`.

### OpsAgent & CapitalLock Runbook

* Start OpsAgent:
  `python -m agents.ops_agent` (health checks configured in config)
* Use `scripts/batch_ops.py` to promote, pause, or rollback strategies.
* CapitalLock state is shared via `agents.agent_registry` and unpaused **only when founder provides a valid `FOUNDER_TOKEN` and calls unlock with a unique `TRACE_ID`**.
* Example strategy integration:

```python
from agents.capital_lock import CapitalLock
lock = CapitalLock(max_drawdown_pct=5, max_loss_usd=100, balance_usd=1000)
strat = Strategy(..., capital_lock=lock)
```

### rwa\_settlement

* Fork simulation:
  `bash scripts/simulate_fork.sh --target=strategies/rwa_settlement`
* Export state:
  `bash scripts/export_state.sh`
* Rollback:
  `bash scripts/rollback.sh --archive=<path>`
* Mutation cycle:
  `python ai/mutator/main.py --logs-dir logs`

### Gas/Latency Runbook

- Flashbots bundles are constructed via `_bundle_and_send` in each strategy.
- Adjust `PRIORITY_FEE_GWEI` to set the priority fee for bundles.
- On failure, `_bundle_and_send` falls back to `TransactionBuilder.send_transaction`.
- Bundle latency is returned for metrics and log entry enrichment.
### Strategy Review & Pruning

- Run `python -m core.strategy_scoreboard` or call `StrategyScoreboard.prune_and_score()` after each trading loop.
- Adapters for Dune Analytics, Whale Alert and Coinbase WebSocket are enabled via environment variables. Review `logs/scoreboard.json` for scores blended with external signals.
- Multi-sig founder approval (`FOUNDER_TOKEN`) is required for pruning and promotion. Alerts and metrics are dispatched via `OpsAgent.notify` and Prometheus.
- Every prune/promote/mutation event is recorded in `logs/mutation_log.json` using the current `TRACE_ID`.


## Agent CLI Reference

| Command | Purpose |
|---------|---------|
| `python ai/promote.py` | Promote tested strategies into the active set. Requires `FOUNDER_TOKEN` and `TRACE_ID`. |
| `python scripts/batch_ops.py promote <strat>` | Batch promote one or more strategies. |
| `python scripts/batch_ops.py pause <strat>` | Move a live strategy to the paused directory. |
| `python scripts/batch_ops.py rollback <strat>` | Restore a strategy from audit logs. |
| `bash scripts/kill_switch.sh` | Toggle the global kill switch. |
| `bash scripts/export_state.sh` | Export logs and state into `$EXPORT_DIR`. |
| `bash scripts/rollback.sh --archive=<file>` | Restore from a DRP archive. |

---

## CODE QUALITY POLICIES

### Stub Logic Policy

* No stubs, no inlining.
* Never inline or stub logic from another module (e.g., kill\_switch, logger).
* Always import shared modules, even if they don’t exist yet.
* If import fails, comment it—do not inline or re-implement logic.

### Chaos/Adversarial Testing Policy

* All new strategies, infra, and test harnesses **must include at least one adversarial or chaos scenario** (e.g., forced error, RPC fail, kill switch activation, stale data, sim reorg, edge risk).
* PRs **are rejected if only happy path is tested**.

### AI Online/Offline Audit Policy

* Codex/LLM agents must:

  * Prefer offline mutation/audit by default (`ai/audit_agent.py` in offline mode).
  * For any major PR, refactor, or new live strategy, must run `ai/audit_agent.py` in online mode (OpenAI API, `OPENAI_API_KEY` from ENV).
  * All online audit recommendations must be logged, and key mutation diffs included in PR body.

---

## AUDIT TRAIL & EXPORT POLICY

* Every batch/module must log:

  * `mutation_id`, `risk_level`, DRP snapshot location.
  * State and logs must be exportable for audit/rollback (`scripts/export_state.sh`).
  * The export script skips symlinks and paths outside the repo to ensure archives are safe to restore.
* Major audit recommendations must be appended to this file for traceability.

---

## CI/CD & CANARY DEPLOY

* GitHub Actions workflow `main.yml` runs lint, type check, tests, fork simulation, DRP dry run and offline audit on every PR and push.
* New batches are automatically tagged `canary-<sha>-<date>` and verified with the same suite.
* Promotion to production requires all checks to pass and `FOUNDER_TOKEN` is provided.

---

## DRP ONE-CLICK ROLLBACK

* `scripts/rollback.sh` restores logs, keys and active strategies from the most recent export archive.
* The script validates archive paths and extracts in a temporary directory to block path traversal attacks.
* Rollback events append to `logs/rollback.log` and `logs/errors.log`.

---

## RED TEAM TEST CASES

* **Nonce replay attacks:** `tests/test_nonce_manager.py::test_cross_agent_replay` verifies cached nonces cannot be replayed across agents.
* **Cross-agent order flow conflicts:** `tests/test_tx_engine.py::test_cross_agent_order_flow` ensures concurrent builders share a single nonce stream.
* **Malicious external input:** `tests/test_export_state_sh.py::test_malicious_env_input` checks environment variables cannot inject dangerous paths.
* **Rate limiting and exploit handling:** `tests/test_rate_limiter.py` enforces call throttling with `core.rate_limiter.RateLimiter`.

---

## LOG SCHEMA & TELEMETRY

* Every log/event must include:

  * `timestamp` (UTC), `tx_id`, `strategy_id`, `mutation_id`, `risk_level`, `block`, `trace_id`, `event`.
  * Where possible, Prometheus metrics hooks.

Example log entry:

```json
{"timestamp":"2025-01-01T00:00:00Z","event":"mutate","tx_id":"0xabc","strategy_id":"cross_domain_arb","mutation_id":"42","risk_level":"low","block":123,"trace_id":"XYZ123"}
```

---

## OPTIONAL BATCHES (GOAT CANDIDATES)

* `strategies/sandwich_attack` — Cross-domain, L1→L2, intent-based sandwiches (2025 alpha)
* `strategies/bridge_exploit` — Async bridge arb, settlement race, liquidity manipulation
* `strategies/nft_liquidation` — NFT lending MEV (liquidations/auctions)
* `strategies/l3_app_rollup_mev` — L3 builder/sequencer MEV (emerging arms race)
* `strategies/rwa_settlement` — On-chain RWA


/asset-backed MEV

* `infra/real_world_execution` — CEX/DEX hybrid arb, capital lock-in
* `agents/ops_agent.py` — Ops monitoring and alerts
* `agents/capital_lock.py` — Runtime risk gating
* `adapters/cex_adapter.py` — Exchange adapter
* `adapters/dex_adapter.py` — Aggregator adapter
* `adapters/bridge_adapter.py` — Bridge API adapter

---

## CHANGELOG

* 2025-05-26T15:24:44Z — DRP export snapshot (dry-run baseline).
* 2025-05-26T17:46:21Z — Export snapshot and rollback restore test.
* 2025-05-26T17:48:56Z — Snapshot after `cross_rollup_superbot` simulation.
* 2025-05-26T18:23:14Z — Post-metrics server integration export.
* 2025-05-29T04:45:17Z — Added red team tests for replay, order conflicts, malicious input, and rate limiting.

---

.
