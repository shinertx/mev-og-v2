import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.logger import StructuredLogger, log_error


class Dummy:
    pass


def test_log_non_serializable(tmp_path):
    log_file = tmp_path / "log.json"
    logger = StructuredLogger("safe", log_file=str(log_file))
    logger.log("event", obj=Dummy())
    data = json.loads(log_file.read_text().splitlines()[0])
    assert data["obj"] == "<Dummy>"


def test_log_error_non_serializable(tmp_path, monkeypatch):
    err_file = tmp_path / "err.log"
    monkeypatch.setenv("ERROR_LOG_FILE", str(err_file))
    log_error("test_mod", "boom", detail=Dummy())
    entry = json.loads(err_file.read_text().splitlines()[0])
    assert entry["detail"] == "<Dummy>"
