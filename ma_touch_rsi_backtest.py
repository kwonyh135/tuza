import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from backtest import (
    candles_for_days,
    default_data_path,
    fetch_ohlcv_frame,
    format_account_summary_lines,
    format_overview_lines,
    load_ohlcv_csv,
    save_ohlcv_csv,
)
from risk import RiskConfig, apply_account_pnl_series, summarize_account_trades
from strategy import summarize_trades


DEFAULT_SYMBOL = "BTC/USDT:USDT"
DEFAULT_DAYS = 365
DEFAULT_DATA_DIR = Path("data")


def rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=length, min_periods=length).mean()
    avg_loss = loss.rolling(window=length, min_periods=length).mean()
    relative_strength = avg_gain / avg_loss
    result = 100 - (100 / (1 + relative_strength))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    return result


def add_photo_strategy_indicators(df):
    result = df.copy()
    result["ma1"] = result["close"].rolling(window=50).mean()
    volume_sum = result["volume"].rolling(window=100).sum()
    result["ma2"] = (result["close"] * result["volume"]).rolling(window=100).sum() / volume_sum
    result["ma3"] = result["close"].rolling(window=200).mean()
    result["rsi"] = rsi(result["close"], length=14)
    return result


def attach_five_minute_rsi(hourly, five_minute):
    hourly_copy = hourly.copy()
    five = five_minute.copy()
    five["rsi_5m"] = rsi(five["close"], length=14)
    hourly_copy["_join_time"] = pd.to_datetime(
        hourly_copy["datetime"], utc=True
    ).map(lambda value: value.value)
    five["_join_time"] = pd.to_datetime(five["datetime"], utc=True).map(
        lambda value: value.value
    )
    return pd.merge_asof(
        hourly_copy.sort_values("_join_time"),
        five[["_join_time", "rsi_5m"]].dropna().sort_values("_join_time"),
        on="_join_time",
        direction="backward",
    ).drop(columns=["_join_time"])


def classify_rsi_stage(row, direction):
    value = row.get("rsi")
    if pd.isna(value):
        return None
    if direction == "long":
        if value <= 25:
            return 2
        if value <= 30:
            return 1
    elif direction == "short":
        if value >= 75:
            return 2
        if value >= 70:
            return 1
    return None


def generate_stage_signals(df, min_distance_pct):
    result = df.copy()
    result["signal"] = None
    result["stage"] = pd.NA
    result["stage0_long"] = False
    result["stage0_short"] = False

    active_long = False
    active_short = False

    for index, row in result.iterrows():
        if any(pd.isna(row.get(column)) for column in ["ma1", "ma2", "ma3", "close", "high", "low"]):
            continue

        long_stack = row["ma3"] > row["ma2"] > row["ma1"]
        short_stack = row["ma3"] < row["ma2"] < row["ma1"]
        distance_wide = abs(row["ma1"] - row["ma3"]) / row["close"] * 100 >= min_distance_pct
        touches_ma1 = row["low"] <= row["ma1"] <= row["high"]
        touches_ma2 = row["low"] <= row["ma2"] <= row["high"]

        if not long_stack or row["close"] > row["ma2"]:
            active_long = False
        if not short_stack or row["close"] < row["ma2"]:
            active_short = False

        if long_stack and distance_wide and row["close"] < row["ma1"] and row["close"] < row["ma2"] and (touches_ma1 or touches_ma2):
            active_long = True
            active_short = False
            result.at[index, "stage0_long"] = True

        if short_stack and distance_wide and row["close"] > row["ma1"] and row["close"] > row["ma2"] and (touches_ma1 or touches_ma2):
            active_short = True
            active_long = False
            result.at[index, "stage0_short"] = True

        if active_long:
            stage = classify_rsi_stage(row, "long")
            if stage is not None:
                result.at[index, "signal"] = "long"
                result.at[index, "stage"] = stage
        elif active_short:
            stage = classify_rsi_stage(row, "short")
            if stage is not None:
                result.at[index, "signal"] = "short"
                result.at[index, "stage"] = stage

    return result


def prepare_photo_strategy_frame(frame, timeframe):
    enriched = add_photo_strategy_indicators(frame)
    return generate_stage_signals(enriched, min_distance_for_timeframe(timeframe))


def min_distance_for_timeframe(timeframe):
    if timeframe in {"5m", "15m"}:
        return 1.5
    if timeframe == "1h":
        return 3.0
    return 1.0


def run_photo_backtest(frame, timeframe, exit_mode):
    prepared = prepare_photo_strategy_frame(frame, timeframe)
    trades = run_signal_backtest(
        prepared,
        exit_mode=exit_mode,
        stop_loss_pct=0.03,
        take_profit_pct=0.26,
        trail_activate_pct=0.03,
        trail_distance_pct=0.015,
    )
    return trades, prepared


def run_signal_backtest(
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
        signal = row.get("signal")
        if pd.isna(signal):
            signal = None

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
                make_trade(
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
            make_trade(
                position,
                float(last["close"]),
                last.get("datetime", last.get("timestamp", last_index)),
                last_index,
                "end_of_data",
            )
        )

    return trades


def make_trade(position, exit_price, exit_time, exit_index, exit_reason):
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


def load_or_fetch(symbol, timeframe, days, data_dir, refresh):
    path = Path(data_dir) / f"{symbol_for_path(symbol)}_{timeframe}_{days}d.csv"
    if path.exists() and not refresh:
        return load_ohlcv_csv(path), path, False

    limit = candles_for_days(timeframe, days)
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    frame = fetch_ohlcv_frame(
        symbol,
        timeframe,
        limit,
        since_ms=int(since.timestamp() * 1000),
    )
    save_ohlcv_csv(frame, path)
    return frame, path, True


def symbol_for_path(symbol):
    return symbol.split(":")[0].replace("/", "").upper()


def print_result(label, trades, risk_config, starting_equity):
    account_trades = apply_account_pnl_series(trades, risk_config)
    price_summary = summarize_trades(trades)
    account_summary = summarize_account_trades(account_trades, starting_equity)

    print(f"{label} - price basis")
    print(f"trades: {price_summary['total_trades']}")
    print(f"win rate: {price_summary['win_rate'] * 100:.2f}%")
    print(f"price return: {price_summary['total_return_pct'] * 100:.2f}%")
    print()
    for line in format_account_summary_lines(label, account_summary):
        print(line)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Backtest the MA touch + RSI strategy from the screenshots."
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--refresh-data", action="store_true")
    parser.add_argument("--starting-equity", type=float, default=1000.0)
    parser.add_argument("--risk-per-trade", type=float, default=0.01)
    parser.add_argument("--leverage", type=float, default=5.0)
    parser.add_argument("--fee-rate", type=float, default=0.0006)
    parser.add_argument("--slippage", type=float, default=0.0005)
    return parser


def main():
    args = build_parser().parse_args()
    risk_config = RiskConfig(
        starting_equity=args.starting_equity,
        risk_per_trade=args.risk_per_trade,
        stop_loss_pct=0.03,
        leverage=args.leverage,
        fee_rate=args.fee_rate,
        slippage_pct=args.slippage,
    )

    for timeframe in ["5m", "15m", "1h"]:
        frame, path, fetched = load_or_fetch(
            args.symbol, timeframe, args.days, args.data_dir, args.refresh_data
        )
        fixed_trades, prepared = run_photo_backtest(frame, timeframe, "fixed")
        trailing_trades, _ = run_photo_backtest(frame, timeframe, "trailing")

        start = frame.iloc[0]["datetime"].strftime("%Y-%m-%d %H:%M UTC")
        end = frame.iloc[-1]["datetime"].strftime("%Y-%m-%d %H:%M UTC")
        print("=" * 72)
        for line in format_overview_lines(
            args.symbol,
            timeframe,
            len(frame),
            start,
            end,
            candles_for_days(timeframe, args.days),
        ):
            print(line)
        print(f"data: {path} ({'downloaded' if fetched else 'cached'})")
        print(f"0단계 롱 setup: {int(prepared['stage0_long'].sum())}")
        print(f"0단계 숏 setup: {int(prepared['stage0_short'].sum())}")
        print(f"RSI 진입 신호: {prepared['signal'].notna().sum()}")
        print()
        print_result("Fixed", fixed_trades, risk_config, args.starting_equity)
        print()
        print_result("Trailing", trailing_trades, risk_config, args.starting_equity)
        print()


if __name__ == "__main__":
    main()
