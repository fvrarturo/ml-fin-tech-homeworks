"""Per-side cost model (Work1.md §5.4).

A single function: given a date-indexed matrix of weights (columns = tickers)
and a per-side cost in bps, return a Series of per-rebalance cost drag.

    cost_{t+h} = c_h * sum_i |w_{i,t+h} - w_{i,t}|  (turnover × per-side bps)

We treat c_h as "per-side" bps — a 1.5 bps per side model charges 1.5 bps on
every dollar of weight change. On the first rebalance (no prior position) the
turnover equals the gross leverage (= 1), so the first-period cost is
c_h * gross_leverage.
"""
from __future__ import annotations

import pandas as pd


def turnover(weights_wide: pd.DataFrame) -> pd.Series:
    """Per-date L1 change in weights. First row = |w_0| = gross leverage."""
    w = weights_wide.fillna(0.0)
    diff = (w - w.shift(1)).abs().sum(axis=1)
    diff.iloc[0] = w.iloc[0].abs().sum()
    return diff


def cost_drag(weights_wide: pd.DataFrame, cost_bps: float) -> pd.Series:
    """Per-date cost as a return-scale fraction (e.g., 3.0 bps → 0.0003)."""
    return turnover(weights_wide) * (cost_bps / 1e4)
