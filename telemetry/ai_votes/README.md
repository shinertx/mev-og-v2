# AI Vote Logs

This directory stores JSON vote logs produced by the automated consensus agents.
Each file is named `ai_vote_<timestamp>.json` and contains a single JSON object:

```json
{
  "strategy_id": "my_strategy",
  "patch_hash": "abc123",
  "agent": "Codex_v1",
  "vote": true,
  "reason": "pass",
  "timestamp": "2025-01-01T00-00-00"
}
```

The environment variable `AI_VOTES_DIR` controls the location of these logs.
By default it points to `telemetry/ai_votes`. Tools read this directory to
check if quorum has been met before promoting a patch.
