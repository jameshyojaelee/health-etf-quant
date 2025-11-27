"""Tests for performance metrics."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.analysis.metrics import (  # noqa: E402
    compute_annual_vol,
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe,
)


def test_basic_metrics_constant_returns():
    daily_returns = pd.Series(0.001, index=pd.date_range("2020-01-01", periods=252, freq="B"))

    cagr = compute_cagr(daily_returns)
    annual_vol = compute_annual_vol(daily_returns)
    sharpe = compute_sharpe(daily_returns)
    equity_curve = (1 + daily_returns).cumprod()
    max_dd = compute_max_drawdown(equity_curve)

    expected_cagr = (1.001**252) - 1
    assert cagr == pytest.approx(expected_cagr, rel=1e-6)
    assert annual_vol == pytest.approx(0.0, abs=1e-12)
    assert np.isnan(sharpe)
    assert max_dd == pytest.approx(0.0, abs=1e-12)
