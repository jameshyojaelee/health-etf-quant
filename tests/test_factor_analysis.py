"""Tests for factor alignment and regression inputs."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.analysis.factor_analysis import align_strategy_and_factors  # noqa: E402


def test_align_strategy_and_factors_scales_percent_rf_and_includes_umd():
    daily_idx = pd.date_range("2020-01-01", "2020-02-28", freq="B")
    daily_returns = pd.Series(0.0, index=daily_idx)

    month_ends = pd.to_datetime(["2020-01-31", "2020-02-29"])
    ff = pd.DataFrame(
        {
            # Use percent-like magnitudes so the RF heuristic triggers (max > 0.5).
            "MKT_RF": [2.0, -1.0],
            "SMB": [0.5, 0.25],
            "HML": [0.1, 0.2],
            "RMW": [0.0, 0.0],
            "CMA": [0.0, 0.0],
            "RF": [1.0, 1.0],
            "UMD": [3.0, -2.0],
        },
        index=month_ends,
    )

    strat_excess, ff_aligned = align_strategy_and_factors(daily_returns, ff, include_umd=True)

    # Strategy monthly return is 0; RF should be scaled to 0.01.
    assert strat_excess.loc[month_ends[0]] == pytest.approx(-0.01, rel=1e-12)
    assert strat_excess.loc[month_ends[1]] == pytest.approx(-0.01, rel=1e-12)

    assert "UMD" in ff_aligned.columns
    assert ff_aligned.loc[month_ends[0], "MKT_RF"] == pytest.approx(0.02, rel=1e-12)
    assert ff_aligned.loc[month_ends[0], "UMD"] == pytest.approx(0.03, rel=1e-12)
    assert np.isfinite(ff_aligned.values).all()

