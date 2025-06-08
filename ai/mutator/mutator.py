"""Simple mutation agent for strategy evolution.

Module purpose and system role:
    - Coordinate scoring and pruning of strategies for AI-led adaptation.
    - Logs mutation decisions for further analysis.

Integration points and dependencies:
    - Depends on :func:`score_strategies` and :func:`prune_strategies`.
    - Uses :class:`core.logger.StructuredLogger` for event logging.

Simulation/test hooks and kill conditions:
    - Pure Python logic; deterministic and safe for unit testing.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, cast

from core.logger import StructuredLogger, log_error, make_json_safe
from datetime import datetime, timezone
import hashlib
import subprocess
from core.secret_manager import get_secret
from ai.mutation_log import log_mutation
from .score import score_strategies
from .prune import prune_strategies
from agents.founder_gate import founder_approved

LOGGER = StructuredLogger("mutator")


def _log_codex_diff(strategy_id: str, prompt: str) -> None:
    """Record prompt and patch hash for ``strategy_id``."""

    base = Path(os.getenv("CODEX_DIFF_DIR", "/last_3_codex_diffs"))
    base.mkdir(parents=True, exist_ok=True)
    file = base / f"{strategy_id}.json"

    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    patch_id = "unknown"
    try:
        diff = subprocess.run(
            ["git", "diff"], capture_output=True, text=True, check=True
        ).stdout
        if diff:
            patch_out = subprocess.run(
                ["git", "patch-id", "--stable"],
                input=diff,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            if patch_out:
                patch_id = patch_out.split()[0]
    except Exception:
        patch_id = "unknown"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "patch_id": patch_id,
        "prompt_hash": prompt_hash,
    }

    entries = []
    if file.exists():
        for line in file.read_text().splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    entries.append(entry)
    entries = entries[-3:]
    with file.open("w") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")


class Mutator:
    """LLM-driven strategy mutation orchestrator."""

    def __init__(
        self,
        metrics: Dict[str, Dict[str, Any]],
        *,
        live: bool | None = None,
        strategy_root: str = "strategies",
    ) -> None:
        self.metrics = metrics
        self.live = bool(live) if live is not None else os.getenv("MUTATOR_LIVE") == "1"
        self.strategy_root = Path(strategy_root)

    # ------------------------------------------------------------------
    def _model_call(self, prompt: str) -> str:
        """Submit ``prompt`` to the configured model API."""

        if not self.live:
            # dry-run mode returns prompt for testing/audit
            return json.dumps({"params": {}})

        try:
            import openai as openai_module  # pragma: no cover - external
            openai_client = cast(Any, openai_module)

            openai_client.api_key = get_secret("OPENAI_API_KEY")
            api_base = os.getenv("OPENAI_API_BASE")
            if api_base:
                openai_client.api_base = api_base
            resp = openai_client.ChatCompletion.create(
                model=os.getenv("MUTATION_MODEL", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
            )
            return cast(str, resp.choices[0].message.content)
        except Exception as exc:  # pragma: no cover - network errors
            raise RuntimeError(f"model API error: {exc}") from exc

    # ------------------------------------------------------------------
    def mutate(
        self, strategy_id: str, config: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Return mutated parameters for ``strategy_id`` via LLM."""

        path = self.strategy_root / strategy_id / "strategy.py"
        try:
            code = path.read_text()
        except Exception as exc:
            log_error("mutator", str(exc), strategy_id=strategy_id, event="read_fail")
            raise

        summary = json.dumps(
            make_json_safe({"strategy": strategy_id, "code": code[:2000], "config": config or {}})
        )
        response = self._model_call(summary)
        try:
            data = json.loads(response)
        except Exception as exc:
            log_error(
                "mutator",
                f"json parse error: {exc}",
                strategy_id=strategy_id,
                event="model_parse",
            )
            raise RuntimeError("invalid model response") from exc

        if not isinstance(data, dict) or not isinstance(data.get("params"), dict):
            log_error(
                "mutator",
                "invalid schema",
                strategy_id=strategy_id,
                event="model_schema",
            )
            raise RuntimeError("model output schema invalid")

        log_mutation(
            "mutate_strategy",
            strategy_id=strategy_id,
            before=config or {},
            after=data["params"],
            prompt=summary,
            response=data,
        )
        _log_codex_diff(strategy_id, summary)
        return cast(Dict[str, Any], data["params"])

    # ------------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        """Return scores and list of pruned strategies."""

        trace = os.getenv("TRACE_ID", str(uuid.uuid4()))
        if not founder_approved("mutator_run"):
            LOGGER.log(
                "mutation_blocked",
                mutation_id=os.getenv("MUTATION_ID", "dev"),
                strategy_id=",".join(self.metrics.keys()),
                risk_level="high",
                trace_id=trace,
            )
            return {"scores": [], "pruned": []}

        scores: List[Dict[str, Any]] = score_strategies(self.metrics)
        pruned = prune_strategies(self.metrics)
        LOGGER.log(
            "mutation_run",
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            strategy_id=",".join(self.metrics.keys()),
            risk_level="low",
            scores=scores,
            pruned=pruned,
            trace_id=trace,
        )
        return {"scores": scores, "pruned": pruned}
