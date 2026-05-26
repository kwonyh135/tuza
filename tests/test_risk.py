import unittest

from risk import (
    RiskConfig,
    apply_account_pnl,
    calculate_position,
    summarize_account_trades,
)


class RiskTests(unittest.TestCase):
    def test_position_size_limits_planned_loss_to_one_percent(self):
        config = RiskConfig(
            starting_equity=1000.0,
            risk_per_trade=0.01,
            stop_loss_pct=0.03,
            leverage=5.0,
            fee_rate=0.0006,
            slippage_pct=0.0005,
        )

        position = calculate_position(equity=1000.0, entry_price=100.0, config=config)

        self.assertAlmostEqual(position["risk_amount"], 10.0)
        self.assertAlmostEqual(position["notional"], 310.5590062112)
        self.assertAlmostEqual(position["quantity"], 3.1055900621)
        self.assertAlmostEqual(position["initial_margin"], 62.1118012422)
        self.assertAlmostEqual(position["planned_loss_pct"], 0.01)

    def test_apply_account_pnl_deducts_fees_and_slippage(self):
        config = RiskConfig(
            starting_equity=1000.0,
            risk_per_trade=0.01,
            stop_loss_pct=0.03,
            leverage=5.0,
            fee_rate=0.0006,
            slippage_pct=0.0005,
        )
        trade = {"side": "long", "entry_price": 100.0, "exit_price": 103.0}

        account_trade = apply_account_pnl(trade, equity=1000.0, config=config)

        self.assertAlmostEqual(account_trade["gross_pnl"], 9.3167701863)
        self.assertAlmostEqual(account_trade["fee_cost"], 0.3782608696)
        self.assertAlmostEqual(account_trade["slippage_cost"], 0.3152173913)
        self.assertAlmostEqual(account_trade["net_pnl"], 8.6232919255)
        self.assertAlmostEqual(account_trade["equity_after"], 1008.6232919255)

    def test_stop_loss_including_costs_stays_near_one_percent(self):
        config = RiskConfig(
            starting_equity=1000.0,
            risk_per_trade=0.01,
            stop_loss_pct=0.03,
            leverage=5.0,
            fee_rate=0.0006,
            slippage_pct=0.0005,
        )
        trade = {"side": "long", "entry_price": 100.0, "exit_price": 97.0}

        account_trade = apply_account_pnl(trade, equity=1000.0, config=config)

        self.assertGreaterEqual(account_trade["account_return_pct"], -0.01)

    def test_summarize_account_trades_reports_drawdown_and_worst_trade(self):
        account_trades = [
            {
                "equity_before": 1000.0,
                "equity_after": 990.0,
                "account_return_pct": -0.01,
                "initial_margin": 66.0,
                "margin_usage_pct": 0.066,
            },
            {
                "equity_before": 990.0,
                "equity_after": 999.9,
                "account_return_pct": 0.01,
                "initial_margin": 66.0,
                "margin_usage_pct": 0.0666666667,
            },
        ]

        summary = summarize_account_trades(account_trades, starting_equity=1000.0)

        self.assertEqual(summary["total_trades"], 2)
        self.assertAlmostEqual(summary["ending_equity"], 999.9)
        self.assertAlmostEqual(summary["total_account_return_pct"], -0.0001)
        self.assertAlmostEqual(summary["max_account_drawdown_pct"], -0.01)
        self.assertAlmostEqual(summary["worst_trade_pct"], -0.01)
        self.assertAlmostEqual(summary["average_margin_usage_pct"], 0.06633333335)


if __name__ == "__main__":
    unittest.main()
