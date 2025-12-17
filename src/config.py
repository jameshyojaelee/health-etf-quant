"""Project-level configuration for tickers, dates, and data locations.

This module centralizes shared defaults so loaders, signal builders, scripts, and
notebooks can reference a single source of truth for:

- Symbols, date ranges, and other parameters (optionally loaded from YAML).
- Filesystem paths for raw and processed datasets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


def get_project_root() -> Path:
    """Return the repository root, assuming this file lives inside `src/`."""
    return Path(__file__).resolve().parent.parent


_PROJECT_ROOT = get_project_root()
DATA_RAW_DIR: Path = _PROJECT_ROOT / "data_raw"
DATA_PROCESSED_DIR: Path = _PROJECT_ROOT / "data_processed"
SETTINGS_PATH: Path = _PROJECT_ROOT / "config" / "settings.yaml"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load repo settings from YAML, returning an empty dict when missing.

    This keeps modules import-safe (e.g., on fresh clones) while enabling
    config-driven defaults when `config/settings.yaml` is present.
    """
    settings_path = Path(path) if path is not None else SETTINGS_PATH
    if not settings_path.exists():
        return {}
    data = yaml.safe_load(settings_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping at {settings_path}, got {type(data).__name__}")
    return data


SETTINGS: dict[str, Any] = load_settings()
DATA_SETTINGS: dict[str, Any] = SETTINGS.get("data", {}) if isinstance(SETTINGS.get("data", {}), dict) else {}
BACKTEST_SETTINGS: dict[str, Any] = (
    SETTINGS.get("backtest", {}) if isinstance(SETTINGS.get("backtest", {}), dict) else {}
)
MACRO_SETTINGS: dict[str, Any] = SETTINGS.get("macro", {}) if isinstance(SETTINGS.get("macro", {}), dict) else {}
REGIME_SETTINGS: dict[str, Any] = (
    SETTINGS.get("regime_strategy", {}) if isinstance(SETTINGS.get("regime_strategy", {}), dict) else {}
)
ROTATION_SETTINGS: dict[str, Any] = (
    SETTINGS.get("rotation_strategy", {}) if isinstance(SETTINGS.get("rotation_strategy", {}), dict) else {}
)


# Data defaults (can be overridden via config/settings.yaml)
TICKERS: list[str] = list(DATA_SETTINGS.get("tickers", ["XBI", "XPH", "IHF", "IHI", "XLV", "SPY"]))
START_DATE: str = str(DATA_SETTINGS.get("start_date", "2006-07-01"))
# Use None to signal "up to the most recent available date".
END_DATE: Optional[str] = DATA_SETTINGS.get("end_date", None)


# Backtest defaults
DEFAULT_TRANSACTION_COST_BPS: float = float(BACKTEST_SETTINGS.get("transaction_cost_bps", 10.0))

# Macro defaults
MACRO_SOURCE: str = str(MACRO_SETTINGS.get("source", "yahoo")).strip().lower()
MACRO_FRED_API_KEY: Optional[str] = MACRO_SETTINGS.get("fred_api_key", None)


# Strategy defaults (used primarily by scripts / notebooks; signal builders also have their own defaults)
REGIME_VIX_THRESHOLD: float = float(REGIME_SETTINGS.get("vix_threshold", 25.0))
REGIME_LOOKBACK_MONTHS_RATE: int = int(REGIME_SETTINGS.get("lookback_months_rate", 6))
REGIME_LOOKBACK_MONTHS_SPY: int = int(REGIME_SETTINGS.get("lookback_months_spy", 6))

ROTATION_MOMENTUM_LOOKBACK_MONTHS: int = int(ROTATION_SETTINGS.get("momentum_lookback_months", 6))
ROTATION_TOP_K: int = int(ROTATION_SETTINGS.get("top_k", 2))
ROTATION_TARGET_VOL_ANNUAL: float = float(ROTATION_SETTINGS.get("target_vol_annual", 0.10))


def apply_settings(settings: dict[str, Any]) -> None:
    """Apply settings dict to module-level defaults (for script-level overrides).

    This is intended for CLI usage (e.g., `--settings path/to/file.yaml`) where
    we want a single run to use alternate defaults without refactoring every
    call site to thread a config object throughout the codebase.
    """
    global SETTINGS, DATA_SETTINGS, BACKTEST_SETTINGS, MACRO_SETTINGS, REGIME_SETTINGS, ROTATION_SETTINGS
    global TICKERS, START_DATE, END_DATE
    global DEFAULT_TRANSACTION_COST_BPS
    global MACRO_SOURCE, MACRO_FRED_API_KEY
    global REGIME_VIX_THRESHOLD, REGIME_LOOKBACK_MONTHS_RATE, REGIME_LOOKBACK_MONTHS_SPY
    global ROTATION_MOMENTUM_LOOKBACK_MONTHS, ROTATION_TOP_K, ROTATION_TARGET_VOL_ANNUAL

    SETTINGS = settings
    DATA_SETTINGS = SETTINGS.get("data", {}) if isinstance(SETTINGS.get("data", {}), dict) else {}
    BACKTEST_SETTINGS = SETTINGS.get("backtest", {}) if isinstance(SETTINGS.get("backtest", {}), dict) else {}
    MACRO_SETTINGS = SETTINGS.get("macro", {}) if isinstance(SETTINGS.get("macro", {}), dict) else {}
    REGIME_SETTINGS = SETTINGS.get("regime_strategy", {}) if isinstance(SETTINGS.get("regime_strategy", {}), dict) else {}
    ROTATION_SETTINGS = (
        SETTINGS.get("rotation_strategy", {}) if isinstance(SETTINGS.get("rotation_strategy", {}), dict) else {}
    )

    TICKERS = list(DATA_SETTINGS.get("tickers", TICKERS))
    START_DATE = str(DATA_SETTINGS.get("start_date", START_DATE))
    END_DATE = DATA_SETTINGS.get("end_date", END_DATE)

    DEFAULT_TRANSACTION_COST_BPS = float(BACKTEST_SETTINGS.get("transaction_cost_bps", DEFAULT_TRANSACTION_COST_BPS))

    MACRO_SOURCE = str(MACRO_SETTINGS.get("source", MACRO_SOURCE)).strip().lower()
    MACRO_FRED_API_KEY = MACRO_SETTINGS.get("fred_api_key", MACRO_FRED_API_KEY)

    REGIME_VIX_THRESHOLD = float(REGIME_SETTINGS.get("vix_threshold", REGIME_VIX_THRESHOLD))
    REGIME_LOOKBACK_MONTHS_RATE = int(REGIME_SETTINGS.get("lookback_months_rate", REGIME_LOOKBACK_MONTHS_RATE))
    REGIME_LOOKBACK_MONTHS_SPY = int(REGIME_SETTINGS.get("lookback_months_spy", REGIME_LOOKBACK_MONTHS_SPY))

    ROTATION_MOMENTUM_LOOKBACK_MONTHS = int(
        ROTATION_SETTINGS.get("momentum_lookback_months", ROTATION_MOMENTUM_LOOKBACK_MONTHS)
    )
    ROTATION_TOP_K = int(ROTATION_SETTINGS.get("top_k", ROTATION_TOP_K))
    ROTATION_TARGET_VOL_ANNUAL = float(ROTATION_SETTINGS.get("target_vol_annual", ROTATION_TARGET_VOL_ANNUAL))
