"""Parameter sweep utilities for robustness analysis."""

from __future__ import annotations

import itertools
from typing import List

import pandas as pd

from src.analysis.metrics import (
    compute_annual_vol,
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe,
)
from src.backtest.engine import run_backtest
from src.signals.ls_biotech_pharma import build_monthly_ls_weights
from src.signals.regime import classify_regime, compute_monthly_features
from src.signals.rotation_signals import build_monthly_rotation_weights


def sweep_regime_parameters(
    prices: pd.DataFrame,
    tnx_yield: pd.Series,
    spy_prices: pd.Series,
    vix: pd.Series,
    rate_thresholds: List[float],
    vix_thresholds: List[float],
    spy_ret_thresholds: List[float],
    transaction_cost_bps: float = 10.0,
) -> pd.DataFrame:
    """Grid-search simple regime thresholds and summarize performance."""
    results = []
    for rate_th, vix_th, spy_th in itertools.product(
        rate_thresholds, vix_thresholds, spy_ret_thresholds
    ):
        features = compute_monthly_features(tnx_yield, spy_prices, vix)
        regimes = classify_regime(
            features,
            rate_threshold=rate_th,
            vix_threshold=vix_th,
            spy_ret_threshold=spy_th,
        )
        ls_weights = build_monthly_ls_weights(regimes, prices.index)
        bt = run_backtest(prices[["XBI", "XPH"]], ls_weights, transaction_cost_bps=transaction_cost_bps)
        cagr = compute_cagr(bt.daily_returns)
        vol = compute_annual_vol(bt.daily_returns)
        sharpe = compute_sharpe(bt.daily_returns)
        mdd = compute_max_drawdown(bt.equity_curve)
        results.append(
            {
                "rate_threshold": rate_th,
                "vix_threshold": vix_th,
                "spy_ret_threshold": spy_th,
                "cagr": cagr,
                "vol": vol,
                "sharpe": sharpe,
                "max_drawdown": mdd,
            }
        )
    return pd.DataFrame(results)


def sweep_momentum_parameters(
    prices: pd.DataFrame,
    lookbacks: List[int],
    top_ks: List[int],
    target_vols: List[float],
    transaction_cost_bps: float = 10.0,
) -> pd.DataFrame:
    """Grid-search momentum lookback, top-k selection, and vol targets."""
    results = []
    for lb, k, tv in itertools.product(lookbacks, top_ks, target_vols):
        weights = build_monthly_rotation_weights(
            prices,
            lookback_months=lb,
            top_k=k,
            target_vol_annual=tv,
        )
        bt = run_backtest(prices, weights, transaction_cost_bps=transaction_cost_bps)
        cagr = compute_cagr(bt.daily_returns)
        vol = compute_annual_vol(bt.daily_returns)
        sharpe = compute_sharpe(bt.daily_returns)
        mdd = compute_max_drawdown(bt.equity_curve)
        results.append(
            {
                "lookback": lb,
                "top_k": k,
                "target_vol": tv,
                "cagr": cagr,
                "vol": vol,
                "sharpe": sharpe,
                "max_drawdown": mdd,
            }
        )
    return pd.DataFrame(results)
