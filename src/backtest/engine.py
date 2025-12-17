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

TRADING_DAYS = 252


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
    borrow_cost_annual: float = 0.0,
    cash_rate_annual: float = 0.0,
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

    # Borrow cost applies to short notional (sum of abs(negative weights)).
    short_notional = (-shifted_weights.clip(upper=0.0)).sum(axis=1)
    borrow_cost_daily = borrow_cost_annual / TRADING_DAYS
    borrow_cost = borrow_cost_daily * short_notional

    # Cash earns a rate when net exposure is less than 1.0 (uninvested capital).
    net_exposure = shifted_weights.sum(axis=1)
    cash_weight = (1.0 - net_exposure).clip(lower=0.0)
    cash_return_daily = cash_rate_annual / TRADING_DAYS
    cash_return = cash_return_daily * cash_weight

    daily_returns_after_costs = portfolio_returns - tc_rate * turnover - borrow_cost + cash_return
    # First row corresponds to an undefined return period (no prior close); keep at 0.
    if not daily_returns_after_costs.empty:
        daily_returns_after_costs.iloc[0] = 0.0

    equity_curve = (1 + daily_returns_after_costs).cumprod()
    equity_curve.iloc[0] = 1.0  # enforce starting wealth exactly 1.0

    meta: Dict[str, Any] = {
        "transaction_cost_bps": transaction_cost_bps,
        "borrow_cost_annual": borrow_cost_annual,
        "cash_rate_annual": cash_rate_annual,
    }

    return BacktestResult(
        daily_returns=daily_returns_after_costs,
        equity_curve=equity_curve,
        weights=shifted_weights,
        turnover=turnover,
        meta=meta,
    )
