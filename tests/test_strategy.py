import unittest

import pandas as pd

from strategy import (
    add_sma_vwma_indicators,
    generate_signal,
    run_backtest,
    summarize_trades,
)


class StrategyTests(unittest.TestCase):
    def test_vwma_uses_volume_weighted_close(self):
        df = pd.DataFrame(
            {
                "close": [10.0, 20.0, 30.0],
                "volume": [1.0, 1.0, 2.0],
            }
        )

        result = add_sma_vwma_indicators(
            df, short_window=2, long_window=3, vwma_window=3
        )

        self.assertEqual(result.loc[2, "SMA50"], 25.0)
        self.assertEqual(result.loc[2, "SMA200"], 20.0)
        self.assertEqual(result.loc[2, "VWMA100"], 22.5)

    def test_generate_signal_prefers_long_when_above_vwma_in_uptrend(self):
        row = pd.Series(
            {"SMA50": 105.0, "SMA200": 100.0, "close": 110.0, "VWMA100": 108.0}
        )

        self.assertEqual(generate_signal(row), "long")

    def test_generate_signal_prefers_short_when_below_vwma_in_downtrend(self):
        row = pd.Series(
            {"SMA50": 95.0, "SMA200": 100.0, "close": 90.0, "VWMA100": 92.0}
        )

        self.assertEqual(generate_signal(row), "short")

    def test_fixed_exit_closes_long_at_take_profit(self):
        df = pd.DataFrame(
            {
                "timestamp": [1, 2, 3, 4],
                "datetime": pd.to_datetime(
                    [
                        "2026-01-01 00:00",
                        "2026-01-01 01:00",
                        "2026-01-01 02:00",
                        "2026-01-01 03:00",
                    ]
                ),
                "open": [100.0, 101.0, 102.0, 104.0],
                "high": [101.0, 102.0, 106.0, 104.5],
                "low": [99.0, 100.0, 101.0, 103.0],
                "close": [100.0, 101.0, 105.0, 104.0],
                "volume": [1.0, 1.0, 1.0, 1.0],
                "SMA50": [101.0, 101.0, 101.0, 101.0],
                "SMA200": [100.0, 100.0, 100.0, 100.0],
                "VWMA100": [99.0, 99.0, 99.0, 99.0],
            }
        )

        trades = run_backtest(
            df, exit_mode="fixed", stop_loss_pct=0.03, take_profit_pct=0.04
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "long")
        self.assertEqual(trades[0]["exit_reason"], "take_profit")
        self.assertAlmostEqual(trades[0]["return_pct"], 0.04)

    def test_trailing_exit_activates_and_closes_on_retracement(self):
        df = pd.DataFrame(
            {
                "timestamp": [1, 2, 3, 4],
                "datetime": pd.to_datetime(
                    [
                        "2026-01-01 00:00",
                        "2026-01-01 01:00",
                        "2026-01-01 02:00",
                        "2026-01-01 03:00",
                    ]
                ),
                "open": [100.0, 101.0, 105.0, 103.0],
                "high": [101.0, 106.0, 107.0, 103.5],
                "low": [99.0, 100.0, 104.0, 102.0],
                "close": [100.0, 105.0, 106.0, 102.0],
                "volume": [1.0, 1.0, 1.0, 1.0],
                "SMA50": [101.0, 101.0, 101.0, 101.0],
                "SMA200": [100.0, 100.0, 100.0, 100.0],
                "VWMA100": [99.0, 99.0, 99.0, 99.0],
            }
        )

        trades = run_backtest(
            df,
            exit_mode="trailing",
            stop_loss_pct=0.03,
            trail_activate_pct=0.03,
            trail_distance_pct=0.02,
        )

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["exit_reason"], "trailing_stop")
        self.assertAlmostEqual(trades[0]["exit_price"], 104.86)

    def test_summarize_trades_reports_basic_metrics(self):
        trades = [
            {"side": "long", "return_pct": 0.05},
            {"side": "short", "return_pct": -0.02},
        ]

        summary = summarize_trades(trades)

        self.assertEqual(summary["total_trades"], 2)
        self.assertEqual(summary["wins"], 1)
        self.assertAlmostEqual(summary["win_rate"], 0.5)
        self.assertAlmostEqual(summary["total_return_pct"], 0.03)
        self.assertEqual(summary["long_trades"], 1)
        self.assertEqual(summary["short_trades"], 1)


if __name__ == "__main__":
    unittest.main()
