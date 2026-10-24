"""Prüft die festen Sicherheitsregeln aus FlexyBase und der Konfiguration."""

import importlib
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

import FlexyBase as base
from FlexyBase import (
    DAILY_LOSS_LIMIT,
    GUARDED_METHODS,
    MAX_LEVERAGE,
    RISK_PER_TRADE,
    FlexyBase,
    capped_leverage,
    risk_based_stake,
    total_loss_reached,
)
from FlexyStarter import FlexyStarter


NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
ALL_STRATEGIES = [FlexyStarter]


def enter_kwargs(**overrides):
    kwargs = dict(
        pair="BTC/USDT:USDT",
        order_type="limit",
        amount=0.001,
        rate=60000.0,
        time_in_force="GTC",
        current_time=NOW,
        entry_tag=None,
        side="long",
    )
    kwargs.update(overrides)
    return kwargs


# --- Hebel ---------------------------------------------------------------


@pytest.mark.parametrize(
    "wanted, exchange_max, expected",
    [
        (2.0, 125.0, 2.0),
        (10.0, 125.0, MAX_LEVERAGE),
        (10.0, 2.0, 2.0),
        (0.5, 125.0, 1.0),
    ],
)
def test_capped_leverage(wanted, exchange_max, expected):
    assert capped_leverage(wanted, exchange_max) == expected


def test_max_leverage_is_three():
    assert MAX_LEVERAGE == 3.0


def test_subclass_cannot_exceed_cap(make_strategy):
    class Greedy(FlexyStarter):
        def choose_leverage(self, pair, side, **kwargs):
            return 50.0

    strategy = make_strategy(Greedy)
    result = strategy.leverage(
        pair="BTC/USDT:USDT",
        current_time=NOW,
        current_rate=60000.0,
        proposed_leverage=1.0,
        max_leverage=125.0,
        entry_tag=None,
        side="short",
    )
    assert result == MAX_LEVERAGE


# --- Risiko pro Trade ----------------------------------------------------


def test_stake_limits_loss_to_risk_per_trade():
    stake = risk_based_stake(total_capital=250.0, stoploss=-0.10, min_stake=5.0, max_stake=250.0)
    assert stake == pytest.approx(50.0)
    assert stake * 0.10 == pytest.approx(250.0 * RISK_PER_TRADE)


def test_stake_skips_trade_when_exchange_minimum_too_high():
    assert risk_based_stake(total_capital=250.0, stoploss=-0.10, min_stake=60.0, max_stake=250.0) == 0


def test_stake_never_exceeds_available_balance():
    assert risk_based_stake(total_capital=250.0, stoploss=-0.10, min_stake=5.0, max_stake=30.0) == 30.0


def test_stake_requires_a_stoploss():
    assert risk_based_stake(total_capital=250.0, stoploss=0.0, min_stake=None, max_stake=250.0) == 0


def test_strategy_stoploss_is_set():
    for strategy_cls in ALL_STRATEGIES:
        assert -0.25 <= strategy_cls.stoploss < 0


# --- Gesamtverlust ---------------------------------------------------------


@pytest.mark.parametrize(
    "current, reached",
    [(250.0, False), (190.0, False), (187.5, True), (100.0, True)],
)
def test_total_loss_threshold(current, reached):
    assert total_loss_reached(250.0, current) is reached


def test_entries_blocked_after_total_loss(make_strategy):
    strategy = make_strategy(FlexyStarter, starting=250.0, current=180.0)
    assert strategy.confirm_trade_entry(**enter_kwargs()) is False
    assert strategy.confirm_trade_entry(**enter_kwargs(side="short")) is False
    assert len(strategy.dp.messages) == 1


def test_entries_allowed_before_total_loss(make_strategy):
    strategy = make_strategy(FlexyStarter, starting=250.0, current=200.0)
    assert strategy.confirm_trade_entry(**enter_kwargs()) is True
    assert strategy.dp.messages == []


# --- Tagesverlust und Schutzmechanismen ------------------------------------


def test_daily_loss_protection(make_strategy):
    protections = make_strategy(FlexyStarter).protections
    drawdown = next(p for p in protections if p["method"] == "MaxDrawdown")
    assert drawdown["max_allowed_drawdown"] == DAILY_LOSS_LIMIT == 0.05
    assert drawdown["lookback_period"] == 24 * 60


def test_protections_are_valid_for_freqtrade(make_strategy):
    from freqtrade.plugins.protectionmanager import ProtectionManager

    ProtectionManager.validate_protections(make_strategy(FlexyStarter).protections)


# --- Unterklassen umgehen die Regeln nicht ---------------------------------


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
@pytest.mark.parametrize("method", GUARDED_METHODS)
def test_guarded_methods_not_overridden(strategy_cls, method):
    defining = next(klass for klass in strategy_cls.__mro__ if method in vars(klass))
    assert defining is FlexyBase, f"{strategy_cls.__name__} überschreibt {method}"


def test_every_strategy_file_inherits_from_base():
    for path in Path(inspect.getfile(base)).parent.glob("*.py"):
        if path.stem == "FlexyBase":
            continue
        module = importlib.import_module(path.stem)
        classes = [
            obj
            for obj in vars(module).values()
            if inspect.isclass(obj) and obj.__module__ == module.__name__
        ]
        for klass in classes:
            assert issubclass(klass, FlexyBase), f"{klass.__name__} erbt nicht von FlexyBase"


# --- Konfiguration ---------------------------------------------------------


def test_config_is_safe(config):
    assert config["dry_run"] is True, "Echtgeld nur bewusst über eine private Konfiguration"
    assert config["trading_mode"] == "futures"
    assert config["margin_mode"] == "isolated"
    assert config["max_open_trades"] == 3
    assert config["order_types"]["stoploss_on_exchange"] is True
    assert config["exchange"]["key"] == "" and config["exchange"]["secret"] == ""
    assert config["telegram"]["token"] == ""


# --- Teststrategie läuft auf Kursdaten -------------------------------------


def test_starter_produces_signals_on_synthetic_prices(make_strategy):
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    close = 60000 * np.exp(np.cumsum(rng.normal(0, 0.01, 2000)))
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=len(close), freq="h", tz="UTC"),
            "open": close,
            "high": close * 1.005,
            "low": close * 0.995,
            "close": close,
            "volume": 100.0,
        }
    )
    strategy = make_strategy(FlexyStarter)
    meta = {"pair": "BTC/USDT:USDT"}
    frame = strategy.populate_indicators(frame, meta)
    frame = strategy.populate_entry_trend(frame, meta)
    frame = strategy.populate_exit_trend(frame, meta)

    assert frame["enter_long"].fillna(0).sum() > 0
    assert frame["enter_short"].fillna(0).sum() > 0
    assert frame["exit_long"].fillna(0).sum() > 0
