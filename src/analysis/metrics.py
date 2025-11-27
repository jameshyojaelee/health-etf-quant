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


def compute_information_ratio(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    """Information ratio based on active returns vs benchmark."""
    aligned = pd.concat([strategy_returns, benchmark_returns], axis=1, join="inner").dropna()
    if aligned.shape[0] < 2:
        return np.nan
    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    if active.std(ddof=0) == 0:
        return np.nan
    return float(active.mean() / active.std(ddof=0))


def compute_correlation(series_a: pd.Series, series_b: pd.Series) -> float:
    """Pearson correlation between two aligned series."""
    aligned = pd.concat([series_a, series_b], axis=1, join="inner").dropna()
    if aligned.shape[0] < 2:
        return np.nan
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def compute_blended_returns(
    base_returns: pd.Series,
    overlay_returns: pd.Series,
    overlay_weight: float = 0.1,
) -> pd.Series:
    """Blend base and overlay returns (e.g., 90% XLV + 10% LS)."""
    aligned = pd.concat([base_returns, overlay_returns], axis=1, join="inner").dropna()
    if aligned.empty:
        return pd.Series(dtype=float)
    base = aligned.iloc[:, 0]
    overlay = aligned.iloc[:, 1]
    return (1 - overlay_weight) * base + overlay_weight * overlay
