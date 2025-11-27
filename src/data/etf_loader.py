"""ETF price loading, caching, and light cleaning utilities."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from src import config


def _select_price_columns(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Extract adjusted close (preferred) or close prices for each ticker."""
    if raw.empty:
        raise ValueError("No data returned from download; raw DataFrame is empty.")

    # Handle yfinance multi-index columns (ticker, field) vs single-index columns.
    prices: pd.DataFrame
    if raw.columns.nlevels == 2:
        field_candidates = ("Adj Close", "Close")
        for field in field_candidates:
            if field in raw.columns.get_level_values(1):
                prices = raw.xs(field, level=1, axis=1)
                break
        else:
            raise KeyError("Expected 'Adj Close' or 'Close' in downloaded data.")
    else:
        if "Adj Close" in raw.columns:
            prices = raw[["Adj Close"]].copy()
            prices.columns = tickers if len(tickers) == 1 else raw.columns
        elif "Close" in raw.columns:
            prices = raw[["Close"]].copy()
            prices.columns = tickers if len(tickers) == 1 else raw.columns
        else:
            # Assume columns already correspond to tickers (e.g., auto_adjust=True).
            prices = raw.copy()

    if isinstance(prices, pd.Series):
        prices = prices.to_frame()

    prices = prices.reindex(columns=tickers)
    prices.index = pd.to_datetime(prices.index)
    prices.sort_index(inplace=True)
    return prices


def download_etf_prices(
    tickers: list[str],
    start: str,
    end: Optional[str] = None,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """Download adjusted close prices for ETFs using yfinance.

    Parameters
    ----------
    tickers : list[str]
        List of ETF tickers to download.
    start : str
        Start date (YYYY-MM-DD).
    end : str | None, optional
        End date; None means up to the latest available.
    auto_adjust : bool, optional
        Whether to request adjusted prices from yfinance directly.

    Returns
    -------
    pandas.DataFrame
        Adjusted close price DataFrame indexed by date with columns in the
        same order as the input tickers.
    """
    raw = yf.download(
        tickers=" ".join(tickers),
        start=start,
        end=end,
        auto_adjust=auto_adjust,
        group_by="ticker",
        progress=False,
    )
    prices = _select_price_columns(raw, tickers)
    return prices


def cache_etf_prices() -> pd.DataFrame:
    """Download (if needed) and cache raw ETF prices to CSV in data_raw."""
    raw_path: Path = config.DATA_RAW_DIR / "etf_prices_raw.csv"
    config.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)

    if raw_path.exists():
        raw_df = pd.read_csv(raw_path, index_col=0, parse_dates=True)
        raw_df.index = pd.to_datetime(raw_df.index)
        raw_df.sort_index(inplace=True)
        return raw_df

    downloaded = download_etf_prices(
        tickers=config.TICKERS,
        start=config.START_DATE,
        end=config.END_DATE,
        auto_adjust=True,
    )
    downloaded.to_csv(raw_path, index_label="Date")
    return downloaded


def load_clean_prices() -> pd.DataFrame:
    """Load cached ETF prices, lightly clean them, and write processed CSV.

    Cleaning steps:
    - Ensure DatetimeIndex sorted ascending.
    - Reindex columns to config.TICKERS, forward-filling small gaps created by
      differing trading calendars.
    - Warn if missing values remain after forward-fill (e.g., leading gaps).
    """
    raw_df = cache_etf_prices()

    df = raw_df.copy()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # Align columns and forward-fill minor gaps (e.g., due to calendar differences).
    df = df.reindex(columns=config.TICKERS).astype(np.float64)
    df = df.ffill()

    missing_counts = df.isna().sum()
    still_missing = {t: int(cnt) for t, cnt in missing_counts.items() if cnt > 0}
    if still_missing:
        warnings.warn(
            f"Missing values remain after cleaning: {still_missing}",
            RuntimeWarning,
        )

    config.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean_path = config.DATA_PROCESSED_DIR / "etf_prices_clean.csv"
    df.to_csv(clean_path, index_label="Date")
    return df
