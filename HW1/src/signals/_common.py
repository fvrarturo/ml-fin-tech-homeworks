"""Shared helpers for building horizon panels.

Four primitives the H3/H4/H5/H6 builders share:

    load_daily_returns()        → per-(ticker, date) total-return panel
    load_membership()           → PIT member-day long frame
    apply_pit_filter(panel)     → inner-join panel with membership
    rolling_cumret(...)         → vectorized log-sum cumulative return

Additionally:

    pick_month_end_dates(dates) → last trading day of each calendar month
    pick_week_end_dates(dates)  → last trading day of each ISO week

All return NumPy-backed float64 / datetime64[ns] / string columns.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "data" / "interim" / "daily.parquet"
MEMBER = ROOT / "data" / "reference" / "dj30_membership_long.csv"


def load_daily_returns() -> pd.DataFrame:
    """Return (date, ticker, ret, retx) sorted by (ticker, date)."""
    df = pd.read_parquet(DAILY)[["date", "ticker", "ret", "retx"]]
    df["ticker"] = df["ticker"].astype(str)
    return df.sort_values(["ticker", "date"]).reset_index(drop=True)


def load_membership() -> pd.DataFrame:
    """Return long-format membership (date, ticker)."""
    m = pd.read_csv(MEMBER, parse_dates=["date"])
    m["ticker"] = m["ticker"].astype(str)
    return m


def apply_pit_filter(
    panel: pd.DataFrame,
    strict: bool = True,
    max_short_days: int = 10,
) -> pd.DataFrame:
    """Inner-join `panel` with membership on (date, ticker).

    If `strict`, require that the fraction of rebalance dates with <30 names is
    bounded by `max_short_days`. This tolerance covers ticker-chain transition
    days (DD→DWDP, DWDP→DOW, UTX→RTX, XOM→CRM, etc.) where signal or forward
    returns can't be computed within ticker. Offending dates are printed.
    """
    m = load_membership()
    out = panel.merge(m, on=["date", "ticker"], how="inner")
    counts = out.groupby("date")["ticker"].nunique()
    short = counts[counts < 30]
    if len(short) > 0:
        print(f"  [apply_pit_filter] {len(short)} short rebalance date(s): "
              f"min={counts.min()}, mode={counts.mode().iloc[0]}")
        for dt, n in short.items():
            print(f"    {pd.Timestamp(dt).date()}  n={n}")
    if strict:
        assert len(short) <= max_short_days, (
            f"PIT broken: {len(short)} short days > tolerance {max_short_days}"
        )
    return out


def rolling_cumret(
    df: pd.DataFrame,
    window: int,
    shift: int = 0,
    group_col: str = "ticker",
    ret_col: str = "ret",
) -> pd.Series:
    """Per-group cumulative simple return over `window` trading days, optionally
    shifted `shift` positions (positive = shift backwards in time, so the window
    ends `shift` days earlier).

    At index `t`:
        shift=0   → return over [t-window+1, t]
        shift=s>0 → return over [t-window-s+1, t-s]
        shift<0   → return over [t+|shift|-window+1, t+|shift|] (look-ahead)

    Works on a long panel sorted by (group_col, date). Returns a Series aligned
    with the input index.
    """
    log_r = np.log1p(df[ret_col].to_numpy(dtype=float))
    s = pd.Series(log_r, index=df.index)
    grouped = s.groupby(df[group_col], sort=False)
    out = grouped.transform(lambda x: x.rolling(window).sum())
    if shift:
        out = out.groupby(df[group_col], sort=False).shift(shift)
    return np.expm1(out)


def forward_cumret(
    df: pd.DataFrame,
    window: int,
    group_col: str = "ticker",
    ret_col: str = "ret",
) -> pd.Series:
    """Per-group forward cumulative simple return over `window` days starting
    at `t+1`, i.e., at index t: prod_{k=1..window}(1+r_{t+k}) − 1.
    """
    log_r = np.log1p(df[ret_col].to_numpy(dtype=float))
    s = pd.Series(log_r, index=df.index)
    # roll forward: rolling-sum at position t+window is r[t+1]+...+r[t+window]
    grouped = s.groupby(df[group_col], sort=False)
    rolled = grouped.transform(lambda x: x.rolling(window).sum())
    # shift by -window so that position t holds the sum ending at t+window
    shifted = rolled.groupby(df[group_col], sort=False).shift(-window)
    return np.expm1(shifted)


def pick_month_end_dates(dates: pd.Series) -> pd.DatetimeIndex:
    """Last trading day of each calendar month in the input set."""
    d = pd.to_datetime(pd.Series(dates).unique())
    s = pd.Series(d).sort_values().reset_index(drop=True)
    ym = s.dt.to_period("M")
    last = s.groupby(ym).max()
    return pd.DatetimeIndex(last.values)


def pick_week_end_dates(dates: pd.Series) -> pd.DatetimeIndex:
    """Last trading day of each ISO calendar week (Friday, or Thursday on a
    Friday holiday, etc.)."""
    d = pd.to_datetime(pd.Series(dates).unique())
    s = pd.Series(d).sort_values().reset_index(drop=True)
    # ISO year-week grouping
    iso = s.dt.isocalendar()
    key = iso["year"].astype(str) + "-" + iso["week"].astype(str).str.zfill(2)
    last = s.groupby(key.values).max()
    return pd.DatetimeIndex(sorted(last.values))


def log_panel_stats(label: str, panel: pd.DataFrame) -> None:
    """One-line console summary of a built horizon panel."""
    counts = panel.groupby("date")["ticker"].nunique()
    print(
        f"{label}  rows={len(panel):,}  rebalances={panel['date'].nunique()}  "
        f"names/date: min={counts.min()}, max={counts.max()}, modal={counts.mode().iloc[0]}  "
        f"signal µ={panel['signal'].mean():+.5f}, σ={panel['signal'].std():.5f}  "
        f"ret_fwd µ={panel['ret_fwd'].mean():+.5f}, σ={panel['ret_fwd'].std():.5f}"
    )


if __name__ == "__main__":
    # Smoke: load & verify
    daily = load_daily_returns()
    members = load_membership()
    print(f"daily rows: {len(daily):,}, tickers: {daily['ticker'].nunique()}")
    print(f"members rows: {len(members):,}, dates: {members['date'].nunique()}")
    print(f"month-end dates: {len(pick_month_end_dates(daily['date']))}")
    print(f"week-end dates:  {len(pick_week_end_dates(daily['date']))}")

    # sanity on rolling_cumret: 1-day cumret = today's return
    s1 = rolling_cumret(daily, window=1)
    assert np.allclose(s1.dropna(), daily["ret"].loc[s1.dropna().index], atol=1e-12)
    print("rolling_cumret window=1 == ret ✓")
