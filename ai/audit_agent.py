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
from typing import Any, Dict, Iterable, List

from core.logger import StructuredLogger

LOGGER = StructuredLogger("audit_agent")


class AuditAgent:
    """Simple log-based audit analysis."""

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
                events.extend(json.loads(l) for l in lines if l.strip())
            except Exception as exc:
                LOGGER.log("log_read_error", strategy_id=p, error=str(exc), risk_level="low")
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
