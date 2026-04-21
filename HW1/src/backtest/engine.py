"""Horizon-agnostic backtest engine.

`run_horizon` consumes a long-format panel and emits a per-rebalance P&L frame
for both MOM and REV. It is called six times with six (cost_bps, target)
combinations from `src/cli/run_all.py`.

Contract:
    input panel columns: [date, ticker, signal, ret_fwd, ...]
    output frame index : date (one row per rebalance)
    output columns     : mom_gross, mom_net, rev_gross, rev_net, turnover
"""
from __future__ import annotations

import pandas as pd

from .costs import cost_drag, turnover
from .portfolio import terciles_longshort


def run_horizon(
    panel: pd.DataFrame,
    cost_bps: float = 1.5,
    target: str = "ret_fwd",
    signal_col: str = "signal",
    round_trip_each_rebalance: bool = False,
) -> pd.DataFrame:
    """Apply the tercile long-short to every date in the panel.

    Parameters
    ----------
    round_trip_each_rebalance
        When True, turnover is forced to ``2 × gross_leverage`` (= 2.0 on a
        dollar-neutral gross=1 portfolio) on every rebalance. This models
        intraday horizons that enter at open and fully unwind at close (H2):
        each "day" we pay both an entry and an exit, independent of whether
        yesterday's ranks agreed with today's. When False (default), turnover
        is ``|w_t - w_{t-1}|`` and holds carry across rebalances (H3–H6).
    """
    p = terciles_longshort(panel, signal_col=signal_col)

    gross = (
        p.assign(
            _m=p["w_mom"] * p[target],
            _r=p["w_rev"] * p[target],
        )
        .groupby("date", as_index=True)[["_m", "_r"]]
        .sum()
        .rename(columns={"_m": "mom_gross", "_r": "rev_gross"})
    )

    w_wide = (
        p.pivot_table(index="date", columns="ticker", values="w_mom", aggfunc="sum")
        .sort_index()
    )
    if round_trip_each_rebalance:
        gross_leverage = w_wide.abs().sum(axis=1)
        turn = 2.0 * gross_leverage
        cost = turn * (cost_bps / 1e4)
    else:
        turn = turnover(w_wide)
        cost = cost_drag(w_wide, cost_bps)

    # Align and assemble
    out = gross.join(turn.rename("turnover"), how="inner")
    out["mom_net"] = out["mom_gross"] - cost.reindex(out.index)
    out["rev_net"] = out["rev_gross"] - cost.reindex(out.index)
    return out[["mom_gross", "mom_net", "rev_gross", "rev_net", "turnover"]]


if __name__ == "__main__":  # smoke test
    import numpy as np

    rng = np.random.default_rng(1)
    n_dates, n_names = 100, 30
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    tickers = [f"T{i:02d}" for i in range(n_names)]
    rows = []
    for d in dates:
        for t in tickers:
            s = rng.normal()
            # forward return is weakly anti-correlated with signal -> REV should earn
            rows.append({"date": d, "ticker": t, "signal": s,
                         "ret_fwd": -0.05 * s + rng.normal() * 0.02})
    panel = pd.DataFrame(rows)

    pnl = run_horizon(panel, cost_bps=1.5)

    # MOM gross + REV gross == 0 exactly (mirror invariant)
    assert (pnl["mom_gross"] + pnl["rev_gross"]).abs().max() < 1e-12, "mirror broken"
    # Turnover in [0, 2]
    assert pnl["turnover"].between(0, 2).all(), "turnover out of range"
    # Sanity: REV mean > MOM mean when signal anti-predicts
    assert pnl["rev_net"].mean() > pnl["mom_net"].mean(), "REV should win here"

    print(pnl.head().to_string())
    print(f"\nengine.py smoke test pass: {len(pnl)} rebalances, "
          f"REV net mean={pnl['rev_net'].mean():.5f}, "
          f"MOM net mean={pnl['mom_net'].mean():.5f}")
