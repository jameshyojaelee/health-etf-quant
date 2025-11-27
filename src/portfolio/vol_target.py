"""Volatility targeting utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def estimate_rolling_vol(
    daily_returns: pd.DataFrame,
    lookback_days: int = 60,
) -> pd.DataFrame:
    """Estimate annualized rolling volatility for each asset."""
    rolling_std = daily_returns.rolling(lookback_days, min_periods=1).std(ddof=0)
    annualized_vol = rolling_std * np.sqrt(TRADING_DAYS)
    return annualized_vol


def build_vol_target_weights(
    selected_tickers: list[str],
    current_date: pd.Timestamp,
    vol_df: pd.DataFrame,
    target_vol_annual: float,
) -> dict[str, float]:
    """Construct inverse-vol weights for selected tickers on a given date.

    Returns zeros if vols are missing/zero. Scales to sum to 1.0 or less.
    """
    weights: dict[str, float] = {t: 0.0 for t in selected_tickers}
    if current_date not in vol_df.index:
        return weights

    vols = vol_df.loc[current_date, selected_tickers].replace(0.0, np.nan).dropna()
    if vols.empty:
        return weights

    inv_vol = 1 / vols
    if inv_vol.sum() <= 0 or np.isinf(inv_vol).any():
        return weights

    raw_weights = inv_vol / inv_vol.sum()
    avg_vol = float((raw_weights * vols).sum())
    scale = 1.0
    if avg_vol > 0 and target_vol_annual > 0:
        scale = min(1.0, target_vol_annual / avg_vol)
    scaled_weights = raw_weights * scale
    for t in selected_tickers:
        weights[t] = float(scaled_weights.get(t, 0.0))
    return weights


def scale_weights_to_target_vol(
    risk_weights: dict[str, float],
    current_vols: pd.Series,
    target_vol_annual: float,
    max_gross_leverage: float = 1.5,
) -> dict[str, float]:
    """Scale risk weights to hit a target portfolio vol with a leverage cap.

    Assumes zero correlations: portfolio_vol ≈ sqrt(sum(w_i^2 * vol_i^2)).
    """
    if current_vols.empty or not risk_weights:
        return {k: 0.0 for k in risk_weights}

    w = pd.Series(risk_weights, dtype=float).reindex(current_vols.index).fillna(0.0)
    vols = current_vols.reindex(w.index).astype(float)
    if vols.isna().all() or w.abs().sum() == 0:
        return {k: 0.0 for k in risk_weights}

    unscaled_var = ((w ** 2) * (vols ** 2)).sum()
    if unscaled_var <= 0 or pd.isna(unscaled_var):
        return {k: 0.0 for k in risk_weights}

    unscaled_vol = float(unscaled_var ** 0.5)
    scale = target_vol_annual / unscaled_vol if target_vol_annual and unscaled_vol else 0.0
    scaled_w = w * scale

    gross = scaled_w.abs().sum()
    if gross > max_gross_leverage and gross > 0:
        scaled_w *= max_gross_leverage / gross

    return {k: float(v) for k, v in scaled_w.items()}
