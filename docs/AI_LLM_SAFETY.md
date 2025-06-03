# AI/LLM Safety—Sandbox, Gating, and Mutation Audit

This document summarizes the mandatory controls for safe AI/LLM driven mutation and promotion within the project.

## Scope
- **Sandbox Execution**: Never evaluate or execute LLM or auto‑generated code outside a secure, auditable sandbox.
- **Founder/Multi-Sig Gating**: All mutation, audit, and promotion steps must be explicitly approved by the founder or designated multi‑sig holders. Every approval must be logged with a `TRACE_ID`.
- **No Placebo Logic**: Remove all placeholder or stub implementations in AI scoring, mutation, and audit modules. Replace them with real, testable logic that emits structured logs.
- **Structured Logs**: Every event must be timestamped and formatted for audit agents. Logs are written to `logs/<module>.json` and errors to `logs/errors.log`.
- **Mutation Tests**: Tests include malicious code injection attempts, blocked AI mutation scenarios, and enforcement of founder gating. These tests must run in CI before any promotion.

## Promotion Workflow
1. Run fork simulations and unit tests.
2. Execute `ai/audit_agent.py` in offline mode.
3. Capture a DRP snapshot via `scripts/export_state.sh`.
4. Obtain founder approval (`FOUNDER_TOKEN`) and log the `TRACE_ID`.
5. Promote the strategy using `ai/promote.py`.

All steps must be logged and traceable. Promotion cannot proceed if any check fails or if founder approval is missing.
