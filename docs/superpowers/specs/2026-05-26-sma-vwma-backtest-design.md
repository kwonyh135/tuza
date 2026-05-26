# SMA/VWMA Backtest Design

## Goal

Prepare a local backtest workflow for a BTC/USDT Bitget futures strategy that prioritizes 1h candles using SMA 50, SMA 200, and VWMA 100, with optional 5m context for later refinement.

## Strategy

The first test version uses only closed 1h candles for trade decisions.

- Long bias: `SMA50 > SMA200`
- Long entry: long bias and previous closed 1h close is above `VWMA100`
- Short bias: `SMA50 < SMA200`
- Short entry: short bias and previous closed 1h close is below `VWMA100`
- No position stacking: one open position at a time
- Opposite signal closes the current position and can allow a later opposite entry

The 5m candle stream is fetched and summarized for reference only. It is not used for first-version entries or exits so the result is easy to compare against the existing 1h bot.

## Exit Models

The backtest compares two exit models:

- Fixed exit: stop loss at 3% adverse price move and take profit at 26% favorable price move.
- Trailing exit: stop loss at 3% adverse price move, trailing stop activates after 3% favorable price move, and exits after a 1.5% retracement from the best price after activation.

All percentages are raw price moves before leverage.

## Architecture

Add strategy/backtest logic outside `bot.py` to avoid changing live trading behavior. Keep pure calculation and simulation logic in `strategy.py`, and keep exchange fetching and command-line output in `backtest.py`.

## Output

The command-line backtest should print:

- Symbol, timeframe, date range, and candle count
- Summary for fixed exit and trailing exit
- Total trades, win rate, total return, maximum drawdown, average return, long/short split
- Recent 5m context if available

## Verification

Unit tests cover VWMA calculation, signal generation, fixed stop/take-profit exits, and trailing stop activation/exits. A smoke check runs the backtest script with synthetic-free live public candle fetching when network access is available.
