"""H6 — 6-month (126-day) Jegadeesh-Titman momentum with 1-month skip.

Rebalance on the last trading day of each calendar month (same cadence as H5)
but with a 126-day forward hold; consecutive forwards overlap by 105 days.

    signal at rebalance t  = prod_{k=t-125}^{t-21}(1+r_k) - 1
                             (5-month window ending 1 month ago; skip-1-month
                              JT convention, decouples from H5 reversal)
    ret_fwd at rebalance t = prod_{k=t+1}^{t+126}(1+r_k) - 1

The overlap requires Newey-West HAC standard errors with q=6 on the downstream
t-stat (Work1.md §6.6, §13.4). The engine produces raw P&L; the NW correction
happens in src/backtest/metrics.py and is surfaced in the per-horizon stats row.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ._common import (
    apply_pit_filter,
    load_daily_returns,
    log_panel_stats,
    pick_month_end_dates,
)

OUT = Path(__file__).resolve().parents[2] / "data" / "interim" / "h6_panel.parquet"

LOOKBACK_DAYS = 126   # look-back horizon
SKIP_DAYS = 21        # JT skip-1-month
FWD_DAYS = 126        # forward hold


def build() -> pd.DataFrame:
    d = load_daily_returns()
    d["log_r"] = np.log1p(d["ret"])
    d["log_wealth"] = d.groupby("ticker", sort=False)["log_r"].cumsum()

    # Per-ticker offset lookups (trading-day indexed, via shift on sorted panel).
    g = d.groupby("ticker", sort=False)["log_wealth"]
    lw_skip_end = g.shift(SKIP_DAYS)                        # log_wealth at t-21
    lw_skip_start = g.shift(LOOKBACK_DAYS)                  # log_wealth at t-126
    lw_fwd = g.shift(-FWD_DAYS)                             # log_wealth at t+126

    d["signal"] = np.expm1(lw_skip_end - lw_skip_start)     # 105-day skip-past return
    d["ret_fwd"] = np.expm1(lw_fwd - d["log_wealth"])       # 126-day forward

    reb = pick_month_end_dates(d["date"])
    sub = d[d["date"].isin(set(reb))].copy()
    sub = sub.dropna(subset=["signal", "ret_fwd"])

    # Long lookback (126d) on a rotating universe: every ticker transition
    # creates 6 months of 29-name rebalance dates until the new ticker has
    # enough history. Expected upper bound across 2016-2025 events: ~24 such
    # months. Tolerance raised accordingly.
    out = apply_pit_filter(
        sub[["date", "ticker", "signal", "ret_fwd"]],
        strict=True,
        max_short_days=30,
    )
    return out[["date", "ticker", "signal", "ret_fwd"]].reset_index(drop=True)


def main() -> None:
    panel = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT, index=False)
    log_panel_stats("H6", panel)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
