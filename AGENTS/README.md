# AGENTS Environment

This document lists environment variables and Python packages used by automation agents and test harnesses.

## New Variables

- `FLASHBOTS_AUTH_KEY` – private key used to sign Flashbots or SUAVE bundles.
- `FLASHBOTS_RPC_URL` – endpoint for Flashbots/SUAVE relay. Defaults to `https://relay.flashbots.net`.
- `SIM_MARKET_EVENTS` – path to JSON events for `MarketEventFeedAdapter` dry-run.
- `DEX_FEED_URL` / `CEX_FEED_URL` – override default market feed endpoints.

## Dependencies

The `flashbots` Python package is required for bundle submission via Web3. Install via `pip install -r requirements.txt`.
