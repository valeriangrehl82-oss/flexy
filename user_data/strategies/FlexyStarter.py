"""
FlexyStarter: einfache Teststrategie für Schritt 1.

Zweck: prüfen, dass Flexy technisch rund läuft (Daten, Orders, Stop-Loss,
Telegram). Sie ist NICHT für echtes Geld gedacht. Die lernende Strategie
mit FreqAI folgt in Schritt 2 und erbt ebenfalls von FlexyBase.

Logik: Trendfilter über zwei gleitende Durchschnitte, Einstieg bei einer
Gegenbewegung (RSI), Long im Aufwärtstrend, Short im Abwärtstrend.
"""

import talib.abstract as ta
from pandas import DataFrame

from FlexyBase import FlexyBase


class FlexyStarter(FlexyBase):
    timeframe = "1h"
    startup_candle_count = 200

    # Gewinnziele relativ zum Einsatz (mit Hebel), nach Minuten im Trade
    minimal_roi = {"0": 0.08, "360": 0.04, "1440": 0.01}

    def choose_leverage(self, pair: str, side: str, **kwargs) -> float:
        return 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        uptrend = dataframe["ema_fast"] > dataframe["ema_slow"]
        downtrend = dataframe["ema_fast"] < dataframe["ema_slow"]
        rsi_turns_up = (dataframe["rsi"] > 35) & (dataframe["rsi"].shift(1) <= 35)
        rsi_turns_down = (dataframe["rsi"] < 65) & (dataframe["rsi"].shift(1) >= 65)
        has_volume = dataframe["volume"] > 0

        dataframe.loc[uptrend & rsi_turns_up & has_volume, ["enter_long", "enter_tag"]] = (
            1,
            "trend_pullback_long",
        )
        dataframe.loc[downtrend & rsi_turns_down & has_volume, ["enter_short", "enter_tag"]] = (
            1,
            "trend_pullback_short",
        )
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[dataframe["rsi"] > 70, "exit_long"] = 1
        dataframe.loc[dataframe["rsi"] < 30, "exit_short"] = 1
        return dataframe
