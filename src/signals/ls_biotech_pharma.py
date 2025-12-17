"""Biotech vs pharma long-short signal construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas import Series, DataFrame

from src.portfolio.vol_target import estimate_rolling_vol


def build_monthly_ls_weights_simple(
    regime_labels: pd.Series,
    dates: pd.DatetimeIndex,
    long_ticker: str = "XBI",
    short_ticker: str = "XPH",
    risk_off_mode: str = "flat",
) -> pd.DataFrame:
    """Simple mapping: risk-on equals long/short spread, risk-off configurable.

    Parameters
    ----------
    risk_off_mode:
        - "flat": 0 exposure in risk-off months (default)
        - "long_pharma": go long the defensive leg (pharma) only
        - "reverse": flip the spread (short biotech, long pharma)
    """
    if risk_off_mode not in {"flat", "long_pharma", "reverse"}:
        raise ValueError("risk_off_mode must be one of {'flat','long_pharma','reverse'}.")

    tickers = [long_ticker, short_ticker]

    monthly_weights = []
    for date, label in regime_labels.items():
        if label == 1:
            monthly_weights.append(pd.Series({long_ticker: 1.0, short_ticker: -1.0}, name=date))
        else:
            if risk_off_mode == "flat":
                monthly_weights.append(pd.Series({long_ticker: 0.0, short_ticker: 0.0}, name=date))
            elif risk_off_mode == "long_pharma":
                monthly_weights.append(pd.Series({long_ticker: 0.0, short_ticker: 1.0}, name=date))
            else:  # "reverse"
                monthly_weights.append(pd.Series({long_ticker: -1.0, short_ticker: 1.0}, name=date))

    monthly_df = pd.DataFrame(monthly_weights)

    daily_weights = monthly_df.reindex(dates, method="ffill").fillna(0.0)
    daily_weights = daily_weights.reindex(columns=tickers, fill_value=0.0)
    return daily_weights


def extend_ls_weights_to_all_tickers(
    ls_weights: pd.DataFrame,
    all_tickers: list[str],
) -> pd.DataFrame:
    """Extend LS weights to full universe, filling missing tickers with zeros."""
    extended = pd.DataFrame(0.0, index=ls_weights.index, columns=all_tickers)
    for col in ["XBI", "XPH"]:
        if col in ls_weights.columns and col in extended.columns:
            extended[col] = ls_weights[col]
    return extended


def compute_spread_momentum(
    prices: pd.DataFrame,
    long_ticker: str = "XBI",
    short_ticker: str = "XPH",
    lookback_months: int = 6,
) -> pd.Series:
    """Compute 6M log-return momentum of the XBI/XPH spread at month-end."""
    monthly = prices[[long_ticker, short_ticker]].resample("ME").last()
    ratio = monthly[long_ticker] / monthly[short_ticker]
    log_spread = np.log(ratio)
    spread_mom = log_spread - log_spread.shift(lookback_months)
    spread_mom.name = "spread_momentum"
    return spread_mom


def compute_risk_balanced_ls_weights(
    current_vols: Series,
    long_ticker: str = "XBI",
    short_ticker: str = "XPH",
    target_gross_exposure: float = 1.0,
) -> dict[str, float]:
    """Inverse-vol risk-balanced weights for a two-leg spread."""
    vols = current_vols.reindex([long_ticker, short_ticker])
    if vols.isna().any() or (vols <= 0).any():
        return {long_ticker: 0.0, short_ticker: 0.0}

    inv_vol = 1 / vols
    total = inv_vol.sum()
    if total <= 0:
        return {long_ticker: 0.0, short_ticker: 0.0}

    w_long = (inv_vol[long_ticker] / total) * target_gross_exposure
    w_short = (inv_vol[short_ticker] / total) * target_gross_exposure
    return {long_ticker: float(w_long), short_ticker: -float(w_short)}


def _build_monthly_ls_weights_risk_balanced(
    regime_labels: Series,
    prices: DataFrame,
    vol_df: DataFrame,
    spread_momentum: Series,
    long_ticker: str = "XBI",
    short_ticker: str = "XPH",
    target_gross_exposure: float = 1.0,
    spread_mom_threshold: float = 0.0,
) -> DataFrame:
    """Risk-balanced, momentum-gated LS weights mapped to daily frequency.

    Requires macro risk-on AND positive spread momentum to take risk. Otherwise flat.
    """
    monthly_weights = []
    monthly_index = spread_momentum.index.intersection(regime_labels.index)

    for date in monthly_index:
        weights = {t: 0.0 for t in prices.columns}
        reg = regime_labels.loc[date]
        smom = spread_momentum.loc[date]
        if reg == 1 and pd.notna(smom) and smom > spread_mom_threshold:
            # use last available vol in the month
            if date in vol_df.index:
                current_vols = vol_df.loc[date]
            else:
                current_vols = vol_df.loc[:date].iloc[-1]
            w = compute_risk_balanced_ls_weights(
                current_vols=current_vols,
                long_ticker=long_ticker,
                short_ticker=short_ticker,
                target_gross_exposure=target_gross_exposure,
            )
            weights[long_ticker] = w.get(long_ticker, 0.0)
            weights[short_ticker] = w.get(short_ticker, 0.0)
        monthly_weights.append(pd.Series(weights, name=date))

    monthly_df = pd.DataFrame(monthly_weights)
    daily_weights = monthly_df.reindex(prices.index, method="ffill").fillna(0.0)
    daily_weights = daily_weights.reindex(columns=prices.columns, fill_value=0.0)
    return daily_weights


def build_monthly_ls_weights(
    regime_labels: Series,
    dates: pd.DatetimeIndex | None = None,
    *,
    prices: DataFrame | None = None,
    vol_df: DataFrame | None = None,
    spread_momentum: Series | None = None,
    long_ticker: str = "XBI",
    short_ticker: str = "XPH",
    target_gross_exposure: float = 1.0,
    spread_mom_threshold: float = 0.0,
    risk_off_mode: str = "flat",
    spread_mom_lookback_months: int = 6,
    vol_lookback_days: int = 60,
) -> DataFrame:
    """Build daily long/short weights for the biotech–pharma spread.

    This function is intentionally *backward compatible* with the repo's earlier
    API while supporting a more advanced sizing path:

    1) **Simple mapping** (legacy):
       - Call as `build_monthly_ls_weights(regime_labels, dates)`
       - Uses `build_monthly_ls_weights_simple` with constant +/- 1 notional
         when risk-on and configurable behavior when risk-off.

    2) **Risk-balanced + momentum-gated** (recommended for deeper research):
       - Call with `prices=...` and optionally `vol_df=...`, `spread_momentum=...`
       - Sizes legs by inverse vol and only takes risk when spread momentum is
         above `spread_mom_threshold`.
    """
    if prices is None:
        if dates is None:
            raise ValueError("Provide either `dates` (simple mode) or `prices` (risk-balanced mode).")
        return build_monthly_ls_weights_simple(
            regime_labels=regime_labels,
            dates=dates,
            long_ticker=long_ticker,
            short_ticker=short_ticker,
            risk_off_mode=risk_off_mode,
        )

    # Risk-balanced path
    if vol_df is None:
        daily_returns = prices.pct_change().fillna(0.0)
        vol_df = estimate_rolling_vol(daily_returns, lookback_days=vol_lookback_days)
    if spread_momentum is None:
        spread_momentum = compute_spread_momentum(
            prices,
            long_ticker=long_ticker,
            short_ticker=short_ticker,
            lookback_months=spread_mom_lookback_months,
        )

    return _build_monthly_ls_weights_risk_balanced(
        regime_labels=regime_labels,
        prices=prices,
        vol_df=vol_df,
        spread_momentum=spread_momentum,
        long_ticker=long_ticker,
        short_ticker=short_ticker,
        target_gross_exposure=target_gross_exposure,
        spread_mom_threshold=spread_mom_threshold,
    )
