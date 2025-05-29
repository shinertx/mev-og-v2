"""LLM-driven audit and mutation recommendation agent.

Module purpose and system role:
    - Parse logs and tests to produce audit summaries and mutation suggestions.
    - Designed for offline use without external network calls.

Integration points and dependencies:
    - Reads ``AGENTS.md`` for current guidelines.
    - Utilizes :class:`core.logger.StructuredLogger` for audit logging.

Simulation/test hooks and kill conditions:
    - Pure Python logic for unit tests; network access is not required.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, cast

from core.logger import StructuredLogger, log_error

LOGGER = StructuredLogger("audit_agent")


class AuditAgent:
    """Simple log-based audit analysis.

    The agent can operate entirely offline using :meth:`run_audit` and
    :meth:`suggest_mutations`.  For online verification, the
    :meth:`run_online_audit` method submits a prompt to OpenAI's API using the
    ``OPENAI_API_KEY`` environment variable and returns the model response as a
    string.
    """

    def __init__(self, repo_root: str | None = None) -> None:
        self.repo_root = Path(repo_root or Path(__file__).resolve().parents[1])

    # ------------------------------------------------------------------
    def read_agents_md(self) -> str:
        path = self.repo_root / "AGENTS.md"
        try:
            return path.read_text()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    def run_audit(self, log_paths: Iterable[str]) -> Dict[str, Any]:
        events: List[Dict[str, Any]] = []
        for p in log_paths:
            try:
                lines = Path(p).read_text().splitlines()
                events.extend(json.loads(line) for line in lines if line.strip())
            except Exception as exc:
                LOGGER.log("log_read_error", strategy_id=p, error=str(exc), risk_level="low")
                log_error("audit_agent", str(exc), event="log_read_error", strategy_id=str(p))
        failures = [e for e in events if e.get("error")]
        summary = {
            "total_events": len(events),
            "failures": len(failures),
            "status": "fail" if failures else "pass",
        }
        LOGGER.log(
            "audit_summary",
            strategy_id=",".join(Path(p).stem for p in log_paths),
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            risk_level="low",
            summary=summary,
        )
        return summary

    # ------------------------------------------------------------------
    def suggest_mutations(self, audit_summary: Dict[str, Any]) -> List[str]:
        suggestions: List[str] = []
        if audit_summary.get("failures", 0) > 0:
            suggestions.append("Address logged errors and rerun tests.")
        else:
            suggestions.append("No failures detected.")
        LOGGER.log(
            "mutation_suggestion",
            strategy_id="audit",
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            risk_level="low",
            suggestions=suggestions,
        )
        return suggestions

    # ------------------------------------------------------------------
    def run_online_audit(self, prompt: str) -> str:
        """Submit ``prompt`` to OpenAI and return the text response."""

        import openai as openai_module  # imported here to simplify testing/mocking
        openai_client = cast(Any, openai_module)

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")

        openai_client.api_key = api_key
        resp = openai_client.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        message = cast(str, resp.choices[0].message.content)
        LOGGER.log(
            "online_audit",
            strategy_id="audit",
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            risk_level="low",
            prompt=prompt,
            response=message,
        )
        return message
