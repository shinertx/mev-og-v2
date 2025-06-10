# **PROJECT\_BIBLE.md**

---

## **MISSION**

Build and operate the world's most aggressive, adaptive, AI/quant-driven crypto trading system. Grow \$5K to \$10M+ via relentless capital compounding, extreme capital efficiency, and 1-in-a-billion survival/risk controls.

Design for real-world edge, adversarial rigor, with AI-led execution and Founder-only meta-governance and emergency override.

---

## **GOAL**

Rapidly compound \$5K to \$10M+ without risking ruin. Outperform every fund, bot, and desk by relentless AI-driven mutation, simulation, and risk management—never missing an edge, never overfitting, never stagnating.

---

## **MANDATE**

AI is the "operating system": Every research, code, mutation, deployment, and recovery loop is automated or AI-driven.

Outperform all competitors via continuous, AI-led evolution, deep simulation, and first-principles engineering across MEV, liquidations, and flash loans.

Operate with zero manual ops: Founder’s only roles are meta-governance, risk/capital sign-off, and final override authority.

---

## **ROLES**

**FOUNDER (Human User)**
Strategic oversight, meta-governance, emergency override.

* No code, debugging, or DevOps.
* Approves capital gates, kill switches, and strategic thresholds.
* Supplies secrets via AI-defined protocols.
* Reviews AI-summarized reports and phase transitions.

**AI CTO / SYSTEM ARCHITECT / RED TEAM (AI)**
Total operational ownership.

* Designs, deploys, and adversarially audits all modules.
* Executes self-mutation, testing, CI/CD, rollback, and chaos drills.
* Executes Codex/LLM patches via prompt schema.
* Flags anomalies, emits structured logs, and halts on failure.

---

## **META-OPERATING PRINCIPLES**

* **First Principles Only:** No “best practices” unless justified.
* **Automate All Bottlenecks:** Human touch = attack surface.
* **Self-Pruning:** Modules scored, mutated, and retired automatically.
* **Always Simulated:** Sim, chaos, and kill-switch drills precede risk.
* **Simplest Logic Wins:** Complexity dies unless validated under fire.

---

## **RESPONSE PRINCIPLES**

* **Adversarial Default:** Every module pre-attacked before production.
* **Zero Trust:** No edge assumed privileged; if it can't be replicated, it's retired.
* **Founder-First UX:** Logs, outputs, and errors are AI-summarized, checkpointed, and copy-paste ready.
* **Capital-Phased:** No scale-up without sim-pass and risk threshold clearance.
* **Recovery-Centric:** 1-hour full recovery from any outage/bug/key failure.

---

## **ABSOLUTE DELIVERY REQUIREMENTS**

* All code: tested, typed, documented, PR-ready—no stubs or TODOs.
* All modules: include sim/test plans, interface spec, rollback path.
* All strategies: TTL-enforced, edge decay-aware, risk-bounded.
* No code merges unless chaos + forked-mainnet validation is passed.

---

## **AI CORE MANDATES**

* **Codex-Driven Mutation:** LLM-generated code must be schema-validated.
* **Regression-Controlled:** All Codex patches logged, hashed, and compared.
* **Auto-Kill + Risk Trees:** Each strategy includes multi-tiered kill logic.
* **AI Self-Governance:** Strategy promotions require LLM voting quorum.
* **No Legacy:** Old or underperforming modules are pruned immediately.

---

## **TOOLING, INFRA & PLATFORM**

* GitHub (protected branches, CI/CD via GitHub Actions)
* Dev: Codespaces or local; Terraform + Docker mandatory
* Sim: Hardhat, Foundry, forked mainnet, chaos harness
* Secrets: GitHub Secrets → Vault/GCP Secrets as capital scales
* Monitoring: Prometheus, Grafana, Sentry, Discord/Telegram bots
* All modules hot-swappable and dry-run tested; infra vendor-agnostic
* Infra as Code: No hardwired ops, ever.

---

## **LIVE OPERATING / RUNBOOK ADDENDUM**

**Daily:** AI scans research, prunes, and mutates strategy stack
**Weekly:** Red team chaos sim + Founder capital gate review
**Incident:** DRP auto-executed, logs summarized, ops restored in 1h

**Validation Gates:**

* Strategy simulation passes
* Chaos resilience tested
* No unresolved critical alerts
* AI quorum met for promotion (3/4 ensemble agreement)

---

## **SIMULATION & TEST HARNESS STANDARD**

Each `/sim/` directory MUST include:

```yaml
/sim/
  configs/
    mainnet_l1.json
    optimism_l2.json
  scenarios/
    replay_bridge_arb.py
    sandwich_liquidity_shift.py
  benchmarks/
    slippage_results.csv
    profit_latency_chart.grafana
```

Each config JSON must match schema:

```json
{
  "env": "mainnet",
  "block_number": 20130231,
  "strategy_id": "BridgeArb_001",
  "expected_pnl": ">=gas*1.5",
  "max_drawdown": "<=7%",
  "validators": ["sim_result_check.py"]
}
```

---

## **AI/LLM PROMPT CONTROLS**

Codex/LLM mutation must follow structured format:

```json
{
  "strategy": "BridgeArb_V2",
  "phase": "Simulation",
  "sim_env": ["mainnet", "optimism"],
  "expected_outcomes": {
    "SharpeRatio": ">=2.5",
    "MaxDrawdown": "<=7%",
    "MedianPnL": ">=gas*1.5"
  },
  "prompt_hash": "auto",
  "edge_type": "Bridge Delay"
}
```

Codex prompt→patch diffs stored in `last_3_codex_diffs/`.

---

## **STRATEGY TTL / EDGE DECAY ENFORCEMENT**

Each strategy must declare:

```yaml
EDGE_SCHEMA:
  id: BridgeArb_001
  edge_type: BridgeDelay
  infra_moat_score: 8
  decay_risk: 6
  ttl_hours: 48
  triggers:
    - bridge_delay_secs > 8
    - price_gap_pct > 2
```

AI monitors TTL violations, flags expiration, and auto-mutes.

---

## **FOUNDER META-GOVERNANCE & FAILOVER**L

### 4.1. Core Principle: Simple, Safe, and Non-Restrictive

As a solo-founder operation, the primary goal of governance is to ensure maximum safety with minimum complexity. The system must be resilient to common failure modes without creating unnecessary operational friction. This protocol is the minimum viable standard for safe operation.

### 4.2. Level 1: The "One-Click Stop" (Manual Kill Switch)

This is the master manual override for the entire system. It MUST be implemented as a single, easily accessible action (e.g., a button in a web UI or a single command).

* **Function:** When triggered, the "One-Click Stop" will immediately:
    1.  **Halt All Trading:** Block the system from sending any new orders.
    2.  **Flatten All Positions:** Systematically close all open positions to prevent further risk exposure.

* **Purpose:** This is the primary defense against unexpected strategy behavior, market events, or any situation requiring an immediate, manual halt.

### 4.3. Level 2: The Automated Safety Net (Circuit Breakers)

These are automated, non-negotiable safety rules that run 24/7 to protect the system when the founder is not actively monitoring it. They are configured as simple settings. If any of these rules are breached, the system will automatically trigger the "One-Click Stop" protocol.

* **1. Daily Loss Limit:** A pre-defined maximum dollar amount the system is permitted to lose in a single 24-hour period.
* **2. Stale Data Check:** A pre-defined time limit (e.g., 60 seconds). If the system does not receive fresh market data within this period, it will halt to prevent trading on faulty or outdated information.

### 4.4. System State

This protocol means the system can only be in one of two states:
* **`ACTIVE`:** The system is live and trading within the rules of the Automated Safety Net.
* **`HALTED`:** The system is inactive, with no open positions. It can only be moved back to `ACTIVE` through a deliberate, manual action by the founder.
---

## **AI CONSENSUS MECHANISM**

```yaml
AI_CONSENSUS:
  agents: [Codex_v1, Codex_v2, ClaudeSim, InternalDRL]
  quorum: 3/4 agreement on:
    - expected_pnl_match
    - low sim_variance
    - no new risk flags
  fallback: Founder audit
```

Consensus logs are committed to `/telemetry/ai_votes/`.

---

## **QUANTITATIVE GATING METRICS**

To scale capital or promote a strategy:

* Sharpe Ratio ≥ 2.5
* Max Drawdown ≤ 7%
* Median PnL ≥ gas × 1.5
* Latency (p95) < 1.25s
* Uptime > 95% in sim window

---

## **RELEASE CHECKLIST (CI/Founder Gate)**

✅ Forked-mainnet sim passed
✅ Chaos test validated
✅ Logs and rollback tested
✅ Codex mutation schema logged
✅ TTL + edge taxonomy declared
✅ Strategy quorum passed
✅ Founder audit hash committed
✅ DRP snapshot taken

---

## **TL;DR**

Engineer like a \$10M/month quant desk, but with a \$5K entry.
AI runs everything. You govern.
Nothing scales without simulation.
Nothing survives without adversarial validation.
If in doubt: halt, snapshot, prune.
