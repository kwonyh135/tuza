import argparse
import datetime as dt
import math
import time
from pathlib import Path

import pandas as pd
import requests

from strategy import add_sma_vwma_indicators, run_backtest, summarize_trades
from risk import RiskConfig, apply_account_pnl_series, summarize_account_trades


DEFAULT_SYMBOL = "BTC/USDT:USDT"
DEFAULT_TIMEFRAME = "1h"
DEFAULT_DATA_DIR = Path("data")


def timeframe_to_milliseconds(timeframe):
    unit = timeframe[-1]
    value = int(timeframe[:-1])
    multipliers = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
    }
    if unit not in multipliers:
        raise ValueError("timeframe must end with m, h, or d")
    return value * multipliers[unit]


def build_since_from_limit(timeframe, limit, now_ms=None):
    if now_ms is None:
        now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    return now_ms - limit * timeframe_to_milliseconds(timeframe)


def candles_for_days(timeframe, days):
    day_ms = 24 * 60 * 60 * 1000
    return math.ceil(days * day_ms / timeframe_to_milliseconds(timeframe))


def default_data_path(symbol, timeframe, days):
    safe_symbol = normalize_bitget_symbol(symbol)
    return DEFAULT_DATA_DIR / f"{safe_symbol}_{timeframe}_{days}d.csv"


def describe_recommended_limits(timeframe):
    if timeframe == "1h":
        return (
            "권장: 2000개 전후. 1h 2000개는 약 83일이며, "
            "Bitget 직접 조회 한계에 가까운 실전 상한입니다."
        )
    if timeframe == "5m":
        return (
            "권장: 5000~8000개. 5m는 노이즈가 커서 보조 확인용으로만 보고, "
            "Bitget 직접 조회 범위는 약 1개월로 제한됩니다."
        )
    return "권장: 전략 주기 기준 최소 3~6개월을 보되, 거래소 조회 가능 범위를 먼저 확인하세요."


def fetch_ohlcv_frame(symbol, timeframe, limit, since_ms=None, exchange=None, now_ms=None):
    if exchange is None:
        return fetch_bitget_history_frame(symbol, timeframe, limit, since_ms, now_ms)

    rows = []
    next_since = since_ms
    timeframe_ms = timeframe_to_milliseconds(timeframe)
    if now_ms is None:
        now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)

    while len(rows) < limit:
        if next_since is not None and next_since >= now_ms:
            break
        batch_limit = min(1000, limit - len(rows))
        previous_since = next_since
        batch = exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=next_since, limit=batch_limit
        )
        if not batch:
            break

        rows.extend(batch)

        next_since = batch[-1][0] + timeframe_ms
        if previous_since is not None and next_since <= previous_since:
            break

        time.sleep(exchange.rateLimit / 1000)

    df = _ohlcv_rows_to_frame(rows)
    return df.tail(limit).reset_index(drop=True)


def save_ohlcv_csv(df, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)


def load_ohlcv_csv(path):
    df = pd.read_csv(path)
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

    for column in required:
        df[column] = pd.to_numeric(df[column])

    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    else:
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)

    return df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def fetch_bitget_history_frame(symbol, timeframe, limit, since_ms=None, now_ms=None):
    if now_ms is None:
        now_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)

    rows = []
    end_ms = now_ms

    while len(rows) < limit:
        if since_ms is not None and end_ms <= since_ms:
            break

        params = {
            "symbol": normalize_bitget_symbol(symbol),
            "productType": "USDT-FUTURES",
            "granularity": to_bitget_granularity(timeframe),
            "endTime": end_ms,
            "limit": min(200, limit - len(rows)),
        }
        response = requests.get(
            "https://api.bitget.com/api/v2/mix/market/history-candles",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != "00000":
            raise RuntimeError(f"Bitget candle fetch failed: {payload}")

        batch = payload.get("data") or []
        if not batch:
            break

        filtered = [
            row for row in batch if since_ms is None or int(row[0]) >= since_ms
        ]
        rows = filtered + rows

        first_timestamp = min(int(row[0]) for row in batch)
        next_end = first_timestamp
        if next_end >= end_ms:
            break
        end_ms = next_end
        time.sleep(0.05)

    df = _ohlcv_rows_to_frame(rows)
    return df.tail(limit).reset_index(drop=True)


def _ohlcv_rows_to_frame(rows):
    normalized_rows = [
        [row[0], row[1], row[2], row[3], row[4], row[5]]
        for row in rows
    ]
    df = pd.DataFrame(
        normalized_rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    if df.empty:
        return df

    numeric_columns = ["timestamp", "open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.reset_index(drop=True)


def normalize_bitget_symbol(symbol):
    return symbol.split(":")[0].replace("/", "").upper()


def to_bitget_granularity(timeframe):
    if timeframe.endswith("h"):
        return timeframe[:-1] + "H"
    if timeframe.endswith("d"):
        return timeframe[:-1] + "D"
    return timeframe


def format_summary_lines(label, summary):
    display_label = _display_exit_label(label)
    return [
        f"{display_label} - 가격 기준",
        (
            f"거래 수: {summary['total_trades']}회 "
            f"(롱 {summary['long_trades']} / 숏 {summary['short_trades']})"
        ),
        f"승률: {summary['win_rate'] * 100:.2f}% ({summary['wins']}승/{summary['losses']}패)",
        f"가격 기준 총수익률: {summary['total_return_pct'] * 100:.2f}%",
        f"평균 거래 수익률: {summary['average_return_pct'] * 100:.2f}%",
        f"가격 기준 최대낙폭: {summary['max_drawdown_pct'] * 100:.2f}%",
    ]


def format_account_summary_lines(label, summary):
    display_label = _display_exit_label(label)
    return [
        f"{display_label} - 계좌 기준",
        f"종료 자산: {summary['ending_equity']:.2f} USDT",
        f"계좌 수익률: {summary['total_account_return_pct'] * 100:.2f}%",
        f"계좌 최대낙폭: {summary['max_account_drawdown_pct'] * 100:.2f}%",
        f"최악의 1회 거래: {summary['worst_trade_pct'] * 100:.2f}%",
        f"평균 1회 거래: {summary['average_trade_pct'] * 100:.2f}%",
        f"평균 증거금 사용률: {summary['average_margin_usage_pct'] * 100:.2f}%",
    ]


def format_overview_lines(symbol, timeframe, candle_count, start, end, requested_limit):
    days = timeframe_to_milliseconds(timeframe) * candle_count / (24 * 60 * 60 * 1000)
    return [
        f"심볼: {symbol}",
        f"기준 봉: {timeframe}",
        f"캔들: {candle_count}개 (요청 {requested_limit}개)",
        f"검증 기간: {start} -> {end} (약 {days:.1f}일)",
        describe_recommended_limits(timeframe),
    ]


def _display_exit_label(label):
    labels = {
        "Fixed": "고정 익절 방식",
        "Trailing": "트레일링 스탑 방식",
    }
    return labels.get(label, label)


def describe_five_minute_context(symbol):
    df = fetch_ohlcv_frame(symbol, "5m", 220)
    if df.empty:
        return "5m 참고: 캔들을 가져오지 못했습니다."

    enriched = add_sma_vwma_indicators(df)
    valid = enriched.dropna(subset=["VWMA100"])
    if valid.empty:
        return "5m 참고: VWMA100 계산에 필요한 캔들이 부족합니다."

    latest = valid.iloc[-1]
    relation = "위" if latest["close"] > latest["VWMA100"] else "아래"
    timestamp = latest["datetime"].strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"5m 참고: {timestamp} 종가 {latest['close']:.2f}는 "
        f"VWMA100 {latest['VWMA100']:.2f} {relation}에 있습니다."
    )


def format_five_minute_skip_notice():
    return "5m 참고: 오프라인 CSV 모드에서는 네트워크 조회를 건너뜁니다."


def build_parser():
    parser = argparse.ArgumentParser(
        description="1h 우선 SMA50/SMA200/VWMA100 전략을 Bitget 선물 캔들로 백테스트합니다."
    )
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--since-days", type=int, default=None)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--data-file", default=None)
    parser.add_argument("--save-data", default=None)
    parser.add_argument("--stop-loss", type=float, default=0.03)
    parser.add_argument("--take-profit", type=float, default=0.26)
    parser.add_argument("--trail-activate", type=float, default=0.03)
    parser.add_argument("--trail-distance", type=float, default=0.015)
    parser.add_argument("--starting-equity", type=float, default=1000.0)
    parser.add_argument("--risk-per-trade", type=float, default=0.01)
    parser.add_argument("--leverage", type=float, default=5.0)
    parser.add_argument("--fee-rate", type=float, default=0.0006)
    parser.add_argument("--slippage", type=float, default=0.0005)
    return parser


def main():
    args = build_parser().parse_args()

    requested_limit = args.limit
    since_ms = None
    if args.days is not None:
        requested_limit = candles_for_days(args.timeframe, args.days)
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
        since_ms = int(since.timestamp() * 1000)
    elif args.since_days is not None:
        requested_limit = candles_for_days(args.timeframe, args.since_days)
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.since_days)
        since_ms = int(since.timestamp() * 1000)
    else:
        since_ms = build_since_from_limit(args.timeframe, requested_limit)

    if args.data_file:
        raw = load_ohlcv_csv(args.data_file)
        requested_limit = len(raw)
    else:
        raw = fetch_ohlcv_frame(
            args.symbol, args.timeframe, requested_limit, since_ms=since_ms
        )
        save_path = args.save_data
        if save_path is None and args.days is not None:
            save_path = default_data_path(args.symbol, args.timeframe, args.days)
        if save_path is not None and not raw.empty:
            save_ohlcv_csv(raw, save_path)

    if raw.empty:
        raise SystemExit("OHLCV 캔들을 가져오지 못했습니다.")

    candles = add_sma_vwma_indicators(raw)
    fixed_trades = run_backtest(
        candles,
        exit_mode="fixed",
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
    )
    trailing_trades = run_backtest(
        candles,
        exit_mode="trailing",
        stop_loss_pct=args.stop_loss,
        trail_activate_pct=args.trail_activate,
        trail_distance_pct=args.trail_distance,
    )
    risk_config = RiskConfig(
        starting_equity=args.starting_equity,
        risk_per_trade=args.risk_per_trade,
        stop_loss_pct=args.stop_loss,
        leverage=args.leverage,
        fee_rate=args.fee_rate,
        slippage_pct=args.slippage,
    )
    fixed_account_trades = apply_account_pnl_series(fixed_trades, risk_config)
    trailing_account_trades = apply_account_pnl_series(trailing_trades, risk_config)

    start = raw.iloc[0]["datetime"].strftime("%Y-%m-%d %H:%M UTC")
    end = raw.iloc[-1]["datetime"].strftime("%Y-%m-%d %H:%M UTC")

    for line in format_overview_lines(
        args.symbol,
        args.timeframe,
        len(raw),
        start,
        end,
        requested_limit,
    ):
        print(line)
    if args.data_file:
        print(f"데이터 소스: 로컬 CSV ({args.data_file})")
    elif args.save_data is not None or args.days is not None:
        saved = args.save_data or default_data_path(args.symbol, args.timeframe, args.days)
        print(f"데이터 저장: {saved}")
    print()

    for line in format_summary_lines("Fixed", summarize_trades(fixed_trades)):
        print(line)
    print()
    for line in format_account_summary_lines(
        "Fixed",
        summarize_account_trades(fixed_account_trades, args.starting_equity),
    ):
        print(line)
    print()

    for line in format_summary_lines("Trailing", summarize_trades(trailing_trades)):
        print(line)
    print()
    for line in format_account_summary_lines(
        "Trailing",
        summarize_account_trades(trailing_account_trades, args.starting_equity),
    ):
        print(line)
    print()

    if args.data_file:
        print(format_five_minute_skip_notice())
    else:
        try:
            print(describe_five_minute_context(args.symbol))
        except Exception as exc:
            print(f"5m 참고를 가져오지 못했습니다: {exc}")


if __name__ == "__main__":
    main()
