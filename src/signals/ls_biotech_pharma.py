"""Biotech vs pharma long-short signal construction."""

from __future__ import annotations

import pandas as pd


def build_monthly_ls_weights(
    regime_labels: pd.Series,
    dates: pd.DatetimeIndex,
    tickers_ls: list[str] | None = None,
) -> pd.DataFrame:
    """Map monthly regime labels to daily long-short weights for biotech/pharma.

    Risk-on: long XBI (+1), short XPH (-1).
    Risk-off: flat (0 weights) for now (alternative could be long-only XPH).
    """
    tickers = tickers_ls or ["XBI", "XPH"]
    if set(tickers) != {"XBI", "XPH"}:
        raise ValueError("tickers_ls must include XBI and XPH.")

    monthly_weights = []
    for date, label in regime_labels.items():
        if label == 1:
            monthly_weights.append(pd.Series({"XBI": 1.0, "XPH": -1.0}, name=date))
        else:
            monthly_weights.append(pd.Series({"XBI": 0.0, "XPH": 0.0}, name=date))

    monthly_df = pd.DataFrame(monthly_weights)

    daily_weights = monthly_df.reindex(dates, method="ffill").fillna(0.0)
    daily_weights = daily_weights.reindex(columns=tickers, fill_value=0.0)
    return daily_weights


def extend_ls_weights_to_all_tickers(
    ls_weights: pd.DataFrame,
    all_tickers: list[str],
) -> pd.DataFrame:
    """Extend LS weights to full universe, filling missing tickers with zeros."""
    extended = pd.DataFrame(0.0, index=ls_weights.index, columns=all_tickers)
    for col in ["XBI", "XPH"]:
        if col in ls_weights.columns and col in extended.columns:
            extended[col] = ls_weights[col]
    return extended
