"""H5 — 21-day (monthly) reversal (Jegadeesh 1990).

Rebalance on the last trading day of each calendar month.

    signal at rebalance t  = cumret over the trading days ending t back to the
                             prior month-end rebalance (~21 trading days)
    ret_fwd at rebalance t = cumret to the next month-end rebalance
                             (non-overlapping monthly holding)

Using exact month-to-month cumulative returns rather than a fixed 21-day window
keeps the non-overlapping invariant even across months with 19–23 trading days.
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

OUT = Path(__file__).resolve().parents[2] / "data" / "interim" / "h5_panel.parquet"


def build() -> pd.DataFrame:
    d = load_daily_returns()
    d["log_r"] = np.log1p(d["ret"])
    d["log_wealth"] = d.groupby("ticker", sort=False)["log_r"].cumsum()

    reb = pick_month_end_dates(d["date"])
    reb_set = set(reb)

    sub = d[d["date"].isin(reb_set)].copy()
    sub["log_wealth_prev"] = (
        sub.groupby("ticker", sort=False)["log_wealth"].shift(1)
    )
    sub["signal"] = np.expm1(sub["log_wealth"] - sub["log_wealth_prev"])
    sub["log_wealth_next"] = (
        sub.groupby("ticker", sort=False)["log_wealth"].shift(-1)
    )
    sub["ret_fwd"] = np.expm1(sub["log_wealth_next"] - sub["log_wealth"])

    sub = sub.dropna(subset=["signal", "ret_fwd"])
    out = apply_pit_filter(sub[["date", "ticker", "signal", "ret_fwd"]], strict=True)
    return out[["date", "ticker", "signal", "ret_fwd"]].reset_index(drop=True)


def main() -> None:
    panel = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT, index=False)
    log_panel_stats("H5", panel)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
