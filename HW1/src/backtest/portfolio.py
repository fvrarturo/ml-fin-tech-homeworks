"""Tercile long-short portfolio construction.

`terciles_longshort` is the single portfolio primitive shared across all six
horizons. Per-date tercile weights are dollar-neutral and equal-weighted within
each leg; MOM and REV are exact mirrors so one call produces both.

Contract (Work1.md §5.2):
    input:   df with columns [date, ticker, <signal_col>, ret_fwd, ...]
    output:  same df + columns [rk, q, w_mom, w_rev]

Invariants (per date, full universe present):
    sum(w_mom) == 0            # dollar-neutral
    sum(|w_mom|) == 1          # gross leverage = 1
    sum(w_mom * w_rev) == -sum(w_mom**2)  # exact mirror

Degraded-universe behavior: if a date has fewer than 3 names, the middle tercile
collapses and the long/short legs may be unequal; we still produce well-defined
weights that sum to zero by normalizing each leg to |0.5|.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def terciles_longshort(
    df: pd.DataFrame,
    signal_col: str = "signal",
    date_col: str = "date",
) -> pd.DataFrame:
    """Assign dollar-neutral, equal-weight tercile weights per `date_col`.

    Rank ties are broken by `first` (stable across pandas versions). The bottom
    third (smallest signal) is the long leg for REV and the short leg for MOM.
    """
    out = df.copy()

    out["rk"] = out.groupby(date_col)[signal_col].rank(method="first")
    n_per_date = out.groupby(date_col)["rk"].transform("size")

    rel = (out["rk"] - 1) / n_per_date  # in [0, 1)
    out["q"] = pd.Categorical(
        np.where(rel < 1 / 3, "lo",
                 np.where(rel >= 2 / 3, "hi", "mi")),
        categories=["lo", "mi", "hi"],
    )

    leg_size = out.groupby([date_col, "q"], observed=True)["rk"].transform("size")
    raw = np.where(out["q"] == "hi", 1.0, np.where(out["q"] == "lo", -1.0, 0.0))
    # Equal weight within each leg, scaled to 0.5 so that sum|w| = 1 (gross = 1).
    w_mom = np.where(leg_size > 0, raw * 0.5 / leg_size.where(leg_size > 0, 1), 0.0)

    out["w_mom"] = w_mom
    out["w_rev"] = -w_mom
    return out


if __name__ == "__main__":  # quick unit tests
    rng = np.random.default_rng(0)
    n_dates, n_names = 5, 30
    dates = pd.date_range("2020-01-01", periods=n_dates)
    tickers = [f"T{i:02d}" for i in range(n_names)]
    rows = []
    for d in dates:
        for t in tickers:
            rows.append({"date": d, "ticker": t, "signal": rng.normal(), "ret_fwd": rng.normal()})
    df = pd.DataFrame(rows)

    out = terciles_longshort(df)

    for d, g in out.groupby("date"):
        s = g["w_mom"].sum()
        a = g["w_mom"].abs().sum()
        assert abs(s) < 1e-12, f"{d}: not dollar-neutral ({s})"
        assert abs(a - 1.0) < 1e-12, f"{d}: gross leverage {a:.6f} != 1"
        assert np.allclose(g["w_mom"], -g["w_rev"]), f"{d}: MOM/REV not mirrors"
        # counts in each tercile: 10/10/10
        counts = g["q"].value_counts().to_dict()
        assert counts == {"lo": 10, "mi": 10, "hi": 10}, f"{d}: tercile sizes {counts}"

    print(f"portfolio.py unit tests pass: {n_dates} dates × {n_names} names")
