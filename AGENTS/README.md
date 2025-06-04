# AGENTS Environment

This document lists environment variables and Python packages used by automation agents and test harnesses.

**Python 3.11 Required**

You must use Python 3.11 and activate your virtual environment before running any `python` or `pip` command.

## New Variables

- `FLASHBOTS_AUTH_KEY` – private key used to sign Flashbots or SUAVE bundles.
- `FLASHBOTS_RPC_URL` – endpoint for Flashbots/SUAVE relay. Defaults to `https://relay.flashbots.net`.

## Dependencies

The `flashbots` Python package is required for bundle submission via Web3. Install via `python3.11 -m pip install -r requirements.txt`.
