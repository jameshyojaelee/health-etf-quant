"""Simple daily backtest engine for ETF portfolios."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.addHandler(logging.NullHandler())


@dataclass
class BacktestResult:
    """Container for backtest outputs."""

    daily_returns: pd.Series
    equity_curve: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    meta: Dict[str, Any]


def _validate_alignment(prices: pd.DataFrame, weights: pd.DataFrame) -> None:
    """Ensure indices and columns match before backtesting."""
    if not prices.index.equals(weights.index):
        raise ValueError("Prices and weights indices do not align.")
    if list(prices.columns) != list(weights.columns):
        raise ValueError("Prices and weights columns must match and be ordered identically.")


def run_backtest(
    prices: pd.DataFrame,
    weights: pd.DataFrame,
    transaction_cost_bps: float = 0.0,
) -> BacktestResult:
    """Run a daily backtest given prices and desired portfolio weights.

    Weights at time t are applied to returns from t to t+1 (i.e., shifted by one).
    """
    _validate_alignment(prices, weights)
    logger.info("Running backtest with transaction_cost_bps=%s", transaction_cost_bps)

    weights = weights.fillna(0.0)
    asset_returns = prices.pct_change().fillna(0.0)

    # Apply weights at time t to returns from t to t+1.
    shifted_weights = weights.shift(1).fillna(0.0)

    # Portfolio returns as weighted sum of asset returns.
    portfolio_returns = (shifted_weights * asset_returns).sum(axis=1)

    # Turnover is half L1 change in weights day over day.
    weight_changes = weights.diff().abs()
    turnover = weight_changes.sum(axis=1).fillna(0.0) / 2.0

    tc_rate = transaction_cost_bps / 10000.0
    daily_returns_after_costs = portfolio_returns - tc_rate * turnover

    equity_curve = (1 + daily_returns_after_costs).cumprod()
    equity_curve.iloc[0] = 1.0  # enforce starting wealth exactly 1.0

    meta: Dict[str, Any] = {
        "transaction_cost_bps": transaction_cost_bps,
    }

    return BacktestResult(
        daily_returns=daily_returns_after_costs,
        equity_curve=equity_curve,
        weights=shifted_weights,
        turnover=turnover,
        meta=meta,
    )
