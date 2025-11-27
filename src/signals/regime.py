"""Compute macro regime labels such as risk-on and risk-off."""

from __future__ import annotations

import pandas as pd


def compute_monthly_features(
    tnx_yield: pd.Series,
    spy_prices: pd.Series,
    vix: pd.Series,
) -> pd.DataFrame:
    """Build month-end macro features used for regime labeling.

    - tnx_yield: 10Y Treasury yield levels.
    - spy_prices: SPY adjusted close prices (total return proxy).
    - vix: VIX index levels.
    """
    tnx_m = tnx_yield.resample("ME").last()
    spy_m = spy_prices.resample("ME").last()
    vix_m = vix.resample("ME").mean()

    delta_rate_6m = tnx_m.diff(6)
    spy_return_6m = spy_m.pct_change(6)
    vix_mean_1m = vix_m.rolling(1).mean()

    features = pd.DataFrame(
        {
            "delta_rate_6m": delta_rate_6m,
            "spy_return_6m": spy_return_6m,
            "vix_mean_1m": vix_mean_1m,
        }
    ).dropna(how="all")

    return features


def classify_regime(
    monthly_features: pd.DataFrame,
    rate_threshold: float = 0.0,
    vix_threshold: float = 25.0,
    spy_ret_threshold: float = 0.0,
) -> pd.Series:
    """Label months as risk-on (1) or risk-off (0) based on simple thresholds.

    Defaults are starting points; they are not tuned for performance.
    """
    cond_rate = monthly_features["delta_rate_6m"] <= rate_threshold
    cond_spy = monthly_features["spy_return_6m"] >= spy_ret_threshold
    cond_vix = monthly_features["vix_mean_1m"] <= vix_threshold

    risk_on = (cond_rate & cond_spy & cond_vix).astype(int)
    risk_on.name = "regime"
    return risk_on
