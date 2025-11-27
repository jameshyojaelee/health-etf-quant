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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run healthcare ETF strategies end-to-end.")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--tc_bps", type=float, default=10.0, help="Transaction cost in bps per round trip")
    parser.add_argument(
        "--strategy",
        choices=["regime", "rotation", "both"],
        default="both",
        help="Select which strategy to run",
    )
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


def print_summary(metrics: Dict[str, float]) -> None:
    """Pretty-print a single strategy summary."""
    print(
        f"{metrics['name']:<18} | CAGR: {metrics['cagr']:.2%} | Vol: {metrics['vol']:.2%} "
        f"| Sharpe: {metrics['sharpe']:.2f} | MaxDD: {metrics['max_dd']:.2%}"
    )


def build_synthetic_macro(prices: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Create simple placeholder macro series (TNX, SPY, VIX) for regime logic.

    Replace with real loaders when available; this stays deterministic for quick tests.
    """
    idx = prices.index
    spy_prices = prices.get("SPY") if "SPY" in prices.columns else prices.iloc[:, 0]
    tnx_yield = pd.Series(0.03 + 0.005 * np.sin(np.linspace(0, 6, len(idx))), index=idx, name="TNX")
    spy_ret = spy_prices.pct_change().fillna(0)
    vix = (20 + 80 * spy_ret.abs().rolling(21, min_periods=1).mean()).clip(10, 60)
    return tnx_yield, spy_prices, vix


def run_regime_strategy(prices: pd.DataFrame, tc_bps: float):
    """Run regime-based long-short between XBI and XPH."""
    price_slice = prices[["XBI", "XPH", "SPY"]].dropna()
    tnx_yield, spy_prices, vix = build_synthetic_macro(price_slice)
    features = compute_monthly_features(tnx_yield, spy_prices, vix)
    regimes = classify_regime(features)
    weights = build_monthly_ls_weights(regimes, price_slice.index)
    bt = run_backtest(price_slice[["XBI", "XPH"]], weights, transaction_cost_bps=tc_bps)
    return bt


def run_rotation_strategy(prices: pd.DataFrame, tc_bps: float):
    """Run momentum + vol-targeted rotation across healthcare ETFs."""
    tickers = ["XBI", "XPH", "IHF", "IHI", "XLV"]
    price_slice = prices[tickers].dropna()
    weights = build_monthly_rotation_weights(price_slice)
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

    if args.strategy in ("regime", "both"):
        regime_bt = run_regime_strategy(prices, tc_bps=args.tc_bps)
        summaries.append(summarize("Regime LS", regime_bt.daily_returns, regime_bt.equity_curve))

    if args.strategy in ("rotation", "both"):
        rotation_bt = run_rotation_strategy(prices, tc_bps=args.tc_bps)
        summaries.append(summarize("Rotation", rotation_bt.daily_returns, rotation_bt.equity_curve))

    print("\nStrategy Summary:")
    for m in summaries:
        print_summary(m)


if __name__ == "__main__":
    main()
