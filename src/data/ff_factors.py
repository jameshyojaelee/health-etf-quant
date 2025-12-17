"""Load Fama-French factor data from local CSVs."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from src import config


def load_ff_factors_monthly(path: Path | None = None, *, include_umd: bool = False) -> pd.DataFrame:
    """Load monthly Fama-French factors (FF5 + RF, optionally UMD).

    Parameters
    ----------
    path : Path | None
        Optional path to a processed CSV. Defaults to data_processed/ff_factors_monthly.csv.
    include_umd : bool
        If True, require and return the momentum factor (UMD) as well.

    Returns
    -------
    pandas.DataFrame
        DataFrame indexed by month-end dates with factor columns as decimals.
    """
    default_path = config.DATA_PROCESSED_DIR / "ff_factors_monthly.csv"
    csv_path = Path(path) if path is not None else default_path
    if not csv_path.exists() and path is None:
        from src.data.ff_factors_download import build_ff_factors_monthly

        build_ff_factors_monthly(include_momentum=True, force_refresh=False, processed_path=csv_path)

    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    expected_cols = ["MKT_RF", "SMB", "HML", "RMW", "CMA", "RF"] + (["UMD"] if include_umd else [])
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected factor columns: {missing}")
    return df[expected_cols]
