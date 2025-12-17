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


def compute_sortino(
    daily_returns: pd.Series,
    risk_free_rate_annual: float = 0.0,
    target_return_annual: float = 0.0,
) -> float:
    """Annualized Sortino ratio using downside deviation.

    Notes
    -----
    - Numerator uses annualized *excess* return over the risk-free rate.
    - Downside deviation uses returns below `target_return_annual` (default 0).
    """
    if daily_returns.empty:
        return np.nan

    daily_rf = risk_free_rate_annual / TRADING_DAYS
    daily_target = target_return_annual / TRADING_DAYS

    excess = daily_returns - daily_rf
    downside = (daily_returns - daily_target).clip(upper=0.0)
    downside_vol = float(downside.std(ddof=0) * np.sqrt(TRADING_DAYS))
    if np.isnan(downside_vol) or downside_vol <= np.finfo(float).eps:
        return np.nan

    annual_excess = float(excess.mean() * TRADING_DAYS)
    return annual_excess / downside_vol


def compute_calmar(daily_returns: pd.Series) -> float:
    """Calmar ratio: CAGR / max drawdown (from equity curve)."""
    if daily_returns.empty:
        return np.nan
    equity_curve = (1 + daily_returns.fillna(0.0)).cumprod()
    mdd = compute_max_drawdown(equity_curve)
    if np.isnan(mdd) or mdd <= np.finfo(float).eps:
        return np.nan
    return compute_cagr(daily_returns) / mdd


def _resample_total_return(daily_returns: pd.Series, freq: str = "ME") -> pd.Series:
    """Convert daily returns to total returns at a lower frequency."""
    return daily_returns.resample(freq).apply(lambda r: (1 + r).prod() - 1)


def compute_up_capture(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    freq: str = "ME",
) -> float:
    """Up-capture ratio vs benchmark at `freq` (default month-end).

    Defined as mean(strategy) / mean(benchmark) during periods where benchmark > 0.
    """
    s = _resample_total_return(strategy_returns, freq=freq)
    b = _resample_total_return(benchmark_returns, freq=freq)
    aligned = pd.concat([s, b], axis=1, join="inner").dropna()
    if aligned.shape[0] < 2:
        return np.nan
    up = aligned[aligned.iloc[:, 1] > 0]
    if up.empty:
        return np.nan
    denom = float(up.iloc[:, 1].mean())
    if abs(denom) <= np.finfo(float).eps:
        return np.nan
    return float(up.iloc[:, 0].mean() / denom)


def compute_down_capture(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    freq: str = "ME",
) -> float:
    """Down-capture ratio vs benchmark at `freq` (default month-end).

    Defined as mean(strategy) / mean(benchmark) during periods where benchmark < 0.
    Since both means are typically negative, values:
    - < 1.0 indicate smaller average losses than benchmark
    - > 1.0 indicate larger average losses than benchmark
    """
    s = _resample_total_return(strategy_returns, freq=freq)
    b = _resample_total_return(benchmark_returns, freq=freq)
    aligned = pd.concat([s, b], axis=1, join="inner").dropna()
    if aligned.shape[0] < 2:
        return np.nan
    down = aligned[aligned.iloc[:, 1] < 0]
    if down.empty:
        return np.nan
    denom = float(down.iloc[:, 1].mean())
    if abs(denom) <= np.finfo(float).eps:
        return np.nan
    return float(down.iloc[:, 0].mean() / denom)


def compute_skew(daily_returns: pd.Series) -> float:
    """Sample skewness of returns."""
    if daily_returns.empty:
        return np.nan
    return float(pd.Series(daily_returns).dropna().skew())


def compute_kurtosis(daily_returns: pd.Series) -> float:
    """Sample excess kurtosis of returns (pandas convention)."""
    if daily_returns.empty:
        return np.nan
    return float(pd.Series(daily_returns).dropna().kurt())


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
