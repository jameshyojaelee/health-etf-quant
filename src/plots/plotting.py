"""Plotting helpers built on matplotlib.

These helpers keep notebooks/scripts lightweight and make it easy to reuse a
consistent chart style across the repo.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def compute_drawdown(equity_curve: pd.Series) -> pd.Series:
    """Compute drawdown series from an equity curve."""
    if equity_curve.empty:
        return pd.Series(dtype=float)
    running_max = equity_curve.cummax()
    dd = equity_curve / running_max - 1.0
    dd.name = "drawdown"
    return dd


def plot_equity_curves(
    curves: pd.DataFrame,
    *,
    title: str = "Equity Curves",
    ylabel: str = "Cumulative Wealth",
    figsize: tuple[int, int] = (10, 6),
    out_path: str | Path | None = None,
) -> plt.Axes:
    """Plot one or more equity curves and optionally save to disk."""
    ax = curves.plot(figsize=figsize, title=title)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path)
        plt.close()
    return ax


def plot_drawdown(
    equity_curve: pd.Series,
    *,
    title: str = "Drawdown",
    figsize: tuple[int, int] = (10, 3),
    out_path: str | Path | None = None,
) -> plt.Axes:
    """Plot drawdowns from an equity curve and optionally save to disk."""
    dd = compute_drawdown(equity_curve)
    ax = dd.plot(figsize=figsize, title=title, color="tab:red")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path)
        plt.close()
    return ax
