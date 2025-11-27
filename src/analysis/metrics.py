"""Performance metrics such as CAGR, Sharpe, and drawdowns."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def compute_cagr(daily_returns: pd.Series) -> float:
    """Compound annual growth rate from daily returns."""
    if daily_returns.empty:
        return np.nan
    total_return = float((1 + daily_returns).prod())
    n_days = daily_returns.shape[0]
    return total_return ** (TRADING_DAYS / n_days) - 1


def compute_annual_vol(daily_returns: pd.Series) -> float:
    """Annualized volatility from daily returns (assumes 252 trading days)."""
    if daily_returns.empty:
        return np.nan
    return float(daily_returns.std(ddof=0) * np.sqrt(TRADING_DAYS))


def compute_sharpe(daily_returns: pd.Series, risk_free_rate_annual: float = 0.0) -> float:
    """Annualized Sharpe ratio with optional risk-free rate."""
    if daily_returns.empty:
        return np.nan
    annual_vol = compute_annual_vol(daily_returns)
    if np.isnan(annual_vol) or annual_vol <= np.finfo(float).eps:
        return np.nan
    annual_return = float(daily_returns.mean() * TRADING_DAYS)
    excess_return = annual_return - risk_free_rate_annual
    return excess_return / annual_vol


def compute_max_drawdown(equity_curve: pd.Series) -> float:
    """Maximum peak-to-trough drawdown magnitude (positive number)."""
    if equity_curve.empty:
        return np.nan
    running_max = equity_curve.cummax()
    drawdowns = equity_curve / running_max - 1.0
    max_drawdown = drawdowns.min()
    return float(abs(max_drawdown))
