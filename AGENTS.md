# AGENTS.md — Codex Instructions for MEV-OG

## Objective

Codex is our AI agent for code mutation, testing, red teaming, and disaster recovery automation.

Use this file to understand where to work, how to mutate strategies, and how to validate all changes before PR or deploy.

---

## Codex Directives

### 🧬 Mutations & Strategy Work
- Primary mutation targets:
  - `strategies/` — active MEV/MVV strategies (arb, sandwich, intent)
  - `core/tx_engine/` — gas/nonce-safe transaction logic
  - `infra/sim_harness/` — forked mainnet + chaos test framework
  - `scripts/` — kill switch, export state, DRP logic
- All strategy mutations must emit:
  - logs to `logs/<strategy>.json`
  - errors to `logs/errors.log`
  - metrics to Prometheus (if applicable)

---

## Folder Conventions

| Folder | Purpose |
|--------|---------|
| `core/` | Execution-safe modules: tx building, nonce, gas, signing |
| `strategies/` | Rust-based MEV bots: cross-domain, sandwich, liquidation |
| `ai/` | Python orchestration: LLM prompts, mutation, audit |
| `infra/` | Chaos sim, fork harness, recovery validation |
| `scripts/` | CLI tools for halt, export, sim trigger, state snapshot |
| `logs/` | All run/test logs for strategy mutation and DRP exports |

---

## Validation Requirements

✅ Every PR or module must pass:

```bash
pytest -v
foundry test
scripts/simulate_fork.sh --target=strategies/<module>
scripts/export_state.sh --dry-run

# AGENTS.md — Codex Instructions for MEV-OG

## Purpose

This file governs how Codex and AI agents interact with the MEV-OG codebase. All outputs must comply with the `PROJECT_BIBLE.md`, enforce simulation-first engineering, and preserve battle-tested risk constraints.

Codex is treated as a live agent contributing production code. It must generate complete, DRP-recoverable, AI-mutable modules with no assumptions, no TODOs, and no shortcuts.

---

## 🔐 Codex Prompt Preamble (MANDATORY for All Tasks)

Every task issued to Codex or any AI agent must begin with this preamble.

> Paste this block at the top of every prompt.

```text
Codex: Follow all mandates from `PROJECT_BIBLE.md`.

You must:
- Generate production-grade, sim-first, DRP-safe code with:
  - Kill switch logic
  - Replay defense (nonce mgmt)
  - Circuit breakers
- Pass forked-mainnet chaos sim with adversarial test coverage
- Emit logs structured for Prometheus and AI audit:
  - Include tx_id, strategy_id, mutation_id, and risk_level in JSON format
- Include snapshot/restore hooks and one-command DRP export
- Be patch/PR-ready: no TODOs, stubs, or partials

Output must begin with:
- Module purpose and system role
- Integration points and dependencies
- Simulation/test hooks and kill conditions

All generated modules must support Codex/GPT-based mutation and audit.

---

## 🔄 Codex Behavior Log

- `v0.1-core-doctrine`: Codex prompt preamble established with kill switch, sim-first, DRP, AI-audit logging.
- `v1.0-batch1-tx_engine`: Starting Batch 1. Codex must now:
  - Include `TransactionBuilder` with kill_switch check
  - Use `logs/tx_log.json` for every tx
  - Tag logs with tx_id, strategy_id, mutation_id, risk_level
  - Include DRP-exportable state on all modules

## 🚫 Stub Logic Policy

Codex must never inline or stub functionality from another module (e.g. kill_switch, logger, etc.).

- Always import shared modules, even if they don’t exist yet.
- Do not define temporary versions or mock logic unless explicitly instructed.
- This ensures modules remain plug-and-play and conflicts are avoided.

If import fails during test, comment it but do not inline logic.

## Optional Batches (GOAT Candidates)

- `strategies/sandwich_attack`          # Cross-domain, L1→L2, intent-based sandwiches (2025 alpha)
- `strategies/bridge_exploit`           # Async bridge arb, settlement race, liquidity manipulation
- `strategies/nft_liquidation`          # NFT lending MEV (liquidations/auctions)
- `strategies/l3_app_rollup_mev`        # L3 builder/sequencer MEV (emerging arms race)
- `strategies/rwa_settlement`           # On-chain RWA/asset-backed MEV
- `infra/real_world_execution`          # CEX/DEX hybrid arb, capital lock-in


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
