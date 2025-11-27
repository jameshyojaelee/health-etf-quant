"""Project-level configuration for tickers, dates, and data locations.

This module centralizes shared defaults so loaders, signal builders, and notebooks
can reference a single source of truth for symbols, date ranges, and filesystem
paths.
"""

from pathlib import Path
from typing import Optional


def get_project_root() -> Path:
    """Return the repository root, assuming this file lives inside `src/`."""
    return Path(__file__).resolve().parent.parent


TICKERS: list[str] = ["XBI", "XPH", "IHF", "IHI", "XLV", "SPY"]
START_DATE: str = "2006-07-01"
# Use None to signal "up to the most recent available date".
END_DATE: Optional[str] = None

_PROJECT_ROOT = get_project_root()
DATA_RAW_DIR: Path = _PROJECT_ROOT / "data_raw"
DATA_PROCESSED_DIR: Path = _PROJECT_ROOT / "data_processed"
