"""H4 — 5-day (weekly) reversal / momentum (Lo-MacKinlay 1990).

Rebalance on the last trading day of each ISO calendar week (typically Friday,
or the last trading day of the week on Friday holidays).

    signal at rebalance t  = cumulative return over the 5 trading days ending t
    ret_fwd at rebalance t = cumulative return over the next 5 trading days
                             (i.e., to the next weekly rebalance; non-overlapping)

For short weeks (e.g., Thanksgiving, Christmas) the window is whatever trading
days are actually present; we do not pad to 5.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ._common import (
    apply_pit_filter,
    load_daily_returns,
    log_panel_stats,
    pick_week_end_dates,
)

OUT = Path(__file__).resolve().parents[2] / "data" / "interim" / "h4_panel.parquet"


def build() -> pd.DataFrame:
    d = load_daily_returns()
    d["log_r"] = np.log1p(d["ret"])
    d["log_wealth"] = d.groupby("ticker", sort=False)["log_r"].cumsum()

    reb = pick_week_end_dates(d["date"])
    reb_set = set(reb)

    sub = d[d["date"].isin(reb_set)].copy()
    # signal = cumret over the 5 trading days ending at t (= log_wealth[t] - log_wealth[t-5d])
    sub["log_wealth_prev"] = (
        sub.groupby("ticker", sort=False)["log_wealth"].shift(1)
    )
    sub["signal"] = np.expm1(sub["log_wealth"] - sub["log_wealth_prev"])
    # ret_fwd = cumret to next weekly rebalance
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
    log_panel_stats("H4", panel)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
