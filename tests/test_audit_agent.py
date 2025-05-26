import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
from pathlib import Path

from ai.audit_agent import AuditAgent
from core.logger import StructuredLogger


def test_audit_summary(tmp_path):
    log_file = tmp_path / "strategy.json"
    logger = StructuredLogger("test_strategy", log_file=str(log_file))
    logger.log("run", error=None)
    logger.log("fail", error="oops")

    agent = AuditAgent(repo_root=str(Path(__file__).resolve().parents[1]))
    summary = agent.run_audit([str(log_file)])
    assert summary["failures"] == 1
    suggestions = agent.suggest_mutations(summary)
    assert suggestions

