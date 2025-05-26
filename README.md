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
- **Security:** Kill switch, circuit breakers, replay defense, key rotation
- **Recovery:** DRP + 1-hour restore snapshot from logs/state

---

## Modules

| Module | Status | Description |
|--------|--------|-------------|
| `strategies/cross_domain_arb` | 🚧 In progress | Cross-rollup + L1-L2 arbitrage execution bot |
| `infra/sim_harness` | ✅ | Simulates forks, chaos, and tx latency/failure |
| `ai/mutator` | ✅ | Self-prunes, mutates, and re-tunes strategies |
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
