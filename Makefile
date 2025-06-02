.PHONY: build up down test chaos simulate mutate export promote

build:
docker compose build

up:
docker compose up -d

down:
docker compose down

test:
    pytest -v && foundry test

chaos:
    pytest tests/test_adapters_chaos.py -v

simulate:
bash scripts/simulate_fork.sh --target=strategies/cross_domain_arb

mutate:
python ai/mutator/main.py

export:
bash scripts/export_state.sh

promote:
FOUNDER_TOKEN=dummy python ai/promote.py
