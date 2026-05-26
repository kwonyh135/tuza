# tuza

Python-based automated Bitget futures trading bot.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

Fill `.env` with your Bitget and Telegram credentials before running.

## Strategy

- Symbol: `BTC/USDT:USDT`
- Timeframe: `1h`
- Leverage: `5x`
- Signal: SMA 60/80 crossover with ADX >= 25
- Stop loss: 3% price move
- Take profit: 26% price move

## Backtest

Run the SMA50/SMA200/VWMA100 test strategy without changing live trading code:

```bash
python backtest.py --symbol BTC/USDT:USDT --timeframe 1h --limit 1000
```

On Windows with the local virtual environment:

```powershell
.\.venv\Scripts\python.exe backtest.py --symbol BTC/USDT:USDT --timeframe 1h --limit 1000
```

The report compares fixed take-profit exits against a trailing-stop model and prints a 5m VWMA reference line for context.
Raw strategy lines use price moves before leverage. Account-risk lines include configurable taker fees and slippage, but not funding.

Risk-first mode keeps leverage configurable while sizing the position from account risk:

```powershell
.\.venv\Scripts\python.exe backtest.py --limit 1000 --risk-per-trade 0.01 --leverage 5
```

With a 3% stop and 1% account risk, the backtest targets a position where the planned stop loss is about 1% of equity after estimated fees and slippage. This is different from the live bot's current `USDT_USAGE = 0.98` sizing, where a 3% adverse move at 5x leverage can cost roughly 15% of equity before fees and slippage.

For a more meaningful 1h test, use about 2000 candles:

```powershell
.\.venv\Scripts\python.exe backtest.py --timeframe 1h --limit 2000 --risk-per-trade 0.01 --leverage 5
```

`1h` 2000 candles is roughly 83 days. That is close to Bitget's direct 1h futures candle query range, so it is a practical upper bound for exchange API-only testing. Use `5m` as a separate context check rather than the main decision timeframe:

```powershell
.\.venv\Scripts\python.exe backtest.py --timeframe 5m --limit 8000 --risk-per-trade 0.01 --leverage 5
```

For a one-year test, download and save the candles first:

```powershell
.\.venv\Scripts\python.exe backtest.py --timeframe 1h --days 365 --save-data data\BTCUSDT_1h_365d.csv --risk-per-trade 0.01 --leverage 5
```

Then rerun offline from the saved CSV without calling Bitget again:

```powershell
.\.venv\Scripts\python.exe backtest.py --data-file data\BTCUSDT_1h_365d.csv --risk-per-trade 0.01 --leverage 5
```

Local market data CSV files under `data/` are ignored by git.

## Security

Do not commit real API keys or Telegram tokens. Keep them only in `.env` on the server.
