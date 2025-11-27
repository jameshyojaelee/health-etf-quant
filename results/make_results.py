"""Generate summary CSV and plots for healthcare strategies."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.data.etf_loader import load_clean_prices
from src.backtest.engine import run_backtest
from run_strategies import (
    run_rotation_strategy,
    summarize,
)
from src.data.macro_loader import load_tnx_10y, load_vix
from src.signals.regime import compute_monthly_features, classify_regime
from src.signals.ls_biotech_pharma import compute_spread_momentum, build_monthly_ls_weights
from src.portfolio.vol_target import estimate_rolling_vol


def main() -> None:
    results_dir = Path(__file__).resolve().parent
    prices = load_clean_prices().dropna(how="any")

    # Build regime LS with current macro and spread momentum/vol
    price_slice = prices[["XBI", "XPH", "SPY"]].dropna()
    tnx = load_tnx_10y(start=price_slice.index.min().strftime("%Y-%m-%d"), end=price_slice.index.max().strftime("%Y-%m-%d")).reindex(price_slice.index).ffill()
    vix = load_vix(start=price_slice.index.min().strftime("%Y-%m-%d"), end=price_slice.index.max().strftime("%Y-%m-%d")).reindex(price_slice.index).ffill()
    features = compute_monthly_features(tnx, price_slice["SPY"], vix)
    regimes = classify_regime(features)
    spread_mom = compute_spread_momentum(price_slice[["XBI", "XPH"]], lookback_months=6)
    vol_df = estimate_rolling_vol(price_slice[["XBI", "XPH"]].pct_change().fillna(0.0))
    ls_weights = build_monthly_ls_weights(
        regime_labels=regimes,
        prices=price_slice[["XBI", "XPH"]],
        vol_df=vol_df,
        spread_momentum=spread_mom,
        target_gross_exposure=1.0,
        spread_mom_threshold=0.0,
    )
    from src.backtest.engine import run_backtest
    regime_bt = run_backtest(price_slice[["XBI", "XPH"]], ls_weights, transaction_cost_bps=10.0)

    rotation_bt = run_rotation_strategy(prices, tc_bps=10.0)

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
        ew_bt = run_backtest(prices[hc_cols], ew_daily, transaction_cost_bps=10.0)
        bench.append(summarize("Equal-Weight HC", ew_bt.daily_returns, ew_bt.equity_curve))
        ew_equity = ew_bt.equity_curve.rename("Equal-Weight HC")
    else:
        ew_equity = None

    summary_df = pd.DataFrame(summaries + bench)
    summary_df.to_csv(results_dir / "strategy_summary.csv", index=False)

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

    metrics_plot = summary_df.set_index("name")[["cagr", "sharpe"]]
    metrics_plot.plot(kind="bar", figsize=(10, 6), title="CAGR and Sharpe")
    plt.ylabel("Value")
    plt.tight_layout()
    plt.savefig(results_dir / "metrics_bar.png")
    plt.close()

    print("Saved results to", results_dir)


if __name__ == "__main__":
    main()
