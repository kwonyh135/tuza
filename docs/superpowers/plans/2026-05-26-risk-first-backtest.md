# Risk-First Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add account-risk-aware sizing and reporting to the SMA/VWMA backtest while keeping 5x leverage and limiting planned loss to 1% of equity per trade.

**Architecture:** Add pure risk functions to `risk.py`, keep signal simulation in `strategy.py`, and extend `backtest.py` to report both raw price-return metrics and account-risk metrics with fees/slippage. Live trading code stays unchanged.

**Tech Stack:** Python, pandas, unittest, ccxt.

---

## File Structure

- Create `risk.py`: risk configuration, position sizing, account trade PnL, and equity summary.
- Create `tests/test_risk.py`: deterministic tests for 1% risk sizing and cost-adjusted account PnL.
- Modify `backtest.py`: add risk CLI flags and print risk-adjusted summaries.
- Modify `README.md`: document conservative backtest mode and the reason live bot is not changed yet.

### Task 1: Risk Calculation Tests

**Files:**
- Create: `tests/test_risk.py`

- [ ] **Step 1: Write failing tests**

Test that a 3% stop with 1% account risk sizes notional to one-third of equity and that fees/slippage reduce account PnL.

- [ ] **Step 2: Run tests and verify failure**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_risk -v`

Expected: fails because `risk.py` does not exist yet.

### Task 2: Risk Module

**Files:**
- Create: `risk.py`
- Test: `tests/test_risk.py`

- [ ] **Step 1: Implement risk config and sizing**

Implement `RiskConfig`, `calculate_position`, `apply_account_pnl`, and `summarize_account_trades`.

- [ ] **Step 2: Run tests**

Run: `.\.venv\Scripts\python.exe -m unittest tests.test_risk -v`

Expected: all tests pass.

### Task 3: Backtest Reporting

**Files:**
- Modify: `backtest.py`
- Modify: `README.md`

- [ ] **Step 1: Add CLI risk flags**

Add `--starting-equity`, `--risk-per-trade`, `--leverage`, `--fee-rate`, and `--slippage`.

- [ ] **Step 2: Print risk summaries**

Print ending equity, account return, max account drawdown, worst trade, and average margin usage for fixed and trailing exits.

- [ ] **Step 3: Update README**

Document the risk-first interpretation and the difference from the live bot's current sizing.

### Task 4: Verification

**Files:**
- All changed files

- [ ] **Step 1: Run all tests**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Run risk-first backtest**

Run: `.\.venv\Scripts\python.exe backtest.py --limit 1000 --risk-per-trade 0.01 --leverage 5`

Expected: report includes account-risk summaries for fixed and trailing exits.
