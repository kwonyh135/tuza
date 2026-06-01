import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backtest import (
    build_since_from_limit,
    candles_for_days,
    describe_recommended_limits,
    fetch_bitget_history_frame,
    fetch_ohlcv_frame,
    format_five_minute_skip_notice,
    format_account_summary_lines,
    format_overview_lines,
    format_summary_lines,
    load_ohlcv_csv,
    save_ohlcv_csv,
)


class BacktestCliTests(unittest.TestCase):
    def test_format_summary_lines_renders_percent_metrics(self):
        summary = {
            "total_trades": 2,
            "wins": 1,
            "losses": 1,
            "win_rate": 0.5,
            "total_return_pct": 0.03,
            "average_return_pct": 0.015,
            "max_drawdown_pct": -0.02,
            "long_trades": 1,
            "short_trades": 1,
        }

        lines = format_summary_lines("Fixed", summary)

        self.assertIn("고정 익절 방식", lines[0])
        self.assertIn("거래 수: 2회", lines[1])
        self.assertIn("승률: 50.00%", lines[2])
        self.assertIn("가격 기준 총수익률: 3.00%", lines[3])
        self.assertIn("가격 기준 최대낙폭: -2.00%", lines[5])

    def test_format_account_summary_lines_renders_risk_metrics(self):
        summary = {
            "total_trades": 2,
            "ending_equity": 999.9,
            "total_account_return_pct": -0.0001,
            "max_account_drawdown_pct": -0.01,
            "worst_trade_pct": -0.01,
            "average_trade_pct": 0.0,
            "average_margin_usage_pct": 0.066,
        }

        lines = format_account_summary_lines("Trailing", summary)

        self.assertIn("트레일링 스탑 방식 - 계좌 기준", lines[0])
        self.assertIn("종료 자산: 999.90 USDT", lines[1])
        self.assertIn("계좌 수익률: -0.01%", lines[2])
        self.assertIn("계좌 최대낙폭: -1.00%", lines[3])
        self.assertIn("평균 증거금 사용률: 6.60%", lines[6])

    def test_format_overview_lines_renders_korean_context(self):
        lines = format_overview_lines(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            candle_count=2000,
            start="2026-03-04 03:00 UTC",
            end="2026-05-26 10:00 UTC",
            requested_limit=2000,
        )

        self.assertIn("심볼: BTC/USDT:USDT", lines[0])
        self.assertIn("캔들: 2000개", lines[2])
        self.assertIn("약 83.3일", lines[3])

    def test_describe_recommended_limits_for_one_hour(self):
        text = describe_recommended_limits("1h")

        self.assertIn("권장: 2000개", text)
        self.assertIn("Bitget 직접 조회 한계", text)

    def test_build_since_from_limit_pages_back_from_now(self):
        now_ms = 1_700_000_000_000

        since_ms = build_since_from_limit("1h", 2000, now_ms=now_ms)

        self.assertEqual(since_ms, now_ms - 2000 * 60 * 60 * 1000)

    def test_candles_for_days_calculates_one_year_hourly_count(self):
        self.assertEqual(candles_for_days("1h", 365), 8760)

    def test_fetch_ohlcv_frame_keeps_paging_when_exchange_returns_small_batches(self):
        exchange = FakeExchange(batch_size=200)

        frame = fetch_ohlcv_frame(
            "BTC/USDT:USDT",
            "1h",
            450,
            since_ms=1_700_000_000_000,
            exchange=exchange,
            now_ms=1_700_000_000_000 + 1000 * 60 * 60 * 1000,
        )

        self.assertEqual(len(frame), 450)
        self.assertEqual(exchange.calls, 3)

    def test_fetch_ohlcv_frame_stops_before_requesting_beyond_now(self):
        exchange = FakeExchange(batch_size=200)
        since_ms = 1_700_000_000_000

        frame = fetch_ohlcv_frame(
            "BTC/USDT:USDT",
            "1h",
            450,
            since_ms=since_ms,
            exchange=exchange,
            now_ms=since_ms + 200 * 60 * 60 * 1000,
        )

        self.assertEqual(len(frame), 200)
        self.assertEqual(exchange.calls, 1)

    def test_fetch_bitget_history_frame_keeps_page_boundary_candle(self):
        base = 1_700_000_000_000
        one_hour = 60 * 60 * 1000
        candles = [
            [
                str(base + index * one_hour),
                "100.0",
                "101.0",
                "99.0",
                "100.0",
                "1.0",
            ]
            for index in range(6)
        ]
        calls = []

        def fake_get(url, params, timeout):
            self.assertEqual(url, "https://api.bitget.com/api/v2/mix/market/history-candles")
            self.assertEqual(timeout, 20)
            calls.append(params["endTime"])
            eligible = [row for row in candles if int(row[0]) < params["endTime"]]
            return FakeBitgetResponse(eligible[-3:])

        with patch("backtest.requests.get", side_effect=fake_get):
            frame = fetch_bitget_history_frame(
                "BTC/USDT:USDT",
                "1h",
                6,
                since_ms=base,
                now_ms=base + 6 * one_hour,
            )

        self.assertEqual(list(frame["timestamp"]), [base + index * one_hour for index in range(6)])
        self.assertEqual(calls, [base + 6 * one_hour, base + 3 * one_hour])

    def test_save_and_load_ohlcv_csv_round_trips_dataset(self):
        frame = fetch_ohlcv_frame(
            "BTC/USDT:USDT",
            "1h",
            3,
            since_ms=1_700_000_000_000,
            exchange=FakeExchange(batch_size=3),
            now_ms=1_700_000_000_000 + 10 * 60 * 60 * 1000,
        )

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "btc_1h.csv"

            save_ohlcv_csv(frame, path)
            loaded = load_ohlcv_csv(path)

        self.assertEqual(len(loaded), 3)
        self.assertEqual(list(loaded.columns), list(frame.columns))
        self.assertEqual(int(loaded.loc[0, "timestamp"]), int(frame.loc[0, "timestamp"]))

    def test_format_five_minute_skip_notice_explains_offline_mode(self):
        self.assertIn("오프라인 CSV", format_five_minute_skip_notice())


class FakeExchange:
    rateLimit = 0

    def __init__(self, batch_size):
        self.batch_size = batch_size
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls += 1
        rows = []
        current = since
        for index in range(min(self.batch_size, limit)):
            timestamp = current + index * 60 * 60 * 1000
            rows.append([timestamp, 100.0, 101.0, 99.0, 100.0, 1.0])
        return rows


class FakeBitgetResponse:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return {"code": "00000", "data": self.rows}


if __name__ == "__main__":
    unittest.main()
