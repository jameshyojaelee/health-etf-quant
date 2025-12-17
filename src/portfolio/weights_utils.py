"""Helper functions to transform signals into portfolio weights.

These utilities are intentionally small and focused: alignment, forward-fill, and
basic leverage capping.
"""

from __future__ import annotations

import pandas as pd


def extend_to_universe(weights: pd.DataFrame, universe: list[str]) -> pd.DataFrame:
    """Ensure weights cover the full universe, filling missing tickers with 0."""
    out = pd.DataFrame(0.0, index=weights.index, columns=list(universe))
    for col in weights.columns:
        if col in out.columns:
            out[col] = weights[col]
    return out


def forward_fill_to_index(weights: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Forward-fill weights onto a target index (typically daily prices)."""
    out = weights.reindex(index, method="ffill").fillna(0.0)
    out.index = pd.to_datetime(out.index)
    return out


def cap_gross_leverage(weights: pd.DataFrame, max_gross_leverage: float) -> pd.DataFrame:
    """Scale weights down on days where gross exposure exceeds `max_gross_leverage`."""
    if max_gross_leverage <= 0:
        raise ValueError("max_gross_leverage must be positive.")
    gross = weights.abs().sum(axis=1)
    over = gross > max_gross_leverage
    if not over.any():
        return weights
    scale = (max_gross_leverage / gross).where(over, 1.0)
    return weights.mul(scale, axis=0)
