"""Macroeconomic time series loaders using Yahoo Finance proxies."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf


def _download_single(ticker: str, start: Optional[str], end: Optional[str]) -> pd.Series:
    """Helper to download a single ticker as a Series of adjusted closes."""
    data = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if data.empty:
        return pd.Series(dtype=float, name=ticker)
    if data.columns.nlevels == 2:
        series = data["Adj Close"]
    else:
        series = data["Adj Close"] if "Adj Close" in data.columns else data.iloc[:, 0]
    if isinstance(series, pd.DataFrame):
        series = series.squeeze("columns")
    series.name = ticker
    return series


def load_tnx_10y(start: Optional[str] = None, end: Optional[str] = None) -> pd.Series:
    """Load 10-year US Treasury yield proxy (^TNX) from Yahoo Finance."""
    return _download_single("^TNX", start=start, end=end)


def load_vix(start: Optional[str] = None, end: Optional[str] = None) -> pd.Series:
    """Load VIX index (^VIX) from Yahoo Finance."""
    return _download_single("^VIX", start=start, end=end)


def load_credit_spread_proxy() -> pd.Series:
    """Placeholder for corporate minus Treasury spread (funding stress proxy)."""
    return pd.Series(dtype=float)
