"""FRED (St. Louis Fed) time series loader with lightweight caching.

This module is optional: the project can run entirely on Yahoo Finance proxies
for macro data. When enabled, it fetches series via the FRED API and caches raw
CSV outputs under `data_raw/`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from src import config as project_config

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"


def _cache_path(series_id: str) -> Path:
    project_config.DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = series_id.lower().replace("/", "_")
    return project_config.DATA_RAW_DIR / f"fred_{safe_id}_raw.csv"


def _slice_to_range(series: pd.Series, *, start: Optional[str], end: Optional[str]) -> pd.Series:
    s = series
    if start:
        s = s.loc[pd.to_datetime(start) :]
    if end:
        s = s.loc[: pd.to_datetime(end)]
    return s


def _read_cached_series(path: Path, *, name: str) -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty:
        return pd.Series(dtype=float, name=name)
    s = df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    s = s.astype(float)
    s.name = name
    return s


def _write_cached_series(path: Path, series: pd.Series) -> None:
    series.to_frame(series.name).to_csv(path, index_label="Date")


def fetch_fred_series(
    series_id: str,
    *,
    api_key: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    timeout_seconds: float = 30.0,
) -> pd.Series:
    """Fetch a FRED series from the API as a pandas Series."""
    params: dict[str, str] = {
        "series_id": series_id,
        "file_type": "json",
    }
    if api_key:
        params["api_key"] = api_key
    if start:
        params["observation_start"] = start
    if end:
        params["observation_end"] = end

    url = f"{FRED_OBSERVATIONS_URL}?{urlencode(params)}"
    with urlopen(url, timeout=timeout_seconds) as resp:  # noqa: S310 (user-controlled URL is expected here)
        payload = json.loads(resp.read().decode("utf-8"))

    observations = payload.get("observations", [])
    if not observations:
        return pd.Series(dtype=float, name=series_id)

    df = pd.DataFrame(observations)[["date", "value"]]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.sort_values("date")
    series = pd.Series(df["value"].values, index=df["date"].values, name=series_id)
    series.index = pd.to_datetime(series.index)
    return series


def load_fred_series(
    series_id: str,
    *,
    api_key: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> pd.Series:
    """Load a FRED series from cache or download and cache it."""
    path = _cache_path(series_id)
    if path.exists() and not force_refresh:
        cached = _read_cached_series(path, name=series_id)
        sliced = _slice_to_range(cached, start=start, end=end)
        if not sliced.empty:
            return sliced

    downloaded = fetch_fred_series(series_id, api_key=api_key, start=start, end=end)
    downloaded.index = pd.to_datetime(downloaded.index)
    downloaded = downloaded.sort_index()
    downloaded.name = series_id
    if not downloaded.empty:
        _write_cached_series(path, downloaded)
    return downloaded


def load_10y_yield(
    *,
    api_key: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> pd.Series:
    """10-Year Treasury Constant Maturity Rate (DGS10) from FRED."""
    return load_fred_series("DGS10", api_key=api_key, start=start, end=end, force_refresh=force_refresh)


def load_vix_level(
    *,
    api_key: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> pd.Series:
    """CBOE Volatility Index (VIXCLS) from FRED."""
    return load_fred_series("VIXCLS", api_key=api_key, start=start, end=end, force_refresh=force_refresh)


def load_credit_spread_baa_minus_10y(
    *,
    api_key: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> pd.Series:
    """Credit spread proxy: Moody's BAA yield minus 10Y Treasury yield (BAA - DGS10)."""
    baa = load_fred_series("BAA", api_key=api_key, start=start, end=end, force_refresh=force_refresh)
    dgs10 = load_10y_yield(api_key=api_key, start=start, end=end, force_refresh=force_refresh)
    df = pd.concat([baa.rename("BAA"), dgs10.rename("DGS10")], axis=1).sort_index().ffill()
    spread = df["BAA"] - df["DGS10"]
    spread.name = "BAA_MINUS_10Y"
    return spread

