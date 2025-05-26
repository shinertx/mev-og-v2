import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
from pathlib import Path

from core.logger import StructuredLogger, register_hook


def test_structured_logging(tmp_path):
    log_file = tmp_path / "log.json"
    logger = StructuredLogger("test_mod", log_file=str(log_file))
    captured = []

    def hook(entry):
        captured.append(entry)

    register_hook(hook)
    logger.log(
        "event", tx_id="1", strategy_id="s", mutation_id="m", risk_level="low"
    )

    data = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert data[0]["module"] == "test_mod"
    assert data[0]["event"] == "event"
    assert captured and captured[0]["tx_id"] == "1"
