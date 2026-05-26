# Risk-First Backtest Design

## Goal

Adjust the SMA/VWMA backtest so it evaluates the user's primary goal: avoid large account losses before trying to maximize return.

## Risk Policy

- Keep futures leverage at `5x`.
- Limit planned loss per trade to `1%` of account equity.
- Position size is derived from stop distance, not from nearly all available balance.
- With a 3% price stop, 1% account risk, 0.06% taker fee per side, and 0.05% slippage per side, target notional exposure is roughly 31.06% of current equity before leverage margin.
- At 5x leverage, that notional requires roughly 6.21% of equity as initial margin, before exchange-specific maintenance margin rules.

This is fundamentally different from the current live bot. The live bot uses nearly the full account balance as margin at 5x leverage, so a 3% adverse price move can cost roughly 15% of account equity before fees and slippage.

## Cost Model

Backtests should include conservative transaction costs:

- Taker fee per side: configurable, default `0.0006` based on Bitget's commonly documented futures taker fee.
- Slippage per side: configurable, default `0.0005`.
- Funding: configurable future extension; not modeled in the first implementation because funding rates are time-varying.

## Metrics

Keep raw price-return metrics, but add account-risk metrics:

- Starting equity
- Ending equity
- Total account return
- Maximum equity drawdown
- Worst trade account return
- Average trade account return
- Margin usage estimate
- Number of trades stopped by risk constraints

## Live Bot Policy

Do not wire this into live orders yet. First validate the risk-adjusted backtest. The next live-bot change should add a risk manager that refuses new entries when account risk, daily drawdown, or position query state is unsafe.
