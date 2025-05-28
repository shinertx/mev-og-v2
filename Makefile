.PHONY: build up down test simulate mutate export promote

build:
docker compose build

up:
docker compose up -d

down:
docker compose down

test:
pytest -v && foundry test

simulate:
bash scripts/simulate_fork.sh --target=strategies/cross_domain_arb

mutate:
python ai/mutator/main.py

export:
bash scripts/export_state.sh

promote:
FOUNDER_APPROVED=1 python ai/promote.py
