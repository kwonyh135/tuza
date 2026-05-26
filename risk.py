from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    starting_equity: float = 1000.0
    risk_per_trade: float = 0.01
    stop_loss_pct: float = 0.03
    leverage: float = 5.0
    fee_rate: float = 0.0006
    slippage_pct: float = 0.0005


def calculate_position(equity, entry_price, config):
    if equity <= 0:
        raise ValueError("equity must be positive")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if config.stop_loss_pct <= 0:
        raise ValueError("stop_loss_pct must be positive")
    if config.leverage <= 0:
        raise ValueError("leverage must be positive")

    risk_amount = equity * config.risk_per_trade
    cost_buffer_pct = (config.fee_rate + config.slippage_pct) * 2
    notional = risk_amount / (config.stop_loss_pct + cost_buffer_pct)
    quantity = notional / entry_price
    initial_margin = notional / config.leverage

    return {
        "risk_amount": risk_amount,
        "notional": notional,
        "quantity": quantity,
        "initial_margin": initial_margin,
        "planned_loss_pct": risk_amount / equity,
        "margin_usage_pct": initial_margin / equity,
    }


def apply_account_pnl(trade, equity, config):
    position = calculate_position(equity, trade["entry_price"], config)
    quantity = position["quantity"]

    if trade["side"] == "long":
        gross_pnl = (trade["exit_price"] - trade["entry_price"]) * quantity
    elif trade["side"] == "short":
        gross_pnl = (trade["entry_price"] - trade["exit_price"]) * quantity
    else:
        raise ValueError("trade side must be 'long' or 'short'")

    exit_notional = abs(trade["exit_price"] * quantity)
    fee_cost = (position["notional"] + exit_notional) * config.fee_rate
    slippage_cost = (position["notional"] + exit_notional) * config.slippage_pct
    net_pnl = gross_pnl - fee_cost - slippage_cost
    equity_after = equity + net_pnl

    enriched = dict(trade)
    enriched.update(position)
    enriched.update(
        {
            "equity_before": equity,
            "gross_pnl": gross_pnl,
            "fee_cost": fee_cost,
            "slippage_cost": slippage_cost,
            "net_pnl": net_pnl,
            "equity_after": equity_after,
            "account_return_pct": net_pnl / equity,
        }
    )
    return enriched


def apply_account_pnl_series(trades, config):
    equity = config.starting_equity
    account_trades = []

    for trade in trades:
        account_trade = apply_account_pnl(trade, equity, config)
        account_trades.append(account_trade)
        equity = account_trade["equity_after"]
        if equity <= 0:
            break

    return account_trades


def summarize_account_trades(account_trades, starting_equity):
    if not account_trades:
        return {
            "total_trades": 0,
            "ending_equity": starting_equity,
            "total_account_return_pct": 0.0,
            "max_account_drawdown_pct": 0.0,
            "worst_trade_pct": 0.0,
            "average_trade_pct": 0.0,
            "average_margin_usage_pct": 0.0,
        }

    ending_equity = account_trades[-1]["equity_after"]
    peak = starting_equity
    max_drawdown = 0.0

    for trade in account_trades:
        peak = max(peak, trade["equity_before"])
        peak = max(peak, trade["equity_after"])
        drawdown = (trade["equity_after"] - peak) / peak
        max_drawdown = min(max_drawdown, drawdown)

    trade_returns = [trade["account_return_pct"] for trade in account_trades]
    margin_usages = [trade["margin_usage_pct"] for trade in account_trades]

    return {
        "total_trades": len(account_trades),
        "ending_equity": ending_equity,
        "total_account_return_pct": (ending_equity - starting_equity) / starting_equity,
        "max_account_drawdown_pct": max_drawdown,
        "worst_trade_pct": min(trade_returns),
        "average_trade_pct": sum(trade_returns) / len(trade_returns),
        "average_margin_usage_pct": sum(margin_usages) / len(margin_usages),
    }
