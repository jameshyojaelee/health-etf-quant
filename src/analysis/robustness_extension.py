"""Extended robustness helpers for in/out-of-sample checks and parameter sweeps."""

from __future__ import annotations

import itertools
from typing import List, Tuple, Optional

import pandas as pd

from src.analysis.metrics import (
    compute_annual_vol,
    compute_cagr,
    compute_max_drawdown,
    compute_sharpe,
)
from src.backtest.engine import run_backtest
from src.portfolio.vol_target import estimate_rolling_vol
from src.signals.rotation_signals import build_monthly_rotation_weights
from src.signals.ls_biotech_pharma import build_monthly_ls_weights


def split_periods(returns: pd.Series, split_date: str = "2015-01-01") -> Tuple[pd.Series, pd.Series]:
    """Split a return series into in-sample and out-of-sample segments."""
    in_sample = returns.loc[returns.index < split_date]
    out_sample = returns.loc[returns.index >= split_date]
    return in_sample, out_sample


def summarize_strategy_over_periods(
    daily_returns: pd.Series,
    split_date: str = "2015-01-01",
) -> pd.DataFrame:
    """Compute metrics over full, in-sample, and out-of-sample periods."""
    in_sample, out_sample = split_periods(daily_returns, split_date)

    def _metrics(series: pd.Series) -> dict[str, float]:
        return {
            "cagr": compute_cagr(series),
            "vol": compute_annual_vol(series),
            "sharpe": compute_sharpe(series),
            "max_dd": compute_max_drawdown((1 + series.fillna(0)).cumprod()),
        }

    data = {
        "full": _metrics(daily_returns),
        "in_sample": _metrics(in_sample),
        "out_sample": _metrics(out_sample),
    }
    return pd.DataFrame(data).T[["cagr", "vol", "sharpe", "max_dd"]]


def sweep_rotation_parameters(
    prices: pd.DataFrame,
    lookbacks: List[int],
    top_ks: List[int],
    use_ts_flags: List[bool],
    use_12m1m_flags: List[bool],
    use_xlv_filters: List[bool],
    ts_lookbacks: List[int],
    target_vols: List[float],
    max_gross_list: List[float],
    transaction_cost_bps: float = 10.0,
    split_date: str = "2015-01-01",
) -> pd.DataFrame:
    """Grid search rotation parameters and report Sharpe (full/in/out)."""
    results = []
    for lb, k, use_ts, use_12, use_xlv, ts_lb, tv, mg in itertools.product(
        lookbacks, top_ks, use_ts_flags, use_12m1m_flags, use_xlv_filters, ts_lookbacks, target_vols, max_gross_list
    ):
        weights = build_monthly_rotation_weights(
            prices,
            lookback_months=lb,
            top_k=k,
            use_ts_mom_gating=use_ts,
            use_12m1m=use_12,
            use_xlv_trend_filter=use_xlv,
            ts_lookback_months=ts_lb,
            target_vol_annual=tv,
            max_gross_leverage=mg,
        )
        bt = run_backtest(prices, weights, transaction_cost_bps=transaction_cost_bps)
        in_sample, out_sample = split_periods(bt.daily_returns, split_date)
        results.append(
            {
                "lookback": lb,
                "top_k": k,
                "use_ts": use_ts,
                "use_12m1m": use_12,
                "use_xlv_filter": use_xlv,
                "ts_lookback": ts_lb,
                "target_vol": tv,
                "max_gross": mg,
                "sharpe_full": compute_sharpe(bt.daily_returns),
                "sharpe_in": compute_sharpe(in_sample),
                "sharpe_out": compute_sharpe(out_sample),
            }
        )
    return pd.DataFrame(results)


def sweep_regime_ls_parameters(
    prices: pd.DataFrame,
    vol_df: pd.DataFrame,
    regime_labels: pd.Series,
    spread_momentum: pd.Series,
    spread_mom_thresholds: List[float],
    target_gross_list: List[float],
    monthly_features: Optional[pd.DataFrame] = None,
    rate_thresholds: Optional[List[float]] = None,
    vix_thresholds: Optional[List[float]] = None,
    spy_ret_thresholds: Optional[List[float]] = None,
    transaction_cost_bps: float = 10.0,
    split_date: str = "2015-01-01",
) -> pd.DataFrame:
    """Grid search regime LS parameters and report Sharpe (full/in/out)."""
    results = []
    macro_grid = list(
        itertools.product(
            rate_thresholds or [None],
            vix_thresholds or [None],
            spy_ret_thresholds or [None],
        )
    )
    from src.signals.regime import classify_regime

    for sm_th, tg, (rt, vt, st) in itertools.product(spread_mom_thresholds, target_gross_list, macro_grid):
        if monthly_features is not None and (rt is not None or vt is not None or st is not None):
            regimes = classify_regime(
                monthly_features,
                rate_threshold=rt if rt is not None else -0.5,
                vix_threshold=vt if vt is not None else 25.0,
                spy_ret_threshold=st if st is not None else 0.0,
            )
        else:
            regimes = regime_labels
        weights = build_monthly_ls_weights(
            regime_labels=regimes,
            prices=prices[["XBI", "XPH"]],
            vol_df=vol_df,
            spread_momentum=spread_momentum,
            target_gross_exposure=tg,
            spread_mom_threshold=sm_th,
        )
        bt = run_backtest(prices[["XBI", "XPH"]], weights, transaction_cost_bps=transaction_cost_bps)
        in_sample, out_sample = split_periods(bt.daily_returns, split_date)
        results.append(
            {
                "spread_mom_th": sm_th,
                "target_gross": tg,
                "rate_th": rt,
                "vix_th": vt,
                "spy_th": st,
                "sharpe_full": compute_sharpe(bt.daily_returns),
                "sharpe_in": compute_sharpe(in_sample),
                "sharpe_out": compute_sharpe(out_sample),
            }
        )
    return pd.DataFrame(results)
