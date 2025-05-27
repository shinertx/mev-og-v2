# MEV-OG Onboarding Guide

This quick-start guide summarizes how to set up and run the project. For detailed policies and runbooks, see [AGENTS.md](../AGENTS.md) and [PROJECT_BIBLE.md](../PROJECT_BIBLE.md).

## 1. Install Dependencies

```bash
poetry install          # installs Python packages
docker compose up -d    # launches local infrastructure
```

Copy the sample environment and configuration:

```bash
cp .env.example .env
cp config.example.yaml config.yaml
```

## 2. Run Tests and Simulations

Fork simulations and tests must pass before promotion:

```bash
bash scripts/simulate_fork.sh --target=strategies/<module>
pytest -v
foundry test
```

Run a mutation cycle if simulations succeed:

```bash
python ai/mutator/main.py
```

## 3. Promotion

Set `FOUNDER_APPROVED=1` to allow promotion and then execute:

```bash
python ai/promote.py            # single promotion
# or
python scripts/batch_ops.py promote <strategy> --source-dir staging --dest-dir active
```

## 4. DRP Export and Rollback

Create a Disaster Recovery Package (DRP) after successful tests:

```bash
bash scripts/export_state.sh
```

Set `DRP_ENC_KEY` to encrypt the archive with `openssl` or `gpg`. The same
variable must be provided to `scripts/rollback.sh` for decryption.

Restore from an archive if needed:

```bash
bash scripts/rollback.sh --archive=<exported-archive>
```

## 5. Kill Switch and Metrics

Use `scripts/kill_switch.sh` to toggle the system kill switch. Start the metrics
server for Prometheus scraping with:

```bash
python -m core.metrics --port $METRICS_PORT
```
If you set `METRICS_TOKEN`, include the header
`Authorization: Bearer $METRICS_TOKEN` when scraping.

## 6. Running the Orchestrator

`ai/mutator/main.py` serves as the live orchestrator. Use `--help` for a full
list of options. The most important flags are:

```
--logs-dir <path>      # where strategy logs are read from
--config <file>        # path to config.yaml (defaults to ./config.yaml)
--dry-run              # run checks without promoting changes
--mode live|dry-run    # explicit trade mode override
```

Example dry-run:

```bash
python ai/mutator/main.py --logs-dir logs --dry-run
```

If the run completes with no errors you can promote to live trading by removing
`--dry-run` and ensuring `config.yaml` has `mode: live`.

### DRP snapshots and restore

The orchestrator exports a Disaster Recovery Package by calling
`scripts/export_state.sh`. Restore from a snapshot with:

```bash
bash scripts/rollback.sh --archive=<exported-archive>
```

### Kill/Pause/Rollback flows

* **Kill switch:** `bash scripts/kill_switch.sh` toggles trading halt.
* **Pause strategy:** `python scripts/batch_ops.py pause <strategy>`.
* **Rollback:** `python scripts/batch_ops.py rollback <strategy>` or use the DRP
  archive as shown above.

### Troubleshooting

* Check `logs/errors.log` for stack traces.
* Ensure RPC endpoints in `config.yaml` are reachable.
* Verify the metrics server is running on `$METRICS_PORT`.


---

Refer to [AGENTS.md](../AGENTS.md) and [PROJECT_BIBLE.md](../PROJECT_BIBLE.md) for
complete mutation, audit, and promotion policies.
