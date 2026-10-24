import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
STRATEGY_DIR = ROOT / "user_data" / "strategies"

# Freqtrade lädt Strategien aus diesem Ordner; die Tests importieren sie gleich.
sys.path.insert(0, str(STRATEGY_DIR))


@pytest.fixture
def config():
    return json.loads((ROOT / "user_data" / "config.json").read_text())


class FakeWallets:
    def __init__(self, starting: float, current: float):
        self.starting = starting
        self.current = current

    def get_starting_balance(self) -> float:
        return self.starting

    def get_total_stake_amount(self) -> float:
        return self.current


class FakeDataProvider:
    def __init__(self):
        self.messages = []

    def send_msg(self, message: str, **kwargs) -> None:
        self.messages.append(message)


@pytest.fixture
def make_strategy(config):
    def _make(strategy_cls, starting=250.0, current=250.0):
        strategy = strategy_cls(config)
        strategy.wallets = FakeWallets(starting, current)
        strategy.dp = FakeDataProvider()
        return strategy

    return _make
