"""Simple driver to run regime long-short and momentum rotation strategies end-to-end.

Usage:
    python run_strategies.py --start 2008-01-01 --end 2023-12-31 --tc_bps 10 --strategy both

This script is a quick regression harness to verify that signals, backtest, and metrics
wire together after code changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

# Ensure src/ is on path when executed from repo root.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src import config as project_config
from src.data.etf_loader import load_clean_prices
from src.signals.regime import classify_regime, compute_monthly_features
from src.signals.ls_biotech_pharma import build_monthly_ls_weights
from src.signals.rotation_signals import build_monthly_rotation_weights
from src.backtest.engine import run_backtest
from src.analysis.metrics import (
    compute_annual_vol,
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe,
)
from src.data.macro_loader import load_tnx_10y, load_vix
from src.analysis.factor_analysis import align_strategy_and_factors, run_ff_regression
from src.data.ff_factors import load_ff_factors_monthly


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run healthcare ETF strategies end-to-end.")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--tc_bps",
        type=float,
        default=project_config.DEFAULT_TRANSACTION_COST_BPS,
        help="Transaction cost in bps per round trip",
    )
    parser.add_argument(
        "--strategy",
        choices=["regime", "rotation", "both"],
        default="both",
        help="Select which strategy to run",
    )
    parser.add_argument("--split_year", type=int, default=None, help="Optional train/test split year (e.g., 2015)")

    # Regime strategy parameters (defaults can be set in config/settings.yaml)
    parser.add_argument(
        "--rate_lookback_months",
        type=int,
        default=project_config.REGIME_LOOKBACK_MONTHS_RATE,
        help="Lookback (months) for 10Y yield change",
    )
    parser.add_argument(
        "--spy_lookback_months",
        type=int,
        default=project_config.REGIME_LOOKBACK_MONTHS_SPY,
        help="Lookback (months) for SPY return",
    )
    parser.add_argument("--rate_threshold", type=float, default=0.0, help="Risk-on if delta_rate <= threshold")
    parser.add_argument("--spy_ret_threshold", type=float, default=0.0, help="Risk-on if SPY return >= threshold")
    parser.add_argument(
        "--vix_threshold",
        type=float,
        default=project_config.REGIME_VIX_THRESHOLD,
        help="Risk-on if VIX <= threshold",
    )
    parser.add_argument(
        "--risk_off_mode",
        choices=["flat", "long_pharma", "reverse"],
        default="flat",
        help="Risk-off behavior for the LS spread",
    )

    # Rotation strategy parameters (defaults can be set in config/settings.yaml)
    parser.add_argument(
        "--momentum_lookback_months",
        type=int,
        default=project_config.ROTATION_MOMENTUM_LOOKBACK_MONTHS,
        help="Momentum lookback (months) when not using 12-1 momentum",
    )
    parser.add_argument("--top_k", type=int, default=project_config.ROTATION_TOP_K, help="Select top K ETFs by momentum")
    parser.add_argument(
        "--target_vol_annual",
        type=float,
        default=project_config.ROTATION_TARGET_VOL_ANNUAL,
        help="Target annualized volatility",
    )
    parser.add_argument("--max_gross_leverage", type=float, default=1.5, help="Max gross exposure cap")
    parser.add_argument("--no_ts_mom_gating", action="store_true", help="Disable per-asset TS momentum gating")
    parser.add_argument("--no_xlv_trend_filter", action="store_true", help="Disable XLV trend (risk-off) filter")
    parser.add_argument("--no_12m1m", action="store_true", help="Use simple lookback momentum instead of 12-1")
    return parser.parse_args()


def summarize(name: str, daily_returns: pd.Series, equity_curve: pd.Series) -> Dict[str, float]:
    """Compute key metrics for display."""
    return {
        "name": name,
        "cagr": compute_cagr(daily_returns),
        "vol": compute_annual_vol(daily_returns),
        "sharpe": compute_sharpe(daily_returns),
        "max_dd": compute_max_drawdown(equity_curve),
    }


def summarize_split(name: str, daily_returns: pd.Series, split_date: pd.Timestamp) -> Dict[str, Dict[str, float]]:
    """Compute train/test metrics split at split_date."""
    train = daily_returns.loc[:split_date]
    test = daily_returns.loc[split_date + pd.Timedelta(days=1) :]
    return {
        "train": {
            "cagr": compute_cagr(train),
            "vol": compute_annual_vol(train),
            "sharpe": compute_sharpe(train),
            "max_dd": compute_max_drawdown((1 + train.fillna(0)).cumprod()),
        },
        "test": {
            "cagr": compute_cagr(test),
            "vol": compute_annual_vol(test),
            "sharpe": compute_sharpe(test),
            "max_dd": compute_max_drawdown((1 + test.fillna(0)).cumprod()),
        },
    }


def print_summary(metrics: Dict[str, float]) -> None:
    """Pretty-print a single strategy summary."""
    print(
        f"{metrics['name']:<18} | CAGR: {metrics['cagr']:.2%} | Vol: {metrics['vol']:.2%} "
        f"| Sharpe: {metrics['sharpe']:.2f} | MaxDD: {metrics['max_dd']:.2%}"
    )


def fetch_macro_series(
    start: str | None,
    end: str | None,
    price_index: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series]:
    """Download TNX (10Y yield) and VIX levels and align to price calendar."""
    start_date = start or price_index.min().strftime("%Y-%m-%d")
    end_date = end or price_index.max().strftime("%Y-%m-%d")
    tnx = load_tnx_10y(start=start_date, end=end_date)
    vix = load_vix(start=start_date, end=end_date)
    tnx = tnx.reindex(price_index).ffill()
    vix = vix.reindex(price_index).ffill()
    tnx.name = "TNX"
    vix.name = "VIX"
    return tnx, vix


def run_regime_strategy(
    prices: pd.DataFrame,
    tc_bps: float,
    start: str | None,
    end: str | None,
    *,
    rate_lookback_months: int = project_config.REGIME_LOOKBACK_MONTHS_RATE,
    spy_lookback_months: int = project_config.REGIME_LOOKBACK_MONTHS_SPY,
    rate_threshold: float = 0.0,
    vix_threshold: float = project_config.REGIME_VIX_THRESHOLD,
    spy_ret_threshold: float = 0.0,
    risk_off_mode: str = "flat",
):
    """Run regime-based long-short between XBI and XPH."""
    price_slice = prices[["XBI", "XPH", "SPY"]].dropna()
    tnx_yield, vix = fetch_macro_series(start=start, end=end, price_index=price_slice.index)
    spy_prices = price_slice["SPY"]
    features = compute_monthly_features(
        tnx_yield,
        spy_prices,
        vix,
        lookback_months_rate=rate_lookback_months,
        lookback_months_spy=spy_lookback_months,
        vix_window_months=1,
    )
    regimes = classify_regime(
        features,
        rate_threshold=rate_threshold,
        vix_threshold=vix_threshold,
        spy_ret_threshold=spy_ret_threshold,
    )
    weights = build_monthly_ls_weights(regimes, price_slice.index, risk_off_mode=risk_off_mode)
    bt = run_backtest(price_slice[["XBI", "XPH"]], weights, transaction_cost_bps=tc_bps)
    risk_on_frac = regimes.mean()
    return bt, risk_on_frac


def run_rotation_strategy(
    prices: pd.DataFrame,
    tc_bps: float,
    *,
    momentum_lookback_months: int = project_config.ROTATION_MOMENTUM_LOOKBACK_MONTHS,
    top_k: int = project_config.ROTATION_TOP_K,
    target_vol_annual: float = project_config.ROTATION_TARGET_VOL_ANNUAL,
    use_12m1m: bool = True,
    use_ts_mom_gating: bool = True,
    use_xlv_trend_filter: bool = True,
    max_gross_leverage: float = 1.5,
):
    """Run momentum + vol-targeted rotation across healthcare ETFs."""
    tickers = ["XBI", "XPH", "IHF", "IHI", "XLV"]
    price_slice = prices[tickers].dropna()
    weights = build_monthly_rotation_weights(
        price_slice,
        lookback_months=momentum_lookback_months,
        top_k=top_k,
        target_vol_annual=target_vol_annual,
        use_12m1m=use_12m1m,
        use_ts_mom_gating=use_ts_mom_gating,
        use_xlv_trend_filter=use_xlv_trend_filter,
        max_gross_leverage=max_gross_leverage,
    )
    bt = run_backtest(price_slice, weights, transaction_cost_bps=tc_bps)
    return bt


def main() -> None:
    args = parse_args()
    prices = load_clean_prices()
    if args.start:
        prices = prices.loc[pd.to_datetime(args.start) :]
    if args.end:
        prices = prices.loc[: pd.to_datetime(args.end)]

    print("Running strategies with transaction_cost_bps=", args.tc_bps)
    summaries = []
    bench = []
    strategy_returns: Dict[str, pd.Series] = {}
    strategy_equity: Dict[str, pd.Series] = {}

    if args.strategy in ("regime", "both"):
        regime_bt, risk_on_frac = run_regime_strategy(
            prices,
            tc_bps=args.tc_bps,
            start=args.start,
            end=args.end,
            rate_lookback_months=args.rate_lookback_months,
            spy_lookback_months=args.spy_lookback_months,
            rate_threshold=args.rate_threshold,
            vix_threshold=args.vix_threshold,
            spy_ret_threshold=args.spy_ret_threshold,
            risk_off_mode=args.risk_off_mode,
        )
        summaries.append(summarize("Regime LS", regime_bt.daily_returns, regime_bt.equity_curve))
        strategy_returns["Regime LS"] = regime_bt.daily_returns
        strategy_equity["Regime LS"] = regime_bt.equity_curve
        print(f"Regime risk-on fraction: {risk_on_frac:.1%}")

    if args.strategy in ("rotation", "both"):
        rotation_bt = run_rotation_strategy(
            prices,
            tc_bps=args.tc_bps,
            momentum_lookback_months=args.momentum_lookback_months,
            top_k=args.top_k,
            target_vol_annual=args.target_vol_annual,
            use_12m1m=not args.no_12m1m,
            use_ts_mom_gating=not args.no_ts_mom_gating,
            use_xlv_trend_filter=not args.no_xlv_trend_filter,
            max_gross_leverage=args.max_gross_leverage,
        )
        summaries.append(summarize("Rotation", rotation_bt.daily_returns, rotation_bt.equity_curve))
        strategy_returns["Rotation"] = rotation_bt.daily_returns
        strategy_equity["Rotation"] = rotation_bt.equity_curve

    # Benchmarks
    if "XLV" in prices.columns:
        w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w["XLV"] = 1.0
        bench_bt = run_backtest(prices[w.columns], w, transaction_cost_bps=0.0)
        bench.append(summarize("Buy&Hold XLV", bench_bt.daily_returns, bench_bt.equity_curve))
    if "SPY" in prices.columns:
        w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w["SPY"] = 1.0
        bench_bt = run_backtest(prices[w.columns], w, transaction_cost_bps=0.0)
        bench.append(summarize("Buy&Hold SPY", bench_bt.daily_returns, bench_bt.equity_curve))

    # Equal-weight healthcare basket (monthly rebalance)
    hc_cols = [c for c in ["XBI", "XPH", "IHF", "IHI", "XLV"] if c in prices.columns]
    if hc_cols:
        month_ends = prices.resample("ME").last().index
        ew_monthly = pd.DataFrame(1 / len(hc_cols), index=month_ends, columns=hc_cols)
        ew_daily = ew_monthly.reindex(prices.index, method="ffill").fillna(0.0)
        ew_bt = run_backtest(prices[hc_cols], ew_daily, transaction_cost_bps=args.tc_bps)
        bench.append(summarize("Equal-Weight HC", ew_bt.daily_returns, ew_bt.equity_curve))

    print("\nStrategy Summary:")
    for m in summaries:
        print_summary(m)
    if bench:
        print("\nBenchmarks:")
        for m in bench:
            print_summary(m)

    if args.split_year and strategy_returns:
        split_date = pd.Timestamp(year=args.split_year, month=12, day=31)
        print(f"\nTrain/Test split at {split_date.date()}:")
        for name, rets in strategy_returns.items():
            splits = summarize_split(name, rets, split_date)
            train = splits["train"]
            test = splits["test"]
            print(
                f"{name} train: CAGR {train['cagr']:.2%}, Sharpe {train['sharpe']:.2f}; "
                f"test: CAGR {test['cagr']:.2%}, Sharpe {test['sharpe']:.2f}"
            )

    # Factor regression if data available
    try:
        ff = load_ff_factors_monthly()
        print("\nFactor Regression (monthly excess returns vs FF5):")
        for name, daily_ret in strategy_returns.items():
            strat_excess, ff_aligned = align_strategy_and_factors(daily_ret, ff)
            reg = run_ff_regression(strat_excess, ff_aligned)
            print(
                f"{name}: alpha={reg['alpha_annual']:.2%} (t={reg['alpha_tstat']:.2f}), "
                f"R^2={reg['r2']:.3f}, n={reg['n_obs']}"
            )
    except FileNotFoundError:
        print("\nFama-French factor file not found; skip factor regression.")


if __name__ == "__main__":
    main()
