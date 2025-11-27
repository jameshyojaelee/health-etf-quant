"""Tests for the backtest engine."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.backtest.engine import run_backtest  # noqa: E402


def test_constant_weights_returns_and_equity():
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    prices = pd.DataFrame(
        {
            "A": [100, 101, 102, 103, 104],
            "B": [200, 202, 204, 206, 208],
        },
        index=dates,
    )
    weights = pd.DataFrame(0.5, index=dates, columns=["A", "B"])

    result = run_backtest(prices, weights)

    asset_returns = prices.pct_change().fillna(0.0)
    expected_weights = weights.shift(1).fillna(0.0)
    expected_port = (expected_weights * asset_returns).sum(axis=1)
    expected_equity = (1 + expected_port).cumprod()
    expected_equity.iloc[0] = 1.0

    assert np.allclose(result.daily_returns.values, expected_port.values)
    assert np.allclose(result.equity_curve.values, expected_equity.values)
    assert np.allclose(result.turnover.values, 0.0)
    assert np.allclose(result.weights.values, expected_weights.values)


def test_turnover_and_transaction_costs():
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    prices = pd.DataFrame(
        {
            "A": [100, 110, 121],
            "B": [100, 100, 100],
        },
        index=dates,
    )
    weights = pd.DataFrame(
        {
            "A": [0.5, 1.0, 1.0],
            "B": [0.5, 0.0, 0.0],
        },
        index=dates,
    )

    result = run_backtest(prices, weights, transaction_cost_bps=10)

    asset_returns = prices.pct_change().fillna(0.0)
    expected_weights = weights.shift(1).fillna(0.0)
    expected_port = (expected_weights * asset_returns).sum(axis=1)
    expected_turnover = weights.diff().abs().sum(axis=1).fillna(0.0) / 2.0
    expected_costs = 0.001 * expected_turnover
    expected_daily = expected_port - expected_costs

    assert np.allclose(result.daily_returns.values, expected_daily.values)
    assert np.allclose(result.turnover.values, expected_turnover.values)
