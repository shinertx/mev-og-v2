# MEV-OG Onboarding Guide

This quick-start guide summarizes how to set up and run the project. For detailed policies and runbooks, see [AGENTS.md](../AGENTS.md) and [PROJECT_BIBLE.md](../PROJECT_BIBLE.md).

**Python 3.11 Required**

You must use Python 3.11 and activate your virtual environment before running any `python` or `pip` command.

## 1. Install Dependencies

```bash
poetry install          # installs Python packages
pre-commit install      # set up git hooks
docker compose build    # build service images
docker compose up -d    # launches local infrastructure
```
You can use the Makefile shortcuts as well:
```bash
make build
make up
```

Fetch secrets from Vault and copy the sample configuration:

```bash
python3.11 scripts/load_vault_secrets.py
cp config.example.yaml config.yaml
```

Optionally provision a dev instance via Terraform:

```bash
cd infra/terraform
terraform init
terraform apply -var="ami=<ami-id>" -var="key_name=<ssh-key>"
cd ../..
```

## 2. Run Tests and Simulations

Fork simulations and tests must pass before promotion:

```bash
bash scripts/simulate_fork.sh --target=strategies/<module>
pytest -v
foundry test
# or use
make simulate
make test
```

Run a mutation cycle if simulations succeed:

```bash
python3.11 ai/mutator/main.py
make mutate
```

## 3. Promotion

Set `FOUNDER_TOKEN` to allow promotion and then execute:

```bash
python3.11 ai/promote.py            # single promotion
# or
python3.11 scripts/batch_ops.py promote <strategy> --source-dir staging --dest-dir active
make promote
```

## 4. DRP Export and Rollback

Create a Disaster Recovery Package (DRP) after successful tests:

```bash
bash scripts/export_state.sh
make export
```

Set `DRP_ENC_KEY` to encrypt the archive with `openssl` or `gpg`. The same
variable must be provided to `scripts/rollback.sh` for decryption.
All log and state files are sanitized via `make_json_safe()` before export to
guarantee valid JSON for audit agents.

Restore from an archive if needed:

```bash
bash scripts/rollback.sh --archive=<exported-archive>
make down
```

## 5. Kill Switch and Metrics

Use `scripts/kill_switch.sh` to toggle the system kill switch. The metrics
server now starts automatically when you run the Docker stack:

```bash
make up  # or `docker compose up -d`
```
Verify it by visiting `http://localhost:8000/metrics`. If you set `METRICS_TOKEN`,
include the header `Authorization: Bearer $METRICS_TOKEN` when scraping.

## Running the Strategy Orchestrator

Start all enabled strategies using the unified orchestrator. Use dry-run mode
first to verify configuration:

```bash
python3.11 -m core.orchestrator --config=config.yaml --dry-run
```

For continuous live execution run:

```bash
python3.11 -m core.orchestrator --config=config.yaml --live
```

Live mode requires a valid `FOUNDER_TOKEN`. Use `--health` for an on-demand health
check without executing strategies.

## 6. Wallet Operations

`scripts/wallet_ops.py` handles secure wallet funding and draining. Every action
requires founder confirmation and logs to `logs/wallet_ops.json`.

```bash
python3.11 scripts/wallet_ops.py fund --from 0xabc --to 0xdef --amount 1
python3.11 scripts/wallet_ops.py withdraw-all --from 0xhot --to 0xbank
python3.11 scripts/wallet_ops.py drain-to-cold --from 0xhot --to 0xcold
```

Use `--dry-run` to simulate without sending a transaction. State snapshots are
exported before and after each operation.

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
python3.11 ai/mutator/main.py --logs-dir logs --dry-run
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
* **Pause strategy:** `python3.11 scripts/batch_ops.py pause <strategy>`.
* **Rollback:** `python3.11 scripts/batch_ops.py rollback <strategy>` or use the DRP
  archive as shown above.

### Troubleshooting

* Check `logs/errors.log` for stack traces.
* Ensure RPC endpoints in `config.yaml` are reachable.
* Verify `http://localhost:8000/metrics` responds with Prometheus data.



---

Refer to [AGENTS.md](../AGENTS.md) and [PROJECT_BIBLE.md](../PROJECT_BIBLE.md) for
complete mutation, audit, and promotion policies.
