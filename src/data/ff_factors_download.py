"""Download and parse Fama-French factor data from the Ken French library.

This module provides a small, dependency-light way to:
- download FF5 monthly and Momentum (UMD) monthly factor datasets
- parse the "monthly" section into a clean DataFrame
- cache raw zip files under `data_raw/`
- write processed CSVs under `data_processed/`
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen

import pandas as pd

from src import config as project_config

FF5_MONTHLY_ZIP_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_5_Factors_2x3_CSV.zip"
)
MOM_MONTHLY_ZIP_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Momentum_Factor_CSV.zip"
)


def _download_file(url: str, dest: Path, *, timeout_seconds: float = 60.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=timeout_seconds) as resp:  # noqa: S310 (expected network fetch)
        dest.write_bytes(resp.read())


def _read_first_csv_from_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No .csv file found inside zip: {zip_path}")
        # Ken French zips typically contain exactly one CSV.
        with zf.open(csv_names[0]) as f:
            raw = f.read()
    # The files often include non-utf8 characters; latin-1 is safe and deterministic.
    return raw.decode("latin-1")


def _parse_monthly_section(
    csv_text: str,
    *,
    column_renames: dict[str, str],
    keep_cols: list[str],
) -> pd.DataFrame:
    """Parse the monthly section of a Ken French CSV into decimals."""
    reader = csv.reader(io.StringIO(csv_text))

    header: Optional[list[str]] = None
    rows: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []

    date_re = re.compile(r"^\d{6}$")

    for row in reader:
        if not row:
            continue
        first = row[0].strip().strip('"')

        if header is None:
            # Find the header line (e.g., ",Mkt-RF,SMB,..." or "Date,Mkt-RF,...").
            cells = [c.strip().strip('"') for c in row]
            if any(c in keep_cols for c in cells):
                if cells and cells[0] == "":
                    cells[0] = "Date"
                header = cells
            continue

        if not date_re.match(first):
            # End of the monthly block.
            break

        # Some rows can be shorter; pad defensively.
        row = row + [""] * (len(header) - len(row))
        record_raw = dict(zip(header, row))

        dt = pd.to_datetime(first, format="%Y%m") + pd.offsets.MonthEnd(0)
        index.append(dt)

        record: dict[str, float] = {}
        for raw_col in keep_cols:
            val = record_raw.get(raw_col, "")
            num = pd.to_numeric(str(val).strip(), errors="coerce")
            if pd.notna(num) and float(num) <= -99.0:
                num = pd.NA
            record[column_renames.get(raw_col, raw_col)] = float(num) / 100.0 if pd.notna(num) else float("nan")
        rows.append(record)

    if not rows:
        raise ValueError("Failed to parse any monthly rows from Ken French dataset.")

    df = pd.DataFrame(rows, index=pd.DatetimeIndex(index, name="Date"))
    df = df.sort_index()
    return df


def build_ff_factors_monthly(
    *,
    include_momentum: bool = True,
    force_refresh: bool = False,
    raw_dir: Path | None = None,
    processed_path: Path | None = None,
) -> pd.DataFrame:
    """Download + parse FF5 monthly (and optionally UMD) and write processed CSV."""
    raw_dir = raw_dir or project_config.DATA_RAW_DIR
    processed_path = processed_path or (project_config.DATA_PROCESSED_DIR / "ff_factors_monthly.csv")

    raw_dir.mkdir(parents=True, exist_ok=True)
    project_config.DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    ff5_zip = raw_dir / "ff5_factors_monthly.zip"
    if force_refresh or not ff5_zip.exists():
        _download_file(FF5_MONTHLY_ZIP_URL, ff5_zip)

    ff5_text = _read_first_csv_from_zip(ff5_zip)
    ff5_df = _parse_monthly_section(
        ff5_text,
        column_renames={"Mkt-RF": "MKT_RF"},
        keep_cols=["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"],
    )

    out = ff5_df.copy()

    if include_momentum:
        mom_zip = raw_dir / "ff_momentum_monthly.zip"
        if force_refresh or not mom_zip.exists():
            _download_file(MOM_MONTHLY_ZIP_URL, mom_zip)
        mom_text = _read_first_csv_from_zip(mom_zip)
        mom_df = _parse_monthly_section(
            mom_text,
            column_renames={"Mom": "UMD"},
            keep_cols=["Mom"],
        )
        out = out.join(mom_df, how="left")

    out.to_csv(processed_path, index_label="Date")
    return out
