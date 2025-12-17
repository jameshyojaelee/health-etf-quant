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
from src.signals.ls_biotech_pharma import build_monthly_ls_weights, compute_spread_momentum
from src.signals.rotation_signals import build_monthly_rotation_weights
from src.backtest.engine import run_backtest
from src.analysis.metrics import (
    compute_annual_vol,
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe,
)
from src.portfolio.vol_target import estimate_rolling_vol
from src.data.macro_loader import load_tnx_10y, load_vix
from src.analysis.factor_analysis import align_strategy_and_factors, run_ff_regression
from src.data.ff_factors import load_ff_factors_monthly


def parse_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "--settings",
        type=str,
        default=None,
        help="Optional YAML settings path to override defaults for this run",
    )
    pre_args, _ = pre_parser.parse_known_args()
    if pre_args.settings:
        settings_path = Path(pre_args.settings)
        if not settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {settings_path}")
        project_config.apply_settings(project_config.load_settings(settings_path))

    parser = argparse.ArgumentParser(description="Run healthcare ETF strategies end-to-end.")
    parser.add_argument(
        "--settings",
        type=str,
        default=pre_args.settings,
        help="Optional YAML settings path to override defaults for this run",
    )
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
    parser.add_argument(
        "--ls_mode",
        choices=["simple", "risk_balanced"],
        default="simple",
        help="Regime LS implementation: simple spread or risk-balanced (vol + spread momentum gated)",
    )
    parser.add_argument(
        "--spread_mom_threshold",
        type=float,
        default=float(project_config.REGIME_SETTINGS.get("spread_mom_threshold", 0.0)),
        help="Risk-balanced LS: require spread momentum > threshold to take risk",
    )
    parser.add_argument(
        "--target_gross_exposure",
        type=float,
        default=float(project_config.REGIME_SETTINGS.get("target_gross_exposure", 1.0)),
        help="Risk-balanced LS: target gross exposure for the spread",
    )
    parser.add_argument(
        "--vol_lookback_days",
        type=int,
        default=int(project_config.REGIME_SETTINGS.get("vol_lookback_days", 60)),
        help="Risk-balanced LS: rolling vol lookback in trading days",
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
    parser.add_argument(
        "--defensive_ticker",
        type=str,
        default=None,
        help="When all momentum scores <= 0, allocate 100% to this ticker instead of cash (if present in prices).",
    )
    return parser.parse_args()


def summarize(
    name: str,
    daily_returns: pd.Series,
    equity_curve: pd.Series,
    *,
    weights: pd.DataFrame | None = None,
    turnover: pd.Series | None = None,
) -> Dict[str, float]:
    """Compute key metrics for display."""
    out: Dict[str, float] = {
        "name": name,
        "cagr": compute_cagr(daily_returns),
        "vol": compute_annual_vol(daily_returns),
        "sharpe": compute_sharpe(daily_returns),
        "max_dd": compute_max_drawdown(equity_curve),
    }
    if weights is not None and not weights.empty:
        out["avg_gross"] = float(weights.abs().sum(axis=1).mean())
        out["avg_net"] = float(weights.sum(axis=1).mean())
    if turnover is not None and not turnover.empty:
        out["avg_turnover"] = float(turnover.mean())
    return out


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
    extras = []
    if "avg_gross" in metrics:
        extras.append(f"Gross: {metrics['avg_gross']:.2f}")
    if "avg_net" in metrics:
        extras.append(f"Net: {metrics['avg_net']:.2f}")
    if "avg_turnover" in metrics:
        extras.append(f"Turnover: {metrics['avg_turnover']:.3f}")
    extra_str = (" | " + " | ".join(extras)) if extras else ""
    print(
        f"{metrics['name']:<18} | CAGR: {metrics['cagr']:.2%} | Vol: {metrics['vol']:.2%} "
        f"| Sharpe: {metrics['sharpe']:.2f} | MaxDD: {metrics['max_dd']:.2%}{extra_str}"
    )


def fetch_macro_series(
    start: str | None,
    end: str | None,
    price_index: pd.DatetimeIndex,
) -> tuple[pd.Series, pd.Series]:
    """Load macro series (10Y yield + VIX) and align to the price calendar."""
    start_date = start or price_index.min().strftime("%Y-%m-%d")
    end_date = end or price_index.max().strftime("%Y-%m-%d")

    macro_source = project_config.MACRO_SOURCE
    if macro_source == "fred":
        from src.data.fred_loader import load_10y_yield, load_vix_level

        tnx = load_10y_yield(api_key=project_config.MACRO_FRED_API_KEY, start=start_date, end=end_date)
        vix = load_vix_level(api_key=project_config.MACRO_FRED_API_KEY, start=start_date, end=end_date)
    elif macro_source == "yahoo":
        tnx = load_tnx_10y(start=start_date, end=end_date)
        vix = load_vix(start=start_date, end=end_date)
    else:
        raise ValueError(f"Unsupported macro.source={macro_source!r}; expected 'yahoo' or 'fred'.")

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
    ls_mode: str = "simple",
    spread_mom_threshold: float = 0.0,
    target_gross_exposure: float = 1.0,
    vol_lookback_days: int = 60,
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
    if ls_mode == "simple":
        weights = build_monthly_ls_weights(regimes, price_slice.index, risk_off_mode=risk_off_mode)
    elif ls_mode == "risk_balanced":
        spread_mom = compute_spread_momentum(price_slice[["XBI", "XPH"]], lookback_months=6)
        vol_df = estimate_rolling_vol(
            price_slice[["XBI", "XPH"]].pct_change().fillna(0.0),
            lookback_days=vol_lookback_days,
        )
        weights = build_monthly_ls_weights(
            regime_labels=regimes,
            prices=price_slice[["XBI", "XPH"]],
            vol_df=vol_df,
            spread_momentum=spread_mom,
            target_gross_exposure=target_gross_exposure,
            spread_mom_threshold=spread_mom_threshold,
        )
    else:
        raise ValueError("ls_mode must be one of {'simple','risk_balanced'}.")
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
    defensive_ticker: str | None = None,
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
        defensive_ticker=defensive_ticker,
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
            ls_mode=args.ls_mode,
            spread_mom_threshold=args.spread_mom_threshold,
            target_gross_exposure=args.target_gross_exposure,
            vol_lookback_days=args.vol_lookback_days,
        )
        summaries.append(
            summarize(
                "Regime LS",
                regime_bt.daily_returns,
                regime_bt.equity_curve,
                weights=regime_bt.weights,
                turnover=regime_bt.turnover,
            )
        )
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
            defensive_ticker=args.defensive_ticker,
        )
        summaries.append(
            summarize(
                "Rotation",
                rotation_bt.daily_returns,
                rotation_bt.equity_curve,
                weights=rotation_bt.weights,
                turnover=rotation_bt.turnover,
            )
        )
        strategy_returns["Rotation"] = rotation_bt.daily_returns
        strategy_equity["Rotation"] = rotation_bt.equity_curve

    # Benchmarks
    if "XLV" in prices.columns:
        w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w["XLV"] = 1.0
        bench_bt = run_backtest(prices[w.columns], w, transaction_cost_bps=0.0)
        bench.append(
            summarize(
                "Buy&Hold XLV",
                bench_bt.daily_returns,
                bench_bt.equity_curve,
                weights=bench_bt.weights,
                turnover=bench_bt.turnover,
            )
        )
    if "SPY" in prices.columns:
        w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w["SPY"] = 1.0
        bench_bt = run_backtest(prices[w.columns], w, transaction_cost_bps=0.0)
        bench.append(
            summarize(
                "Buy&Hold SPY",
                bench_bt.daily_returns,
                bench_bt.equity_curve,
                weights=bench_bt.weights,
                turnover=bench_bt.turnover,
            )
        )

    # Equal-weight healthcare basket (monthly rebalance)
    hc_cols = [c for c in ["XBI", "XPH", "IHF", "IHI", "XLV"] if c in prices.columns]
    if hc_cols:
        month_ends = prices.resample("ME").last().index
        ew_monthly = pd.DataFrame(1 / len(hc_cols), index=month_ends, columns=hc_cols)
        ew_daily = ew_monthly.reindex(prices.index, method="ffill").fillna(0.0)
        ew_bt = run_backtest(prices[hc_cols], ew_daily, transaction_cost_bps=args.tc_bps)
        bench.append(
            summarize(
                "Equal-Weight HC",
                ew_bt.daily_returns,
                ew_bt.equity_curve,
                weights=ew_bt.weights,
                turnover=ew_bt.turnover,
            )
        )

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
        try:
            ff = load_ff_factors_monthly(include_umd=True)
            include_umd = True
        except ValueError:
            ff = load_ff_factors_monthly(include_umd=False)
            include_umd = False

        label = "FF5+UMD" if include_umd else "FF5"
        print(f"\nFactor Regression (monthly excess returns vs {label}):")
        for name, daily_ret in strategy_returns.items():
            strat_excess, ff_aligned = align_strategy_and_factors(daily_ret, ff, include_umd=include_umd)
            reg = run_ff_regression(strat_excess, ff_aligned)
            print(
                f"{name}: alpha={reg['alpha_annual']:.2%} (t={reg['alpha_tstat']:.2f}), "
                f"R^2={reg['r2']:.3f}, n={reg['n_obs']}"
            )
    except Exception as e:
        print(f"\nFactor regression skipped due to error: {e}")


if __name__ == "__main__":
    main()
