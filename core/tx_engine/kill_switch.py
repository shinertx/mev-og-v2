import os

def kill_switch_triggered() -> bool:
    """Return True if kill switch file or env variable is present."""
    if os.environ.get('KILL_SWITCH_ACTIVE', '0') == '1':
        return True
    return os.path.exists('kill_switch.flag')
