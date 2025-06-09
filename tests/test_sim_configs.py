import json
from pathlib import Path

from scripts.validate_sim_configs import validate_file


def test_config_schema():
    base = Path('sim/configs')
    for file in base.glob('*.json'):
        validate_file(file)
        data = json.loads(file.read_text())
        assert all(k in data for k in ('env', 'block_number', 'strategy_id', 'expected_pnl', 'max_drawdown', 'validators'))


