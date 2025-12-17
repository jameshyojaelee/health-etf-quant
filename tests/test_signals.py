"""Tests for signal construction and weight generation."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.signals.momentum import compute_momentum_signal  # noqa: E402
from src.signals.ls_biotech_pharma import build_monthly_ls_weights  # noqa: E402
from src.signals.rotation_signals import build_monthly_rotation_weights  # noqa: E402


def test_momentum_signal_is_shifted_one_period():
    idx = pd.date_range("2020-01-31", periods=3, freq="ME")
    prices = pd.DataFrame({"XBI": [100.0, 110.0, 121.0]}, index=idx)

    mom = compute_momentum_signal(prices, lookback_months=1)
    # raw 1M returns are 10% at Feb and Mar; after shift, Mar's signal is Feb's return.
    assert np.isnan(mom.loc[idx[1], "XBI"])
    assert mom.loc[idx[2], "XBI"] == pytest.approx(0.10, rel=1e-12)


def test_ls_weights_simple_modes():
    idx = pd.date_range("2020-01-31", periods=3, freq="ME")
    regimes = pd.Series([0, 1, 0], index=idx, name="regime")

    w_flat = build_monthly_ls_weights(regimes, idx, risk_off_mode="flat")
    assert list(w_flat.columns) == ["XBI", "XPH"]
    assert w_flat.loc[idx[0], "XBI"] == 0.0 and w_flat.loc[idx[0], "XPH"] == 0.0
    assert w_flat.loc[idx[1], "XBI"] == 1.0 and w_flat.loc[idx[1], "XPH"] == -1.0

    w_long_pharma = build_monthly_ls_weights(regimes, idx, risk_off_mode="long_pharma")
    assert w_long_pharma.loc[idx[0], "XBI"] == 0.0 and w_long_pharma.loc[idx[0], "XPH"] == 1.0


def test_ls_weights_risk_balanced_path_runs():
    idx = pd.date_range("2020-01-31", periods=3, freq="ME")
    regimes = pd.Series([0, 1, 1], index=idx, name="regime")

    prices = pd.DataFrame({"XBI": [100.0, 110.0, 120.0], "XPH": [100.0, 90.0, 80.0]}, index=idx)
    vol_df = pd.DataFrame({"XBI": [0.2, 0.2, 0.2], "XPH": [0.2, 0.2, 0.2]}, index=idx)
    spread_mom = pd.Series([np.nan, 0.5, 0.5], index=idx, name="spread_momentum")

    w = build_monthly_ls_weights(
        regimes,
        prices=prices,
        vol_df=vol_df,
        spread_momentum=spread_mom,
        target_gross_exposure=1.0,
        spread_mom_threshold=0.0,
    )
    assert w.index.equals(prices.index)
    assert list(w.columns) == ["XBI", "XPH"]
    assert w.loc[idx[0]].abs().sum() == pytest.approx(0.0, abs=1e-12)
    assert w.loc[idx[1], "XBI"] > 0.0
    assert w.loc[idx[1], "XPH"] < 0.0


def test_rotation_weights_basic_properties():
    dates = pd.date_range("2020-01-01", "2020-04-30", freq="B")
    n = len(dates)

    prices = pd.DataFrame(
        {
            "XBI": np.linspace(100.0, 140.0, n),
            "XPH": np.full(n, 100.0),
            "IHF": np.linspace(100.0, 90.0, n),
            "IHI": np.linspace(100.0, 110.0, n),
            "XLV": np.linspace(100.0, 105.0, n),
        },
        index=dates,
    )

    weights = build_monthly_rotation_weights(
        prices,
        lookback_months=1,
        top_k=1,
        target_vol_annual=0.10,
        use_12m1m=False,
        use_ts_mom_gating=False,
        use_xlv_trend_filter=False,
        max_gross_leverage=1.5,
    )

    assert weights.index.equals(prices.index)
    assert list(weights.columns) == list(prices.columns)
    assert (weights.abs().sum(axis=1) <= 1.5 + 1e-12).all()

    last = weights.iloc[-1]
    assert (last.abs() > 0).sum() <= 1


def test_rotation_all_cash_when_all_momentum_negative():
    dates = pd.date_range("2020-01-01", "2020-06-30", freq="B")
    n = len(dates)
    prices = pd.DataFrame(
        {
            "XBI": np.linspace(100.0, 80.0, n),
            "XPH": np.linspace(100.0, 90.0, n),
            "IHF": np.linspace(100.0, 70.0, n),
            "IHI": np.linspace(100.0, 85.0, n),
            "XLV": np.linspace(100.0, 95.0, n),
        },
        index=dates,
    )

    weights = build_monthly_rotation_weights(
        prices,
        lookback_months=1,
        top_k=1,
        target_vol_annual=0.10,
        use_12m1m=False,
        use_ts_mom_gating=False,
        use_xlv_trend_filter=False,
    )
    assert weights.iloc[-1].abs().sum() == pytest.approx(0.0, abs=1e-12)


def test_rotation_defensive_when_all_momentum_negative():
    dates = pd.date_range("2020-01-01", "2020-06-30", freq="B")
    n = len(dates)
    prices = pd.DataFrame(
        {
            "XBI": np.linspace(100.0, 80.0, n),
            "XPH": np.linspace(100.0, 90.0, n),
            "IHF": np.linspace(100.0, 70.0, n),
            "IHI": np.linspace(100.0, 85.0, n),
            "XLV": np.linspace(100.0, 95.0, n),
        },
        index=dates,
    )

    weights = build_monthly_rotation_weights(
        prices,
        lookback_months=1,
        top_k=1,
        target_vol_annual=0.10,
        use_12m1m=False,
        use_ts_mom_gating=False,
        use_xlv_trend_filter=False,
        defensive_ticker="XLV",
    )
    last = weights.iloc[-1]
    assert last["XLV"] == pytest.approx(1.0, rel=1e-12)
    assert last.drop("XLV").abs().sum() == pytest.approx(0.0, abs=1e-12)
