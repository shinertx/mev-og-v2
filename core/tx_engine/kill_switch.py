"""Kill switch utilities for halting transaction execution."""

import os
from pathlib import Path

from core.logger import StructuredLogger, log_error

ENV_VAR = "KILL_SWITCH"


def _flag_file() -> Path:
    """Return path to the kill switch flag file."""

    return Path(os.getenv("KILL_SWITCH_FLAG_FILE", "./flags/kill_switch.txt"))


def _log_file() -> Path:
    """Return path to the kill switch log file."""

    return Path(os.getenv("KILL_SWITCH_LOG_FILE", "logs/kill_log.json"))




def flag_file() -> Path:
    """Public accessor for current flag file path."""
    return _flag_file()


def log_file() -> Path:
    """Public accessor for current log file path."""
    return _log_file()


def init_kill_switch() -> None:
    """Initialize kill switch logging and directories."""
    lf = _log_file()
    lf.parent.mkdir(parents=True, exist_ok=True)
    if not lf.exists():
        lf.touch()


def kill_switch_triggered() -> bool:
    """Check if kill switch is active via environment or flag file."""
    env_active = os.getenv(ENV_VAR) == "1"
    file_active = _flag_file().exists()
    return env_active or file_active


def record_kill_event(origin_module: str) -> None:
    """Append a structured kill event to the log file."""
    source = (
        "env"
        if os.getenv(ENV_VAR) == "1"
        else "file" if _flag_file().exists() else "unknown"
    )
    logger = StructuredLogger("kill_switch", log_file=str(_log_file()))
    logger.log(
        "kill_switch",
        origin_module=origin_module,
        kill_event=True,
        strategy_id=origin_module,
        mutation_id=os.getenv("MUTATION_ID", "dev"),
        risk_level="high",
        trace_id=os.getenv("TRACE_ID", ""),
        block=os.getenv("BLOCK", ""),
        triggered_by=source,
    )
    log_error(
        origin_module,
        "kill switch triggered",
        event="kill_switch",
        strategy_id=origin_module,
        mutation_id=os.getenv("MUTATION_ID", "dev"),
        risk_level="high",
        trace_id=os.getenv("TRACE_ID", ""),
        block=os.getenv("BLOCK", ""),
    )
    try:
        from core import metrics as _metrics
        _metrics.record_kill_event_metric()
    except Exception:
        pass


def clear_kill_switch() -> None:
    """Remove kill switch flag file and environment variable."""
    try:
        ff = _flag_file()
        if ff.exists():
            ff.unlink()
    except Exception:
        pass
    os.environ.pop(ENV_VAR, None)


def record_recovery_event(origin_module: str) -> None:
    """Log kill switch recovery event."""
    logger = StructuredLogger("kill_switch", log_file=str(_log_file()))
    logger.log(
        "kill_recovered",
        origin_module=origin_module,
        kill_event=False,
        strategy_id=origin_module,
        mutation_id=os.getenv("MUTATION_ID", "dev"),
        risk_level="low",
        trace_id=os.getenv("TRACE_ID", ""),
        block=os.getenv("BLOCK", ""),
    )
