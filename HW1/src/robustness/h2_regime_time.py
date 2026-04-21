"""Time-series and regime stability of H2 REV.

Two cuts:

    C1. Year-by-year. For each calendar year 2016..2025, report annualized
        return, vol, Sharpe, t-stat, MDD, and hit rate of REV-net daily
        P&L. A real effect persists across most years; a regime artifact
        concentrates in one or two.

    C2. VIX quintile. Rank each H2 rebalance date by the prior-close VIX
        (CBOE VIXCLS), split into quintiles Q1 (calm) → Q5 (crisis),
        report per-quintile Sharpe and hit rate. A real intraday-mean-
        reversion effect should exist in every regime, not only crisis.

Uses the prior-trading-day VIX close as the regime indicator (available at
the time the H2 signal is generated).

Outputs:
    data/processed/robustness/h2_by_year.csv
    data/processed/robustness/h2_by_vix_quintile.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import run_horizon

ROOT = Path(__file__).resolve().parents[2]
H2_PANEL = ROOT / "data" / "interim" / "h2_panel.parquet"
VIX = ROOT / "data" / "reference" / "VIXCLS.csv"
OUT_YEAR = ROOT / "data" / "processed" / "robustness" / "h2_by_year.csv"
OUT_VIX = ROOT / "data" / "processed" / "robustness" / "h2_by_vix_quintile.csv"


def _stats(x: pd.Series, periods_per_year: int = 252) -> dict:
    x = x.dropna().astype(float)
    n = len(x)
    if n < 2:
        return {"n": n, "ann_ret": np.nan, "ann_vol": np.nan,
                "sharpe": np.nan, "t": np.nan, "hit_rate": np.nan,
                "max_dd": np.nan}
    mu, sd = x.mean(), x.std(ddof=1)
    return {
        "n": n,
        "ann_ret": mu * periods_per_year,
        "ann_vol": sd * np.sqrt(periods_per_year),
        "sharpe": np.sqrt(periods_per_year) * mu / sd if sd > 0 else np.nan,
        "t": np.sqrt(n) * mu / sd if sd > 0 else np.nan,
        "hit_rate": (x > 0).mean(),
        "max_dd": float(((1 + x).cumprod() /
                         (1 + x).cumprod().cummax() - 1).min()),
    }


def by_year(pnl: pd.DataFrame) -> pd.DataFrame:
    rev = pnl["rev_net"].copy()
    rev.index = pd.to_datetime(rev.index)
    rows = []
    for y, series in rev.groupby(rev.index.year):
        s = _stats(series)
        s["year"] = int(y)
        rows.append(s)
    df = pd.DataFrame(rows).set_index("year")
    return df[["n", "ann_ret", "ann_vol", "sharpe", "t", "hit_rate", "max_dd"]]


def by_vix_quintile(pnl: pd.DataFrame) -> pd.DataFrame:
    rev = pnl["rev_net"].copy()
    rev.index = pd.to_datetime(rev.index)

    vix = pd.read_csv(VIX, parse_dates=["observation_date"])
    vix = vix.rename(columns={"observation_date": "date", "VIXCLS": "vix"})
    vix = vix.set_index("date").sort_index()

    # Use the *previous* trading-day close VIX — knowable at signal time.
    # Align via reindex(ffill) to the H2 rebalance dates minus one session.
    prev_close = vix.shift(1)
    aligned = prev_close.reindex(rev.index, method="ffill")["vix"]

    df = pd.DataFrame({"rev_net": rev.values, "vix_prev": aligned.values},
                       index=rev.index).dropna()
    df["quintile"] = pd.qcut(df["vix_prev"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])

    rows = []
    for q, sub in df.groupby("quintile", observed=True):
        s = _stats(sub["rev_net"])
        s["quintile"] = q
        s["vix_low"] = float(sub["vix_prev"].min())
        s["vix_high"] = float(sub["vix_prev"].max())
        s["vix_median"] = float(sub["vix_prev"].median())
        rows.append(s)
    out = pd.DataFrame(rows).set_index("quintile")
    return out[["n", "vix_low", "vix_median", "vix_high",
                "ann_ret", "ann_vol", "sharpe", "t", "hit_rate", "max_dd"]]


def _fmt(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for c in ("ann_ret", "ann_vol", "hit_rate", "max_dd"):
        if c in d.columns:
            d[c] = d[c].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else "")
    for c in ("sharpe", "t"):
        if c in d.columns:
            d[c] = d[c].apply(lambda x: f"{x:+.3f}" if pd.notna(x) else "")
    for c in ("vix_low", "vix_median", "vix_high"):
        if c in d.columns:
            d[c] = d[c].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "")
    return d


def main() -> None:
    panel = pd.read_parquet(H2_PANEL)
    pnl = run_horizon(panel, cost_bps=1.5, round_trip_each_rebalance=True)

    year_df = by_year(pnl)
    vix_df = by_vix_quintile(pnl)

    OUT_YEAR.parent.mkdir(parents=True, exist_ok=True)
    year_df.round(6).to_csv(OUT_YEAR)
    vix_df.round(6).to_csv(OUT_VIX)

    print("C1 — year-by-year H2 REV (net of 1.5 bps/side round-trip):")
    print(_fmt(year_df).to_string())
    # "Always positive?" test
    n_pos = (year_df["sharpe"] > 0).sum()
    n_sig = (year_df["t"] > 1.96).sum()
    print(f"\n  → {n_pos}/{len(year_df)} years had positive Sharpe.")
    print(f"  → {n_sig}/{len(year_df)} years had t > 1.96 within-year.")
    print()

    print("C2 — VIX-quintile partition (Q1 = calm, Q5 = crisis):")
    print(_fmt(vix_df).to_string())
    n_pos_q = (vix_df["sharpe"] > 0).sum()
    print(f"\n  → {n_pos_q}/5 VIX regimes had positive Sharpe.")
    print()

    print(f"wrote {OUT_YEAR.relative_to(ROOT)}")
    print(f"wrote {OUT_VIX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
