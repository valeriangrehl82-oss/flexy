# Flexy

Flexy ist ein privater, vollautomatischer Trading-Bot für Krypto-Futures. Er baut auf
[Freqtrade](https://github.com/freqtrade/freqtrade) auf und lernt ab Schritt 2 mit FreqAI.

**Stand:** Schritt 1 (Fundament). Flexy läuft nur im Demo-Modus (`dry_run`). Die Strategie
`FlexyStarter` ist eine Teststrategie und nicht für echtes Geld gedacht.

## Sicherheitsregeln

Die Regeln stehen in [`FlexyBase.py`](user_data/strategies/FlexyBase.py) und in der
[Konfiguration](user_data/config.json). Jede Strategie erbt von `FlexyBase` und kann sie nicht
umgehen; die [Tests](tests/test_guardrails.py) prüfen das bei jeder Änderung.

| Regel | Wert |
| --- | --- |
| Hebel | höchstens 3x, nur isolierte Margin |
| Risiko pro Trade | höchstens 2 % des Kapitals |
| Offene Trades gleichzeitig | höchstens 3 |
| Stop-Loss | bei jedem Trade, direkt bei der Börse |
| Tagesverlust | über 5 % in 24 Stunden: Pause bis Mitternacht (UTC) |
| Gesamtverlust | ab 25 %: keine neuen Trades, Meldung per Telegram |
| API-Schlüssel | nur Handelsrecht, kein Auszahlungsrecht, nur in `.env` |

## Aufbau

```
user_data/
  config.json            Grundkonfiguration (Binance-Futures, Demo-Modus)
  config.backtest.json   feste Coin-Liste für Backtests
  strategies/
    FlexyBase.py         Sicherheitsregeln für alle Strategien
    FlexyStarter.py      Teststrategie für Schritt 1
tests/                   Tests der Sicherheitsregeln
docker-compose.yml       Betrieb auf dem Server
.env.example             Vorlage für Schlüssel und Telegram
```

## Entwicklung

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

Kursdaten laden und Backtest (braucht Zugriff auf die Binance-Schnittstellen):

```bash
freqtrade download-data -c user_data/config.json -c user_data/config.backtest.json \
  --userdir user_data --timeframes 1h --timerange 20220101-
freqtrade backtesting -c user_data/config.json -c user_data/config.backtest.json \
  --userdir user_data --strategy FlexyStarter --timerange 20220101-
```

## Betrieb auf dem Server (ab Schritt 3)

```bash
cp .env.example .env   # Schlüssel und Telegram eintragen
docker compose up -d
```
