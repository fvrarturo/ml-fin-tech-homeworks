"""H2 — intraday first-half-hour → rest-of-day (Gao, Han, Li & Zhou 2018).

Rebalance once per trading day, within the day. The signal and the forward
return are both intraday — no overnight gap, no carry of positions to the next
session.

    signal at date t = mid_after_open_{i,t} / OPrc_{i,t} - 1
        ^ proxy for the "first-30-minute" return (09:30 → ~10:00 ET).
          Note: `mid_after_open` in iid_ms is a ~5-minute VWAP mid immediately
          after the opening auction, not a 10:00 snapshot. Documented in
          data/REFERENCE_DATA.md §2.5 and data/interim/LOAD_NOTES.md.

    ret_fwd at date t = CPrc_{i,t} / mid_after_open_{i,t} - 1
        ^ "rest-of-day" return (10:00 → 16:00 ET).

We drop the 19 NYSE early-close days in the trimmed window (13:00 close on
Black Fridays, Christmas Eves, July 3s — Work1.md §6.2 Step 3 decision). On
those days the "rest of day" is compressed to a 3-hour window rather than
~6 hours, and the Gao mechanism (institutional rebalancing flows) is not
expected to operate identically.

Output: data/interim/h2_panel.parquet with [date, ticker, signal, ret_fwd].
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._common import apply_pit_filter, log_panel_stats

ROOT = Path(__file__).resolve().parents[2]
INTRA = ROOT / "data" / "interim" / "intraday.parquet"
EARLY = ROOT / "data" / "reference" / "nyse_early_closes.csv"
OUT = ROOT / "data" / "interim" / "h2_panel.parquet"


def build() -> pd.DataFrame:
    iid = pd.read_parquet(INTRA)[["date", "ticker", "open", "close",
                                  "mid_after_open"]]
    iid["ticker"] = iid["ticker"].astype(str)

    # Intraday returns — price-only (intraday dividends are negligible).
    iid["signal"] = iid["mid_after_open"] / iid["open"] - 1.0
    iid["ret_fwd"] = iid["close"] / iid["mid_after_open"] - 1.0

    # Drop early-close days.
    ec = pd.read_csv(EARLY, parse_dates=["date"])
    iid = iid[~iid["date"].isin(set(ec["date"]))].copy()

    iid = iid.dropna(subset=["signal", "ret_fwd"])

    # `mid_after_open` has systematic NaN patterns in the WRDS iid_ms feed
    # (up to 1.8% / year in 2020 and 2025). SHW has the worst coverage (254
    # rows missing), AMZN second (215). On those (date, ticker) pairs we can't
    # compute the first-30 signal, so the row drops out and the date has <30
    # names. This is a data quality issue in the vendor feed, not a ticker
    # transition. ~160 dates over the 2016-2025 window have 25-29 names
    # instead of 30. Tercile construction still works on n<30 universes
    # (sizes become e.g. 9/8/9 or 10/8/10).
    out = apply_pit_filter(
        iid[["date", "ticker", "signal", "ret_fwd"]],
        strict=True,
        max_short_days=250,
    )
    return out[["date", "ticker", "signal", "ret_fwd"]].reset_index(drop=True)


def main() -> None:
    panel = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT, index=False)
    log_panel_stats("H2", panel)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
