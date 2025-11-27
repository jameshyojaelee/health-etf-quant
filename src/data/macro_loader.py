"""Placeholders for macroeconomic time series loaders."""

from __future__ import annotations

import pandas as pd


def load_tnx_10y() -> pd.Series:
    """Placeholder for 10-year US Treasury yield (TNX) series (funding conditions)."""
    return pd.Series(dtype=float)


def load_vix() -> pd.Series:
    """Placeholder for VIX equity volatility index (risk sentiment)."""
    return pd.Series(dtype=float)


def load_credit_spread_proxy() -> pd.Series:
    """Placeholder for corporate minus Treasury spread (funding stress proxy)."""
    return pd.Series(dtype=float)
