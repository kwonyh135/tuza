import pandas as pd


def add_sma_vwma_indicators(df, short_window=50, long_window=200, vwma_window=100):
    result = df.copy()
    result["SMA50"] = result["close"].rolling(window=short_window).mean()
    result["SMA200"] = result["close"].rolling(window=long_window).mean()

    weighted_close = result["close"] * result["volume"]
    volume_sum = result["volume"].rolling(window=vwma_window).sum()
    result["VWMA100"] = weighted_close.rolling(window=vwma_window).sum() / volume_sum

    return result


def generate_signal(row):
    values = [row.get("SMA50"), row.get("SMA200"), row.get("close"), row.get("VWMA100")]
    if any(pd.isna(value) for value in values):
        return None

    if row["SMA50"] > row["SMA200"] and row["close"] > row["VWMA100"]:
        return "long"
    if row["SMA50"] < row["SMA200"] and row["close"] < row["VWMA100"]:
        return "short"
    return None


def run_backtest(
    df,
    exit_mode="fixed",
    stop_loss_pct=0.03,
    take_profit_pct=0.26,
    trail_activate_pct=0.03,
    trail_distance_pct=0.015,
):
    if exit_mode not in {"fixed", "trailing"}:
        raise ValueError("exit_mode must be 'fixed' or 'trailing'")

    trades = []
    position = None
    last_signal = None

    for index, row in df.iterrows():
        signal = generate_signal(row)

        if position is None:
            if signal in {"long", "short"} and signal != last_signal:
                position = {
                    "side": signal,
                    "entry_price": float(row["close"]),
                    "entry_time": row.get("datetime", row.get("timestamp", index)),
                    "entry_index": index,
                    "best_price": float(row["close"]),
                    "trail_active": False,
                }
            last_signal = signal
            continue

        exit_price = None
        exit_reason = None
        entry = position["entry_price"]
        side = position["side"]

        if side == "long":
            stop_price = entry * (1 - stop_loss_pct)
            take_profit_price = entry * (1 + take_profit_pct)

            if row["low"] <= stop_price:
                exit_price = stop_price
                exit_reason = "stop_loss"
            elif exit_mode == "fixed" and row["high"] >= take_profit_price:
                exit_price = take_profit_price
                exit_reason = "take_profit"
            elif exit_mode == "trailing":
                if row["high"] >= entry * (1 + trail_activate_pct):
                    position["trail_active"] = True
                if position["trail_active"]:
                    position["best_price"] = max(position["best_price"], float(row["high"]))
                    trail_stop = position["best_price"] * (1 - trail_distance_pct)
                    if row["close"] <= trail_stop:
                        exit_price = trail_stop
                        exit_reason = "trailing_stop"
            if exit_price is None and signal == "short":
                exit_price = float(row["close"])
                exit_reason = "opposite_signal"

        elif side == "short":
            stop_price = entry * (1 + stop_loss_pct)
            take_profit_price = entry * (1 - take_profit_pct)

            if row["high"] >= stop_price:
                exit_price = stop_price
                exit_reason = "stop_loss"
            elif exit_mode == "fixed" and row["low"] <= take_profit_price:
                exit_price = take_profit_price
                exit_reason = "take_profit"
            elif exit_mode == "trailing":
                if row["low"] <= entry * (1 - trail_activate_pct):
                    position["trail_active"] = True
                if position["trail_active"]:
                    position["best_price"] = min(position["best_price"], float(row["low"]))
                    trail_stop = position["best_price"] * (1 + trail_distance_pct)
                    if row["close"] >= trail_stop:
                        exit_price = trail_stop
                        exit_reason = "trailing_stop"
            if exit_price is None and signal == "long":
                exit_price = float(row["close"])
                exit_reason = "opposite_signal"

        if exit_price is not None:
            trades.append(
                _make_trade(
                    position,
                    exit_price,
                    row.get("datetime", row.get("timestamp", index)),
                    index,
                    exit_reason,
                )
            )
            position = None

        last_signal = signal

    if position is not None and not df.empty:
        last_index = df.index[-1]
        last = df.iloc[-1]
        trades.append(
            _make_trade(
                position,
                float(last["close"]),
                last.get("datetime", last.get("timestamp", last_index)),
                last_index,
                "end_of_data",
            )
        )

    return trades


def summarize_trades(trades):
    total_trades = len(trades)
    wins = sum(1 for trade in trades if trade["return_pct"] > 0)
    losses = sum(1 for trade in trades if trade["return_pct"] < 0)
    returns = [trade["return_pct"] for trade in trades]
    total_return = sum(returns)

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total_trades if total_trades else 0.0,
        "total_return_pct": total_return,
        "average_return_pct": total_return / total_trades if total_trades else 0.0,
        "max_drawdown_pct": max_drawdown,
        "long_trades": sum(1 for trade in trades if trade["side"] == "long"),
        "short_trades": sum(1 for trade in trades if trade["side"] == "short"),
    }


def _make_trade(position, exit_price, exit_time, exit_index, exit_reason):
    entry = position["entry_price"]
    if position["side"] == "long":
        return_pct = (exit_price - entry) / entry
    else:
        return_pct = (entry - exit_price) / entry

    return {
        "side": position["side"],
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "entry_index": position["entry_index"],
        "exit_index": exit_index,
        "entry_price": entry,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "return_pct": return_pct,
    }
