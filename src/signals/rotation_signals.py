"""Signals for healthcare rotation strategies."""

from __future__ import annotations

import pandas as pd

from src.portfolio.vol_target import build_vol_target_weights, estimate_rolling_vol
from src.signals.momentum import compute_momentum_signal


def build_monthly_rotation_weights(
    prices: pd.DataFrame,
    lookback_months: int = 6,
    top_k: int = 2,
    target_vol_annual: float = 0.10,
) -> pd.DataFrame:
    """Construct daily weights for a momentum-driven, vol-targeted rotation strategy."""
    monthly_prices = prices.resample("ME").last()
    momentum_scores = compute_momentum_signal(monthly_prices, lookback_months=lookback_months)

    daily_returns = prices.pct_change().fillna(0.0)
    vol_df = estimate_rolling_vol(daily_returns)

    monthly_weights = []
    for date, row in momentum_scores.iterrows():
        weights = {ticker: 0.0 for ticker in prices.columns}
        scores = row.dropna()
        if scores.empty or scores.max() <= 0:
            monthly_weights.append(pd.Series(weights, name=date))
            continue

        winners = scores.nlargest(min(top_k, len(scores))).index.tolist()
        vol_weights = build_vol_target_weights(
            selected_tickers=winners,
            current_date=date,
            vol_df=vol_df,
            target_vol_annual=target_vol_annual,
        )
        for t in winners:
            weights[t] = vol_weights.get(t, 0.0)
        monthly_weights.append(pd.Series(weights, name=date))

    monthly_df = pd.DataFrame(monthly_weights)
    daily_weights = monthly_df.reindex(prices.index, method="ffill").fillna(0.0)
    daily_weights = daily_weights.reindex(columns=prices.columns, fill_value=0.0)
    return daily_weights
