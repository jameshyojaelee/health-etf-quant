"""Plotting helpers built on matplotlib.

These helpers keep notebooks/scripts lightweight and make it easy to reuse a
consistent chart style across the repo.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def compute_drawdown(equity_curve: pd.Series) -> pd.Series:
    """Compute drawdown series from an equity curve."""
    if equity_curve.empty:
        return pd.Series(dtype=float)
    running_max = equity_curve.cummax()
    dd = equity_curve / running_max - 1.0
    dd.name = "drawdown"
    return dd


def add_episode_shading(
    ax: plt.Axes,
    episodes: list[tuple[str, str, str]] | None,
    *,
    color: str = "0.85",
    alpha: float = 0.5,
) -> None:
    """Optionally shade event windows on an axis.

    Episodes are tuples of (start_date, end_date, label). Dates can be any
    pandas-parseable string, e.g. "2008-09-01".
    """
    if not episodes:
        return
    ymin, ymax = ax.get_ylim()
    for start, end, label in episodes:
        s = pd.to_datetime(start)
        e = pd.to_datetime(end)
        ax.axvspan(s, e, color=color, alpha=alpha, linewidth=0)
        if label:
            mid = s + (e - s) / 2
            ax.text(mid, ymax, label, ha="center", va="bottom", fontsize=8, color="0.35")
    ax.set_ylim(ymin, ymax)


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
    episodes: list[tuple[str, str, str]] | None = None,
) -> plt.Axes:
    """Plot drawdowns from an equity curve and optionally save to disk."""
    dd = compute_drawdown(equity_curve)
    ax = dd.plot(figsize=figsize, title=title, color="tab:red")
    ax.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    add_episode_shading(ax, episodes)
    plt.tight_layout()

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path)
        plt.close()
    return ax


def plot_drawdowns_panel(
    curves: pd.DataFrame,
    *,
    title: str = "Drawdowns",
    figsize: tuple[int, int] = (10, 8),
    out_path: str | Path | None = None,
    episodes: list[tuple[str, str, str]] | None = None,
) -> plt.Figure:
    """Plot drawdowns for each curve on separate subplots."""
    cols = list(curves.columns)
    fig, axes = plt.subplots(len(cols), 1, figsize=figsize, sharex=True)
    if len(cols) == 1:
        axes = [axes]
    for ax, col in zip(axes, cols):
        dd = compute_drawdown(curves[col].dropna())
        ax.plot(dd.index, dd.values, color="tab:red", linewidth=1.0)
        ax.set_ylabel(col)
        ax.grid(True, alpha=0.3)
        add_episode_shading(ax, episodes)
    fig.suptitle(title)
    plt.tight_layout()

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path)
        plt.close(fig)
    return fig


def plot_weights_heatmap(
    weights: pd.DataFrame,
    *,
    title: str = "Weights Heatmap",
    freq: str = "ME",
    figsize: tuple[int, int] = (12, 4),
    out_path: str | Path | None = None,
    cmap: str = "RdBu_r",
) -> plt.Axes:
    """Plot a resampled weights heatmap (tickers x time)."""
    if weights.empty:
        raise ValueError("weights is empty")

    monthly = weights.resample(freq).last().fillna(0.0)
    monthly = monthly.loc[:, (monthly.abs().sum(axis=0) > 0)]
    if monthly.empty:
        monthly = weights.resample(freq).last().fillna(0.0)

    tickers = list(monthly.columns)
    dates = list(monthly.index)
    data = monthly.T.values

    vmax = float(np.nanmax(np.abs(data))) if data.size else 1.0
    vmax = max(vmax, 1e-6)

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(data, aspect="auto", interpolation="nearest", cmap=cmap, vmin=-vmax, vmax=vmax)
    ax.set_title(title)
    ax.set_yticks(range(len(tickers)))
    ax.set_yticklabels(tickers)

    # Avoid unreadable x labels; sample roughly ~10 ticks.
    step = max(1, len(dates) // 10)
    xticks = list(range(0, len(dates), step))
    ax.set_xticks(xticks)
    ax.set_xticklabels([pd.to_datetime(dates[i]).strftime("%Y-%m") for i in xticks], rotation=45, ha="right")

    plt.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    plt.tight_layout()

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path)
        plt.close(fig)
    return ax
