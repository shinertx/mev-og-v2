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

---

## Codex Behavior Log

- v0.1-core-doctrine: Codex preamble, kill switch, sim-first, DRP, AI audit logging.
- v1.0-batch1-tx_engine: TransactionBuilder w/ kill switch, logs, DRP export.
- v1.1-batch1-kill_switch: Kill switch, logging, sim harness, unit test.
- v1.2-batch1-export_state: DRP snapshot/export, logs, dry-run/clean modes.
- v1.3-batch1-kill_switch_sh: Manual/DRY-RUN kill script, PR-ready, logs.
- v1.4-batch1-full_audit_patch: Full DRP/sim audit and patch.
- v2.1-batch2-goat_upgrade: Adversarial, DRP, sim, metrics, alert, mutation/AI-ready cross-domain MEV stack.
- v3.1-batch3-datetime_aiapi_upgrade: Datetime logging future-proofed, AI audit agent online (OpenAI API ready).

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
  - Major audit recommendations must be appended to this file for traceability.

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

---

- `v1.1-batch1-kill_switch`: Codex now produces:
  - Kill switch check from `.env` or flag file
  - Logs kill events to `/logs/kill_log.json`
  - Sim harness + unit test for env/file triggers


- `v1.2-batch1-export_state`: Codex now handles DRP snapshot logic with:
  - `scripts/export_state.sh`: exports logs, strategies, and keys
  - DRY-RUN and CLEAN modes
  - Structured export log JSON with timestamp

- `v1.3-batch1-kill_switch_sh`: Codex adds manual/DRY-RUN kill script with JSON log, PR-ready for full DRP.

- v1.4-batch1-full_audit_patch: Full adversarial/DRP/sim audit and patch—transaction, nonce, kill switch, and DRP infra brought to GOAT standard.

- v2.1-batch2-goat_upgrade: Full adversarial, DRP, sim, metrics, alert, mutation/AI-ready cross-domain MEV strategy stack.

- v3.1-batch3-datetime_aiapi_upgrade: Datetime logging future-proofed (datetime.now(datetime.UTC)), AI audit agent can now call OpenAI API live.
- v3.4-batch123-fullfix: Compliance sweep across all modules, unified error logging, updated tests and fork simulation script.
- v4.0-batch4-ai_mutation_promotion: AI-driven self-mutation loop with founder-gated promotion and continuous audit.
