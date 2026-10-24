"""
FlexyBase: feste Sicherheitsregeln für alle Flexy-Strategien.

Jede Flexy-Strategie erbt von dieser Klasse. Die Regeln hier gelten immer,
egal welche Signale oder welches Lernmodell die Unterklasse verwendet:

- Hebel höchstens MAX_LEVERAGE, nur isolierte Margin (siehe config.json)
- Risiko pro Trade höchstens RISK_PER_TRADE des Kapitals
- Ab MAX_TOTAL_LOSS Gesamtverlust keine neuen Trades mehr
- Tagesverlust über DAILY_LOSS_LIMIT: Pause bis Mitternacht (UTC)

Unterklassen überschreiben nur `choose_leverage`, nie `leverage`,
`custom_stake_amount`, `confirm_trade_entry` oder `protections`.
Die Tests in tests/test_guardrails.py prüfen das.
"""

from datetime import datetime

from freqtrade.strategy import IStrategy


MAX_LEVERAGE = 3.0
RISK_PER_TRADE = 0.02
MAX_TOTAL_LOSS = 0.25
DAILY_LOSS_LIMIT = 0.05

# Diese Methoden tragen die Sicherheitsregeln und dürfen nicht überschrieben werden.
GUARDED_METHODS = ("leverage", "custom_stake_amount", "confirm_trade_entry", "protections")


def capped_leverage(wanted: float, exchange_max: float) -> float:
    """Gewünschten Hebel auf 1x bis MAX_LEVERAGE (und das Börsen-Maximum) begrenzen."""
    return max(1.0, min(wanted, MAX_LEVERAGE, exchange_max))


def risk_based_stake(
    total_capital: float,
    stoploss: float,
    min_stake: float | None,
    max_stake: float,
) -> float:
    """
    Einsatz (Margin) so wählen, dass ein Stop-Loss höchstens RISK_PER_TRADE kostet.

    In Freqtrade bezieht sich der Stop-Loss bei Futures auf den Einsatz, also
    kostet ein ausgelöster Stop-Loss genau Einsatz * |stoploss|.
    Gibt 0 zurück (Trade wird ausgelassen), wenn die Mindestgrösse der Börse
    mehr Risiko erzwingen würde.
    """
    if total_capital <= 0 or stoploss >= 0:
        return 0.0
    stake = min(total_capital * RISK_PER_TRADE / abs(stoploss), max_stake)
    if min_stake is not None and min_stake > stake:
        return 0.0
    return stake


def total_loss_reached(starting_balance: float, current_balance: float) -> bool:
    """True, sobald das Kapital um MAX_TOTAL_LOSS oder mehr gefallen ist."""
    if starting_balance <= 0:
        return False
    return current_balance <= starting_balance * (1 - MAX_TOTAL_LOSS)


class FlexyBase(IStrategy):
    INTERFACE_VERSION = 3

    can_short = True
    stoploss = -0.10
    use_custom_stoploss = False

    # Wird bei jedem Start einmal gemeldet, danach erst wieder nach einem Neustart.
    _total_loss_reported = False

    @property
    def protections(self):
        return [
            {
                # Tagesverlust-Grenze: über 5 % Verlust in 24 h -> Pause bis Mitternacht UTC
                "method": "MaxDrawdown",
                "calculation_mode": "equity",
                "lookback_period": 24 * 60,
                "trade_limit": 1,
                "max_allowed_drawdown": DAILY_LOSS_LIMIT,
                "unlock_at": "00:00",
            },
            {
                # Drei Stop-Losses innerhalb von 24 Kerzen -> 12 Kerzen Pause
                "method": "StoplossGuard",
                "lookback_period_candles": 24,
                "trade_limit": 3,
                "stop_duration_candles": 12,
                "only_per_pair": False,
            },
            {
                # Nach jedem Trade 2 Kerzen Pause auf demselben Paar
                "method": "CooldownPeriod",
                "stop_duration_candles": 2,
            },
        ]

    def choose_leverage(self, pair: str, side: str, **kwargs) -> float:
        """Von Unterklassen überschreibbar. Ergebnis wird immer auf MAX_LEVERAGE begrenzt."""
        return 1.0

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        wanted = self.choose_leverage(pair=pair, side=side, entry_tag=entry_tag)
        return capped_leverage(wanted, max_leverage)

    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float | None,
        max_stake: float,
        leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return risk_based_stake(
            total_capital=self.wallets.get_total_stake_amount(),
            stoploss=self.stoploss,
            min_stake=min_stake,
            max_stake=max_stake,
        )

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        if total_loss_reached(
            self.wallets.get_starting_balance(), self.wallets.get_total_stake_amount()
        ):
            if not self._total_loss_reported:
                self.dp.send_msg(
                    f"Flexy: Gesamtverlust von {MAX_TOTAL_LOSS:.0%} erreicht. "
                    "Keine neuen Trades mehr, bis du die Lage geprüft hast."
                )
                self._total_loss_reported = True
            return False
        return True
