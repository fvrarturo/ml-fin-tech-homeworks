"""Consume TAQ 30-min bar parquets and produce the H1 signal panel.

Runs on the cluster after aggregation, but is pure-pandas so it can also
run locally on rsync'd bars.

    out/bars/year=YYYY/ticker=XXX.parquet      (from aggregate_bars.py)
        │
        ▼
    h1_panel.parquet  [datetime, ticker, signal, ret_fwd]

Signal construction (Work1.md §6.1 Step 2):
    Within (ticker, date): bar_k_logret = ln(close_k / close_{k-1})
    Signal at bar k      = prior-bar log-return (bar k-1)
    ret_fwd at bar k     = next-bar log-return (bar k+1)
    Drop rows where either is NaN (the first/last bar of each session).

Shifts are strictly within (ticker, date) so we never cross the overnight
gap or a ticker-change boundary.

PIT filter: membership is on calendar date, not bar-level — every bar on
date `d` uses the DJ30 member set for that date.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def build_panel(bars_dir: Path, members_path: Path) -> pd.DataFrame:
    """Load all partitioned ticker-year parquets, compute bar returns, shift
    into signal / ret_fwd, PIT-filter."""
    # Scan partitions: year=YYYY/ticker=XXX.parquet
    parts = sorted(bars_dir.glob("year=*/ticker=*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no bar parquets under {bars_dir}")

    frames = []
    for p in parts:
        # Extract ticker from the path to avoid re-reading it from inside
        tkr = p.stem.split("=", 1)[1]
        year = int(p.parent.name.split("=", 1)[1])
        df = pd.read_parquet(p)
        df["ticker"] = tkr
        df["_year"] = year
        frames.append(df)
    bars = pd.concat(frames, ignore_index=True)

    bars["date"] = pd.to_datetime(bars["date"])

    # Compose a unique within-session key for stable sort → shift.
    bars = bars.sort_values(["ticker", "date", "bar"]).reset_index(drop=True)
    # Build a per-(ticker, date) group id; shift inside that group only so we
    # never cross the overnight boundary.
    grp = bars.groupby(["ticker", "date"], sort=False)

    bars["log_close"] = np.log(bars["close"])
    bars["bar_logret"] = grp["log_close"].diff()                  # k vs k-1
    # Signal at bar k = ret_{k-1 → k}. With shift(0), bar_logret *is* that.
    # But Work1.md says "signal at bar k = previous-bar return". The "previous
    # bar return" means the return over bar k-1 itself (ret of bar k-1 = log_close_{k-1} - log_close_{k-2}),
    # which is grp.shift(1) of bar_logret.
    bars["signal"] = grp["bar_logret"].shift(1)
    # Forward return at bar k = ret_{k+1} = grp.shift(-1) of bar_logret.
    bars["ret_fwd"] = grp["bar_logret"].shift(-1)

    panel = bars.dropna(subset=["signal", "ret_fwd"]).copy()

    # Point-in-time membership filter.
    members = pd.read_csv(members_path, parse_dates=["date"])
    members["ticker"] = members["ticker"].astype(str)
    before = len(panel)
    panel = panel.merge(members, on=["date", "ticker"], how="inner")
    after = len(panel)
    print(f"  PIT filter kept {after:,} / {before:,} rows")

    # Compose a bar-level datetime for audit (optional; H3-like engines
    # use `date` and ignore the bar column since each row is its own
    # rebalance).
    # Bar k starts at 09:30 + 30·(k) minutes in the re-numbered scheme (k=1 ≡ 10:00).
    # For the backtest engine we need a unique rebalance index; use date+bar
    # as the rebalance date for H1.
    panel["rebalance"] = panel["date"] + pd.to_timedelta(30 * panel["bar"].astype(int), unit="m")

    # Engine contract: date, ticker, signal, ret_fwd.
    # We store `rebalance` as the date column so each bar is its own rebalance.
    out = panel.rename(columns={"date": "trading_date"})[
        ["rebalance", "ticker", "signal", "ret_fwd", "trading_date", "bar"]
    ].rename(columns={"rebalance": "date"})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars-dir", type=Path, required=True,
                    help="Root of partitioned bars — contains year=*/ticker=*.parquet")
    ap.add_argument("--members", type=Path, required=True,
                    help="dj30_membership_long.csv")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output h1_panel.parquet")
    ap.add_argument("--meta", type=Path, default=None)
    args = ap.parse_args()

    panel = build_panel(args.bars_dir, args.members)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(args.out, index=False)

    counts = panel.groupby("trading_date")["ticker"].nunique()
    meta = {
        "rows": int(len(panel)),
        "rebalances": int(panel["date"].nunique()),
        "trading_days": int(panel["trading_date"].nunique()),
        "tickers": int(panel["ticker"].nunique()),
        "names_per_day_min": int(counts.min()),
        "names_per_day_max": int(counts.max()),
        "names_per_day_modal": int(counts.mode().iloc[0]),
        "n_short_days": int((counts < 30).sum()),
    }
    if args.meta:
        args.meta.write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
