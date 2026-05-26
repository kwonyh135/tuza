# Backtest Results - 2026-05-26

## Scope

Repository branch: `codex-sma-vwma-backtest`

This update adds offline BTC/USDT futures backtesting with:

- 1% account-risk position sizing at 5x leverage
- Fee and slippage assumptions
- 1h SMA50/SMA200/VWMA100 strategy comparison
- Screenshot-derived MA touch + RSI staged strategy
- Local CSV caching for 1h, 15m, and 5m datasets

CSV market data files are stored under `data/` locally and are intentionally ignored by git.

## Risk Model

- Starting equity: `1000 USDT`
- Risk per trade: `1%`
- Leverage: `5x`
- Stop loss: `3%` price move
- Taker fee assumption: `0.06%` per side
- Slippage assumption: `0.05%` per side

## SMA/VWMA 1-Year Result

Dataset:

- File: `data/BTCUSDT_1h_365d.csv`
- Candles: `8716`
- Period: `2025-05-26 14:00 UTC -> 2026-05-26 12:00 UTC`
- Approximate duration: `363.2 days`

Fixed exit:

- Trades: `51`
- Account return: `-1.94%`
- Ending equity: `980.57 USDT`
- Max account drawdown: `-8.65%`
- Worst trade: `-1.00%`

Trailing stop:

- Trades: `88`
- Account return: `+1.53%`
- Ending equity: `1015.27 USDT`
- Max account drawdown: `-10.82%`
- Worst trade: `-1.00%`

## Screenshot MA Touch + RSI Strategy

Indicator mapping:

- `ma1 = SMA 50`
- `ma2 = VWMA 100`
- `ma3 = SMA 200`

Stage rules:

- Stage 0 long setup: `ma3 > ma2 > ma1`, wide `ma1/ma3` distance, and price breaks/touches `ma1` or `ma2`
- Stage 0 short setup: `ma3 < ma2 < ma1`, wide `ma1/ma3` distance, and price breaks/touches `ma1` or `ma2`
- Stage 1 long: `RSI <= 30`
- Stage 2 long: `RSI <= 25`
- Stage 1 short: `RSI >= 70`
- Stage 2 short: `RSI >= 75`

### 5m

- Candles: `104597`
- Stage 0 long setups: `272`
- Stage 0 short setups: `179`
- RSI entry signals: `342`

Trailing stop:

- Trades: `51`
- Win rate: `58.82%`
- Account return: `+8.35%`
- Ending equity: `1083.53 USDT`
- Max account drawdown: `-5.45%`
- Worst trade: `-1.00%`

Fixed exit:

- Trades: `35`
- Account return: `-6.60%`
- Ending equity: `934.01 USDT`
- Max account drawdown: `-11.18%`

### 15m

- Candles: `34865`
- Stage 0 long setups: `272`
- Stage 0 short setups: `231`
- RSI entry signals: `371`

Trailing stop:

- Trades: `47`
- Win rate: `46.81%`
- Account return: `+0.77%`
- Ending equity: `1007.68 USDT`
- Max account drawdown: `-5.53%`
- Worst trade: `-1.00%`

Fixed exit:

- Trades: `41`
- Account return: `-4.74%`
- Ending equity: `952.57 USDT`
- Max account drawdown: `-7.73%`

### 1h

- Candles: `8716`
- Stage 0 long setups: `62`
- Stage 0 short setups: `24`
- RSI entry signals: `127`

Trailing stop:

- Trades: `16`
- Win rate: `43.75%`
- Account return: `-3.66%`
- Ending equity: `963.42 USDT`
- Max account drawdown: `-4.80%`
- Worst trade: `-1.00%`

Fixed exit:

- Trades: `12`
- Account return: `-7.42%`
- Ending equity: `925.78 USDT`
- Max account drawdown: `-9.55%`

## Current Read

For the screenshot-derived staged strategy, `5m + trailing stop` is the only configuration that currently clears a basic risk/reward sanity check. It returned `+8.35%` over roughly one year with `-5.45%` max account drawdown under the current assumptions.

This is still not ready for live trading. The next check should stress fees/slippage, test daily loss limits, and compare behavior across more historical regimes before wiring anything into `bot.py`.
