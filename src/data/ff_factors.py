"""Load Fama-French factor data from local CSVs."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from src import config


def load_ff_factors_monthly(path: Path | None = None) -> pd.DataFrame:
    """Load monthly Fama-French factors (MKT-RF, SMB, HML, RMW, CMA, RF).

    Parameters
    ----------
    path : Path | None
        Optional path to a processed CSV. Defaults to data_processed/ff_factors_monthly.csv.

    Returns
    -------
    pandas.DataFrame
        DataFrame indexed by month-end dates with factor columns as decimals.
    """
    default_path = config.DATA_PROCESSED_DIR / "ff_factors_monthly.csv"
    csv_path = Path(path) if path is not None else default_path
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index)
    expected_cols = ["MKT_RF", "SMB", "HML", "RMW", "CMA", "RF"]
    missing = [c for c in expected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected factor columns: {missing}")
    return df[expected_cols]
