"""Macroeconomic time series loaders.

Primary default source:
- Yahoo Finance proxies via `yfinance` (e.g. ^TNX, ^VIX).

This module supports local caching under `data_raw/` to improve offline
reproducibility and speed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

from src import config as project_config


def _normalize_series(series: pd.Series, *, name: str) -> pd.Series:
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s = s.astype(float)
    s.name = name
    return s


def _slice_to_range(series: pd.Series, *, start: Optional[str], end: Optional[str]) -> pd.Series:
    s = series
    if start:
        s = s.loc[pd.to_datetime(start) :]
    if end:
        s = s.loc[: pd.to_datetime(end)]
    return s


def _cache_path(cache_key: str) -> Path:
    project_config.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    return project_config.DATA_RAW_DIR / f"{cache_key}_raw.csv"


def _read_cached_series(path: Path, *, name: str) -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty:
        return pd.Series(dtype=float, name=name)
    series = df.iloc[:, 0]
    return _normalize_series(series, name=name)


def _write_cached_series(path: Path, series: pd.Series) -> None:
    df = series.to_frame(series.name)
    df.to_csv(path, index_label="Date")


def _load_cached_or_download(
    *,
    ticker: str,
    cache_key: str,
    start: Optional[str],
    end: Optional[str],
    force_refresh: bool,
) -> pd.Series:
    path = _cache_path(cache_key)
    if path.exists() and not force_refresh:
        cached = _read_cached_series(path, name=ticker)
        sliced = _slice_to_range(cached, start=start, end=end)
        if not sliced.empty:
            return sliced

    downloaded = _download_single(ticker, start=start, end=end)
    downloaded = _normalize_series(downloaded, name=ticker)
    if not downloaded.empty:
        _write_cached_series(path, downloaded)
    return downloaded

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


def load_tnx_10y(start: Optional[str] = None, end: Optional[str] = None, *, force_refresh: bool = False) -> pd.Series:
    """Load 10-year US Treasury yield proxy (^TNX) from Yahoo Finance.

    Caches to `data_raw/tnx_raw.csv` by default.
    """
    return _load_cached_or_download(
        ticker="^TNX",
        cache_key="tnx",
        start=start,
        end=end,
        force_refresh=force_refresh,
    )


def load_vix(start: Optional[str] = None, end: Optional[str] = None, *, force_refresh: bool = False) -> pd.Series:
    """Load VIX index (^VIX) from Yahoo Finance.

    Caches to `data_raw/vix_raw.csv` by default.
    """
    return _load_cached_or_download(
        ticker="^VIX",
        cache_key="vix",
        start=start,
        end=end,
        force_refresh=force_refresh,
    )


def load_credit_spread_proxy() -> pd.Series:
    """Placeholder for corporate minus Treasury spread (funding stress proxy)."""
    return pd.Series(dtype=float)
