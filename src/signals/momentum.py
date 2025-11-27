"""Generic momentum signal computation utilities."""

from __future__ import annotations

import pandas as pd


def compute_monthly_total_return(prices: pd.DataFrame) -> pd.DataFrame:
    """Resample daily adjusted prices to month-end and compute simple returns."""
    monthly_prices = prices.resample("M").last()
    monthly_returns = monthly_prices.pct_change()
    return monthly_returns


def compute_momentum_signal(
    monthly_prices: pd.DataFrame,
    lookback_months: int = 6,
) -> pd.DataFrame:
    """Compute lookback momentum based on month-end prices.

    Momentum at month t uses prices up to month t and is shifted by one period
    to avoid look-ahead when used for trading in the following month.
    """
    raw_mom = monthly_prices / monthly_prices.shift(lookback_months) - 1.0
    momentum = raw_mom.shift(1)
    return momentum
