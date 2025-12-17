"""Compute macro regime labels such as risk-on and risk-off."""

from __future__ import annotations

import pandas as pd


def compute_monthly_features(
    tnx_yield: pd.Series,
    spy_prices: pd.Series,
    vix: pd.Series,
    lookback_months_rate: int = 6,
    lookback_months_spy: int = 6,
    vix_window_months: int = 1,
) -> pd.DataFrame:
    """Build month-end macro features used for regime labeling.

    - tnx_yield: 10Y Treasury yield levels.
    - spy_prices: SPY adjusted close prices (total return proxy).
    - vix: VIX index levels.
    """
    tnx_m = tnx_yield.resample("ME").last()
    spy_m = spy_prices.resample("ME").last()
    vix_m = vix.resample("ME").mean()

    if lookback_months_rate <= 0 or lookback_months_spy <= 0 or vix_window_months <= 0:
        raise ValueError("Lookback windows must be positive integers.")

    delta_rate = tnx_m.diff(lookback_months_rate)
    spy_return = spy_m.pct_change(lookback_months_spy)
    vix_mean = vix_m.rolling(vix_window_months).mean()

    features = pd.DataFrame(
        {
            f"delta_rate_{lookback_months_rate}m": delta_rate,
            f"spy_return_{lookback_months_spy}m": spy_return,
            f"vix_mean_{vix_window_months}m": vix_mean,
        }
    ).dropna(how="all")

    return features


def _infer_feature_col(
    monthly_features: pd.DataFrame,
    *,
    explicit: str | None,
    prefix: str,
    fallback: str,
) -> str:
    if explicit is not None:
        if explicit not in monthly_features.columns:
            raise KeyError(f"Feature column '{explicit}' not found in monthly_features.")
        return explicit
    matches = [c for c in monthly_features.columns if c.startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if fallback in monthly_features.columns:
        return fallback
    if matches:
        # If multiple exist, choose the first for determinism.
        return sorted(matches)[0]
    raise KeyError(f"Could not infer feature column with prefix '{prefix}'.")


def classify_regime(
    monthly_features: pd.DataFrame,
    rate_threshold: float = 0.0,
    vix_threshold: float = 25.0,
    spy_ret_threshold: float = 0.0,
    rate_feature_col: str | None = None,
    spy_feature_col: str | None = None,
    vix_feature_col: str | None = None,
) -> pd.Series:
    """Label months as risk-on (1) or risk-off (0) based on simple thresholds.

    Defaults are starting points; they are not tuned for performance.
    """
    rate_col = _infer_feature_col(
        monthly_features, explicit=rate_feature_col, prefix="delta_rate_", fallback="delta_rate_6m"
    )
    spy_col = _infer_feature_col(
        monthly_features, explicit=spy_feature_col, prefix="spy_return_", fallback="spy_return_6m"
    )
    vix_col = _infer_feature_col(
        monthly_features, explicit=vix_feature_col, prefix="vix_mean_", fallback="vix_mean_1m"
    )

    cond_rate = monthly_features[rate_col] <= rate_threshold
    cond_spy = monthly_features[spy_col] >= spy_ret_threshold
    cond_vix = monthly_features[vix_col] <= vix_threshold

    risk_on = (cond_rate & cond_spy & cond_vix).astype(int)
    risk_on.name = "regime"
    return risk_on
