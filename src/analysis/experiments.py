"""Structured experiment runner for parameter sweeps (train/test aware)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src import config as project_config
from src.analysis.robustness_extension import sweep_regime_ls_parameters, sweep_rotation_parameters
from src.data.etf_loader import load_clean_prices
from src.portfolio.vol_target import estimate_rolling_vol
from src.signals.ls_biotech_pharma import compute_spread_momentum
from src.signals.regime import classify_regime, compute_monthly_features
from run_strategies import fetch_macro_series


def _load_grid(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in grid file: {path}")
    return data


def _ensure_list(value: Any, default: list[Any]) -> list[Any]:
    if value is None:
        return default
    if isinstance(value, list):
        return value
    return [value]


def run_rotation_experiment(
    prices: pd.DataFrame,
    *,
    grid: dict[str, Any],
    split_date: str,
    transaction_cost_bps: float,
) -> pd.DataFrame:
    lookbacks = _ensure_list(grid.get("lookbacks"), [6, 12])
    top_ks = _ensure_list(grid.get("top_ks"), [1, 2])
    use_ts_flags = _ensure_list(grid.get("use_ts_flags"), [True])
    use_12m1m_flags = _ensure_list(grid.get("use_12m1m_flags"), [True])
    use_xlv_filters = _ensure_list(grid.get("use_xlv_filters"), [True])
    ts_lookbacks = _ensure_list(grid.get("ts_lookbacks"), [6, 12])
    target_vols = _ensure_list(grid.get("target_vols"), [0.10])
    max_gross_list = _ensure_list(grid.get("max_gross_list"), [1.5])

    return sweep_rotation_parameters(
        prices,
        lookbacks=[int(x) for x in lookbacks],
        top_ks=[int(x) for x in top_ks],
        use_ts_flags=[bool(x) for x in use_ts_flags],
        use_12m1m_flags=[bool(x) for x in use_12m1m_flags],
        use_xlv_filters=[bool(x) for x in use_xlv_filters],
        ts_lookbacks=[int(x) for x in ts_lookbacks],
        target_vols=[float(x) for x in target_vols],
        max_gross_list=[float(x) for x in max_gross_list],
        transaction_cost_bps=float(transaction_cost_bps),
        split_date=split_date,
    )


def run_regime_ls_experiment(
    prices: pd.DataFrame,
    *,
    grid: dict[str, Any],
    split_date: str,
    transaction_cost_bps: float,
) -> pd.DataFrame:
    spread_mom_thresholds = _ensure_list(grid.get("spread_mom_thresholds"), [0.0])
    target_gross_list = _ensure_list(grid.get("target_gross_list"), [1.0])
    rate_thresholds = grid.get("rate_thresholds")
    vix_thresholds = grid.get("vix_thresholds")
    spy_ret_thresholds = grid.get("spy_ret_thresholds")
    vol_lookback_days = int(grid.get("vol_lookback_days", 60))
    spread_mom_lookback_months = int(grid.get("spread_mom_lookback_months", 6))

    price_slice = prices[["XBI", "XPH", "SPY"]].dropna()
    tnx_yield, vix = fetch_macro_series(start=None, end=None, price_index=price_slice.index)
    monthly_features = compute_monthly_features(
        tnx_yield,
        price_slice["SPY"],
        vix,
        lookback_months_rate=project_config.REGIME_LOOKBACK_MONTHS_RATE,
        lookback_months_spy=project_config.REGIME_LOOKBACK_MONTHS_SPY,
    )
    regimes = classify_regime(monthly_features, vix_threshold=project_config.REGIME_VIX_THRESHOLD)
    spread_mom = compute_spread_momentum(
        price_slice[["XBI", "XPH"]],
        lookback_months=spread_mom_lookback_months,
    )
    vol_df = estimate_rolling_vol(
        price_slice[["XBI", "XPH"]].pct_change().fillna(0.0),
        lookback_days=vol_lookback_days,
    )

    return sweep_regime_ls_parameters(
        prices=price_slice[["XBI", "XPH"]],
        vol_df=vol_df,
        regime_labels=regimes,
        spread_momentum=spread_mom,
        spread_mom_thresholds=[float(x) for x in spread_mom_thresholds],
        target_gross_list=[float(x) for x in target_gross_list],
        monthly_features=monthly_features if any(v is not None for v in [rate_thresholds, vix_thresholds, spy_ret_thresholds]) else None,
        rate_thresholds=[float(x) for x in rate_thresholds] if rate_thresholds is not None else None,
        vix_thresholds=[float(x) for x in vix_thresholds] if vix_thresholds is not None else None,
        spy_ret_thresholds=[float(x) for x in spy_ret_thresholds] if spy_ret_thresholds is not None else None,
        transaction_cost_bps=float(transaction_cost_bps),
        split_date=split_date,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run train/test-aware parameter sweeps.")
    parser.add_argument("--strategy", choices=["rotation", "regime_ls"], required=True)
    parser.add_argument("--split_date", type=str, default="2015-01-01")
    parser.add_argument("--tc_bps", type=float, default=project_config.DEFAULT_TRANSACTION_COST_BPS)
    parser.add_argument("--grid", type=str, default=None, help="Optional YAML file describing the parameter grid")
    parser.add_argument("--out", type=str, required=True, help="Output CSV path")
    parser.add_argument("--top_n", type=int, default=20, help="Print top N configs by OOS Sharpe")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    grid = _load_grid(Path(args.grid)) if args.grid else {}

    prices = load_clean_prices().dropna(how="any")
    if args.strategy == "rotation":
        tickers = [t for t in ["XBI", "XPH", "IHF", "IHI", "XLV"] if t in prices.columns]
        price_slice = prices[tickers].dropna()
        df = run_rotation_experiment(
            price_slice,
            grid=grid,
            split_date=args.split_date,
            transaction_cost_bps=args.tc_bps,
        )
        sort_key = "sharpe_out"
    else:
        df = run_regime_ls_experiment(
            prices,
            grid=grid,
            split_date=args.split_date,
            transaction_cost_bps=args.tc_bps,
        )
        sort_key = "sharpe_out"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    if sort_key in df.columns:
        top = df.sort_values(sort_key, ascending=False).head(args.top_n)
        print(f"Saved {len(df)} rows to {out_path}")
        print(f"Top {min(args.top_n, len(df))} by {sort_key}:")
        print(top.to_string(index=False))
    else:
        print(f"Saved {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()

