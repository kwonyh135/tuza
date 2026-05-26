import unittest

import pandas as pd

from ma_touch_rsi_backtest import (
    add_photo_strategy_indicators,
    attach_five_minute_rsi,
    classify_rsi_stage,
    generate_stage_signals,
    rsi,
    run_signal_backtest,
)


class MaTouchRsiStrategyTests(unittest.TestCase):
    def test_rsi_reaches_high_value_after_persistent_gains(self):
        series = pd.Series(
            [
                100,
                101,
                102,
                103,
                104,
                105,
                106,
                107,
                108,
                109,
                110,
                111,
                112,
                113,
                114,
            ],
            dtype=float,
        )

        result = rsi(series, length=14)

        self.assertEqual(result.iloc[-1], 100.0)

    def test_add_photo_strategy_indicators_maps_ma_names(self):
        df = pd.DataFrame(
            {
                "close": [float(i) for i in range(1, 205)],
                "volume": [1.0 for _ in range(204)],
            }
        )

        result = add_photo_strategy_indicators(df)

        self.assertAlmostEqual(result.iloc[-1]["ma1"], sum(range(155, 205)) / 50)
        self.assertAlmostEqual(result.iloc[-1]["ma3"], sum(range(5, 205)) / 200)
        self.assertAlmostEqual(result.iloc[-1]["ma2"], sum(range(105, 205)) / 100)

    def test_classify_rsi_stage_for_long_and_short(self):
        row = pd.Series(
            {
                "rsi": 24.0,
            }
        )

        self.assertEqual(classify_rsi_stage(row, "long"), 2)
        self.assertIsNone(classify_rsi_stage(row, "short"))

        row["rsi"] = 72.0
        self.assertEqual(classify_rsi_stage(row, "short"), 1)
        self.assertIsNone(classify_rsi_stage(row, "long"))

    def test_generate_stage_signals_activates_long_after_ma_break_then_rsi(self):
        frame = pd.DataFrame(
            {
                "ma1": [90.0, 89.0, 88.0],
                "ma2": [100.0, 99.0, 98.0],
                "ma3": [110.0, 109.0, 108.0],
                "high": [102.0, 89.5, 88.5],
                "low": [88.0, 87.0, 86.0],
                "close": [89.0, 88.0, 87.0],
                "rsi": [45.0, 29.0, 24.0],
            }
        )

        result = generate_stage_signals(frame, min_distance_pct=3.0)

        self.assertIsNone(result.loc[0, "signal"])
        self.assertEqual(result.loc[1, "signal"], "long")
        self.assertEqual(result.loc[1, "stage"], 1)
        self.assertEqual(result.loc[2, "signal"], "long")
        self.assertEqual(result.loc[2, "stage"], 2)

    def test_generate_stage_signals_activates_short_after_ma_break_then_rsi(self):
        frame = pd.DataFrame(
            {
                "ma1": [110.0, 111.0],
                "ma2": [100.0, 101.0],
                "ma3": [90.0, 91.0],
                "high": [112.0, 113.0],
                "low": [99.0, 110.0],
                "close": [111.0, 112.0],
                "rsi": [45.0, 76.0],
            }
        )

        result = generate_stage_signals(frame, min_distance_pct=3.0)

        self.assertIsNone(result.loc[0, "signal"])
        self.assertEqual(result.loc[1, "signal"], "short")
        self.assertEqual(result.loc[1, "stage"], 2)

    def test_stage_signal_is_blocked_when_ma1_ma3_distance_is_too_small(self):
        frame = pd.DataFrame(
            {
                "ma1": [99.0, 99.0],
                "ma2": [100.0, 100.0],
                "ma3": [101.0, 101.0],
                "high": [101.0, 101.0],
                "low": [98.0, 98.0],
                "close": [99.0, 99.0],
                "rsi": [29.0, 24.0],
            }
        )

        result = generate_stage_signals(frame, min_distance_pct=3.0)

        self.assertTrue(result["signal"].isna().all())

    def test_legacy_short_signal_shape_is_no_longer_direct_signal(self):
        row = pd.Series(
            {
                "ma1": 110.0,
                "ma2": 100.0,
                "ma3": 90.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "rsi": 72.0,
            }
        )

        self.assertEqual(classify_rsi_stage(row, "short"), 1)

    def test_run_signal_backtest_uses_real_prices_for_exits(self):
        frame = pd.DataFrame(
            {
                "timestamp": [1, 2, 3],
                "datetime": pd.to_datetime(
                    ["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00"],
                    utc=True,
                ),
                "open": [100.0, 101.0, 105.0],
                "high": [101.0, 106.0, 106.0],
                "low": [99.0, 100.0, 104.0],
                "close": [100.0, 105.0, 105.0],
                "signal": ["long", None, None],
            }
        )

        trades = run_signal_backtest(frame, exit_mode="fixed", take_profit_pct=0.04)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["entry_price"], 100.0)
        self.assertAlmostEqual(trades[0]["exit_price"], 104.0)
        self.assertEqual(trades[0]["exit_reason"], "take_profit")

    def test_attach_five_minute_rsi_accepts_different_datetime_precision(self):
        hourly = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    ["2026-01-01 01:00", "2026-01-01 02:00"], utc=True
                ).astype("datetime64[us, UTC]"),
                "close": [100.0, 101.0],
            }
        )
        five_minute = pd.DataFrame(
            {
                "datetime": pd.date_range(
                    "2026-01-01 00:00", periods=40, freq="5min", tz="UTC"
                ).astype("datetime64[ms, UTC]"),
                "close": [float(100 + i) for i in range(40)],
            }
        )

        merged = attach_five_minute_rsi(hourly, five_minute)

        self.assertEqual(len(merged), 2)
        self.assertIn("rsi_5m", merged.columns)


if __name__ == "__main__":
    unittest.main()
