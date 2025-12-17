"""Signals for healthcare rotation strategies."""

from __future__ import annotations

import pandas as pd

from src.portfolio.vol_target import (
    build_vol_target_weights,
    estimate_rolling_vol,
    scale_weights_to_target_vol,
)
from src.signals.momentum import (
    compute_12m_1m_momentum,
    compute_momentum_signal,
    compute_ts_momentum_flag,
)


def build_monthly_rotation_weights(
    prices: pd.DataFrame,
    lookback_months: int = 6,
    top_k: int = 2,
    target_vol_annual: float = 0.10,
    use_12m1m: bool = True,
    use_ts_mom_gating: bool = True,
    use_xlv_trend_filter: bool = True,
    xlv_ticker: str = "XLV",
    ts_lookback_months: int = 12,
    max_gross_leverage: float = 1.5,
    defensive_ticker: str | None = None,
    defensive_on_negative_momentum: bool = True,
) -> pd.DataFrame:
    """Construct daily weights for a momentum-driven, vol-targeted rotation strategy.

    Features:
    - Cross-sectional momentum (default 12–1, otherwise lookback momentum).
    - Time-series momentum gating per asset (only long if own lookback return > 0).
    - XLV trend filter: move to cash when XLV 12m return <= 0.
    - Vol-targeted sizing with optional leverage cap.
    """
    hc_tickers = [t for t in ["XBI", "XPH", "IHF", "IHI", "XLV"] if t in prices.columns]
    monthly_prices = prices.resample("ME").last()

    if use_12m1m:
        momentum_scores = compute_12m_1m_momentum(monthly_prices[hc_tickers])
    else:
        momentum_scores = compute_momentum_signal(monthly_prices[hc_tickers], lookback_months=lookback_months)

    ts_flags = (
        compute_ts_momentum_flag(monthly_prices[hc_tickers], lookback_months=ts_lookback_months)
        if use_ts_mom_gating
        else None
    )

    xlv_trend = None
    if use_xlv_trend_filter and xlv_ticker in monthly_prices.columns:
        xlv_trend = monthly_prices[xlv_ticker] / monthly_prices[xlv_ticker].shift(12) - 1.0

    daily_returns = prices.pct_change().fillna(0.0)
    vol_df = estimate_rolling_vol(daily_returns)

    monthly_weights = []
    for date, row in momentum_scores.iterrows():
        weights = {ticker: 0.0 for ticker in prices.columns}

        # Risk-off if XLV trend is negative
        if xlv_trend is not None and pd.notna(xlv_trend.loc[date]) and xlv_trend.loc[date] <= 0:
            monthly_weights.append(pd.Series(weights, name=date))
            continue

        scores = row.dropna()
        if scores.empty:
            monthly_weights.append(pd.Series(weights, name=date))
            continue

        if scores.max() <= 0:
            if (
                defensive_on_negative_momentum
                and defensive_ticker is not None
                and defensive_ticker in prices.columns
            ):
                weights[defensive_ticker] = 1.0
            monthly_weights.append(pd.Series(weights, name=date))
            continue

        eligible_scores = scores.copy()
        if ts_flags is not None:
            flags = ts_flags.loc[date].reindex(eligible_scores.index)
            eligible_scores = eligible_scores[flags == 1]

        if eligible_scores.empty or eligible_scores.max() <= 0:
            monthly_weights.append(pd.Series(weights, name=date))
            continue

        winners = eligible_scores.nlargest(min(top_k, len(eligible_scores))).index.tolist()
        if date in vol_df.index:
            current_vols = vol_df.loc[date, winners].replace(0.0, pd.NA).dropna()
        else:
            current_vols = vol_df.loc[:date, winners].iloc[-1].replace(0.0, pd.NA).dropna()
        if current_vols.empty:
            monthly_weights.append(pd.Series(weights, name=date))
            continue

        inv_vol = 1 / current_vols
        risk_w = (inv_vol / inv_vol.sum()).to_dict()
        scaled_w = scale_weights_to_target_vol(
            risk_weights=risk_w,
            current_vols=current_vols,
            target_vol_annual=target_vol_annual,
            max_gross_leverage=max_gross_leverage,
        )
        for t in winners:
            weights[t] = scaled_w.get(t, 0.0)
        monthly_weights.append(pd.Series(weights, name=date))

    monthly_df = pd.DataFrame(monthly_weights)
    daily_weights = monthly_df.reindex(prices.index, method="ffill").fillna(0.0)
    daily_weights = daily_weights.reindex(columns=prices.columns, fill_value=0.0)

    gross = daily_weights.abs().sum(axis=1)
    over = gross > max_gross_leverage
    if over.any():
        scale = (max_gross_leverage / gross).where(over, 1.0)
        daily_weights = daily_weights.mul(scale, axis=0)

    return daily_weights
