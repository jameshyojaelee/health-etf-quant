"""Generate summary CSV and plots for healthcare strategies."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Ensure repo root (and `src/`) are on path when executed as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src import config as project_config
from src.analysis.robustness_extension import sweep_regime_ls_parameters, sweep_rotation_parameters
from src.data.etf_loader import load_clean_prices
from src.backtest.engine import run_backtest
from src.plots.plotting import plot_drawdowns_panel, plot_weights_heatmap
from run_strategies import (
    fetch_macro_series,
    run_rotation_strategy,
    summarize,
)
from src.signals.regime import compute_monthly_features, classify_regime
from src.signals.ls_biotech_pharma import compute_spread_momentum, build_monthly_ls_weights
from src.portfolio.vol_target import estimate_rolling_vol


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate results bundle (CSV + plots).")
    parser.add_argument(
        "--settings",
        type=str,
        default=None,
        help="Optional YAML settings path to override defaults for this run",
    )
    parser.add_argument(
        "--run_sweeps",
        action="store_true",
        help="Optionally run small parameter sweeps and save CSVs under results/",
    )
    parser.add_argument(
        "--sweep_split_date",
        type=str,
        default="2015-01-01",
        help="Train/test split date for sweeps (YYYY-MM-DD)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.settings:
        settings_path = Path(args.settings)
        if not settings_path.exists():
            raise FileNotFoundError(f"Settings file not found: {settings_path}")
        project_config.apply_settings(project_config.load_settings(settings_path))

    results_dir = Path(__file__).resolve().parent
    tc_bps = project_config.DEFAULT_TRANSACTION_COST_BPS
    prices = load_clean_prices().dropna(how="any")

    # Build regime LS with current macro and spread momentum/vol
    price_slice = prices[["XBI", "XPH", "SPY"]].dropna()
    tnx, vix = fetch_macro_series(start=None, end=None, price_index=price_slice.index)
    features = compute_monthly_features(
        tnx,
        price_slice["SPY"],
        vix,
        lookback_months_rate=project_config.REGIME_LOOKBACK_MONTHS_RATE,
        lookback_months_spy=project_config.REGIME_LOOKBACK_MONTHS_SPY,
        vix_window_months=1,
    )
    regimes = classify_regime(features, vix_threshold=project_config.REGIME_VIX_THRESHOLD)
    spread_mom = compute_spread_momentum(
        price_slice[["XBI", "XPH"]],
        lookback_months=int(project_config.REGIME_SETTINGS.get("spread_mom_lookback_months", 6)),
    )
    vol_df = estimate_rolling_vol(price_slice[["XBI", "XPH"]].pct_change().fillna(0.0))
    ls_weights = build_monthly_ls_weights(
        regime_labels=regimes,
        prices=price_slice[["XBI", "XPH"]],
        vol_df=vol_df,
        spread_momentum=spread_mom,
        target_gross_exposure=float(project_config.REGIME_SETTINGS.get("target_gross_exposure", 1.0)),
        spread_mom_threshold=float(project_config.REGIME_SETTINGS.get("spread_mom_threshold", 0.0)),
    )
    regime_bt = run_backtest(price_slice[["XBI", "XPH"]], ls_weights, transaction_cost_bps=tc_bps)

    rotation_bt = run_rotation_strategy(
        prices,
        tc_bps=tc_bps,
        momentum_lookback_months=project_config.ROTATION_MOMENTUM_LOOKBACK_MONTHS,
        top_k=project_config.ROTATION_TOP_K,
        target_vol_annual=project_config.ROTATION_TARGET_VOL_ANNUAL,
    )

    summaries = [
        summarize("Regime LS", regime_bt.daily_returns, regime_bt.equity_curve),
        summarize("Rotation", rotation_bt.daily_returns, rotation_bt.equity_curve),
    ]

    # Benchmarks
    bench = []
    if "XLV" in prices.columns:
        w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w["XLV"] = 1.0
        xl_bt = run_backtest(prices[w.columns], w, transaction_cost_bps=0.0)
        bench.append(summarize("Buy&Hold XLV", xl_bt.daily_returns, xl_bt.equity_curve))
        xl_equity = xl_bt.equity_curve.rename("XLV")
    else:
        xl_equity = None

    if "SPY" in prices.columns:
        w = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        w["SPY"] = 1.0
        spy_bt = run_backtest(prices[w.columns], w, transaction_cost_bps=0.0)
        bench.append(summarize("Buy&Hold SPY", spy_bt.daily_returns, spy_bt.equity_curve))
        spy_equity = spy_bt.equity_curve.rename("SPY")
    else:
        spy_equity = None

    hc_cols = [c for c in ["XBI", "XPH", "IHF", "IHI", "XLV"] if c in prices.columns]
    if hc_cols:
        month_ends = prices.resample("ME").last().index
        ew_monthly = pd.DataFrame(1 / len(hc_cols), index=month_ends, columns=hc_cols)
        ew_daily = ew_monthly.reindex(prices.index, method="ffill").fillna(0.0)
        ew_bt = run_backtest(prices[hc_cols], ew_daily, transaction_cost_bps=tc_bps)
        bench.append(summarize("Equal-Weight HC", ew_bt.daily_returns, ew_bt.equity_curve))
        ew_equity = ew_bt.equity_curve.rename("Equal-Weight HC")
    else:
        ew_equity = None

    summary_df = pd.DataFrame(summaries + bench)
    summary_df.to_csv(results_dir / "strategy_summary.csv", index=False)

    if args.run_sweeps:
        rotation_tickers = [t for t in ["XBI", "XPH", "IHF", "IHI", "XLV"] if t in prices.columns]
        rotation_sweep = sweep_rotation_parameters(
            prices[rotation_tickers].dropna(),
            lookbacks=[6, 12],
            top_ks=[1, 2],
            use_ts_flags=[True, False],
            use_12m1m_flags=[True],
            use_xlv_filters=[True],
            ts_lookbacks=[6, 12],
            target_vols=[project_config.ROTATION_TARGET_VOL_ANNUAL],
            max_gross_list=[1.5],
            transaction_cost_bps=tc_bps,
            split_date=args.sweep_split_date,
        )
        rotation_sweep.to_csv(results_dir / "rotation_sweep.csv", index=False)

        regime_sweep = sweep_regime_ls_parameters(
            prices=price_slice[["XBI", "XPH"]],
            vol_df=vol_df,
            regime_labels=regimes,
            spread_momentum=spread_mom,
            spread_mom_thresholds=[0.0, 0.1],
            target_gross_list=[1.0, 1.5],
            transaction_cost_bps=tc_bps,
            split_date=args.sweep_split_date,
        )
        regime_sweep.to_csv(results_dir / "regime_sweep.csv", index=False)

    curves = [rotation_bt.equity_curve.rename("Rotation"), regime_bt.equity_curve.rename("Regime LS")]
    if xl_equity is not None:
        curves.append(xl_equity)
    if spy_equity is not None:
        curves.append(spy_equity)
    if ew_equity is not None:
        curves.append(ew_equity)
    curves_df = pd.concat(curves, axis=1)
    ax = curves_df.plot(figsize=(10, 6), title="Equity Curves")
    ax.set_ylabel("Cumulative Wealth")
    plt.tight_layout()
    plt.savefig(results_dir / "equity_curves.png")
    plt.close()

    plot_drawdowns_panel(curves_df, out_path=results_dir / "drawdowns.png")
    plot_weights_heatmap(
        rotation_bt.weights,
        title="Rotation Weights (Monthly)",
        out_path=results_dir / "weights_heatmap_rotation.png",
    )
    plot_weights_heatmap(
        regime_bt.weights,
        title="Regime LS Weights (Monthly)",
        out_path=results_dir / "weights_heatmap_regime.png",
    )

    metrics_plot = summary_df.set_index("name")[["cagr", "sharpe"]]
    metrics_plot.plot(kind="bar", figsize=(10, 6), title="CAGR and Sharpe")
    plt.ylabel("Value")
    plt.tight_layout()
    plt.savefig(results_dir / "metrics_bar.png")
    plt.close()

    print("Saved results to", results_dir)


if __name__ == "__main__":
    main()
