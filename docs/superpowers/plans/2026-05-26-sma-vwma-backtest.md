# SMA/VWMA Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local backtest workflow for the 1h-first SMA50/SMA200/VWMA100 futures strategy with fixed-exit and trailing-stop comparison.

**Architecture:** Keep live trading code unchanged in `bot.py`. Add pure indicator, signal, and simulation functions in `strategy.py`, then add `backtest.py` as a CLI wrapper for public Bitget OHLCV fetching and report printing.

**Tech Stack:** Python, pandas, ccxt, unittest.

---

## File Structure

- Create `strategy.py`: indicator calculation, signal generation, trade simulation, and summary metrics.
- Create `backtest.py`: command-line runner that fetches public candles from Bitget and prints fixed/trailing comparison output.
- Create `tests/test_strategy.py`: focused unit tests for pure strategy behavior.
- Modify `README.md`: add a short backtest usage section.

### Task 1: Strategy Unit Tests

**Files:**
- Create: `tests/test_strategy.py`

- [ ] **Step 1: Write failing tests**

Add tests that import the desired API from `strategy.py`:

```python
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

        result = add_sma_vwma_indicators(df, short_window=2, long_window=3, vwma_window=3)

        self.assertEqual(result.loc[2, "SMA50"], 25.0)
        self.assertEqual(result.loc[2, "SMA200"], 20.0)
        self.assertEqual(result.loc[2, "VWMA100"], 22.5)

    def test_generate_signal_prefers_long_when_above_vwma_in_uptrend(self):
        row = pd.Series({"SMA50": 105.0, "SMA200": 100.0, "close": 110.0, "VWMA100": 108.0})

        self.assertEqual(generate_signal(row), "long")

    def test_generate_signal_prefers_short_when_below_vwma_in_downtrend(self):
        row = pd.Series({"SMA50": 95.0, "SMA200": 100.0, "close": 90.0, "VWMA100": 92.0})

        self.assertEqual(generate_signal(row), "short")

    def test_fixed_exit_closes_long_at_take_profit(self):
        df = pd.DataFrame(
            {
                "timestamp": [1, 2, 3, 4],
                "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00", "2026-01-01 03:00"]),
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

        trades = run_backtest(df, exit_mode="fixed", stop_loss_pct=0.03, take_profit_pct=0.04)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["side"], "long")
        self.assertEqual(trades[0]["exit_reason"], "take_profit")
        self.assertAlmostEqual(trades[0]["return_pct"], 0.04)

    def test_trailing_exit_activates_and_closes_on_retracement(self):
        df = pd.DataFrame(
            {
                "timestamp": [1, 2, 3, 4],
                "datetime": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 02:00", "2026-01-01 03:00"]),
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
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m unittest tests.test_strategy -v`

Expected: fails because `strategy` does not exist yet.

### Task 2: Strategy Implementation

**Files:**
- Create: `strategy.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: Implement pure strategy functions**

Create `strategy.py` with:

```python
import math

import pandas as pd


def add_sma_vwma_indicators(df, short_window=50, long_window=200, vwma_window=100):
    result = df.copy()
    result["SMA50"] = result["close"].rolling(window=short_window).mean()
    result["SMA200"] = result["close"].rolling(window=long_window).mean()
    weighted_close = result["close"] * result["volume"]
    volume_sum = result["volume"].rolling(window=vwma_window).sum()
    result["VWMA100"] = weighted_close.rolling(window=vwma_window).sum() / volume_sum
    return result
```

Then add `generate_signal`, `run_backtest`, and `summarize_trades` following the tested API.

- [ ] **Step 2: Run tests and verify pass**

Run: `python -m unittest tests.test_strategy -v`

Expected: all tests pass.

### Task 3: Backtest CLI

**Files:**
- Create: `backtest.py`
- Modify: `README.md`

- [ ] **Step 1: Add command-line runner**

Create `backtest.py` to:

- parse `--symbol`, `--timeframe`, `--limit`, `--since-days`
- fetch public OHLCV through `ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "future"}})`
- run fixed and trailing simulations
- print readable summaries
- fetch a small 5m sample and print latest close versus 5m VWMA100 as reference

- [ ] **Step 2: Document usage**

Add README usage:

```bash
python backtest.py --symbol BTC/USDT:USDT --timeframe 1h --limit 1000
```

- [ ] **Step 3: Smoke test**

Run: `python backtest.py --limit 300`

Expected: prints fixed and trailing summaries if network access is available. If the sandbox blocks network access, rerun with escalation.

### Task 4: Final Verification

**Files:**
- All changed files

- [ ] **Step 1: Run unit tests**

Run: `python -m unittest tests.test_strategy -v`

Expected: all tests pass.

- [ ] **Step 2: Run CLI help**

Run: `python backtest.py --help`

Expected: exits 0 and shows available options.

- [ ] **Step 3: Check git diff**

Run: `git diff -- README.md backtest.py strategy.py tests/test_strategy.py docs/superpowers/specs/2026-05-26-sma-vwma-backtest-design.md docs/superpowers/plans/2026-05-26-sma-vwma-backtest.md`

Expected: diff contains only the backtest feature, docs, and tests.

## Self-Review

- Spec coverage: indicators, 1h-first signals, fixed exit, trailing exit, 5m reference, CLI output, and tests are covered.
- Placeholder scan: no open TBD/TODO entries are left in executable work.
- Type consistency: tests and plan use `add_sma_vwma_indicators`, `generate_signal`, `run_backtest`, and `summarize_trades` consistently.
