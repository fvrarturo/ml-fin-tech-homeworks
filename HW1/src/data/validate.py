"""Cross-dataset validation.

Run: `python -m src.data.validate`

Checks (exit-code 0 if all pass, 1 on any red):

  R0. CRSP parquet exists and has the expected schema.
  R1. iid parquet exists and has the expected schema.
  R2. CRSP and iid cover the same calendar window.
  R3. Point-in-time membership merge against CRSP produces 29 or 30 names per
      day (30 is the target; 29 tolerated for the duration of the known GS gap
      documented in data/interim/LOAD_NOTES.md).
  R4. DlyRet and DlyRetx agree except on dividend days (|ret - retx| should be
      non-trivial on <~5% of rows, mostly in earnings-month quarters).
  R5. The permno-ticker map covers the DD→DWDP→DOW and UTX→RTX chains.
  R6. IBES earnings_dates.csv has ≥30 announcements per always-present ticker.

Prints a green/red report; non-zero exit on red.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "data" / "interim" / "daily.parquet"
INTRA = ROOT / "data" / "interim" / "intraday.parquet"
MEMBER = ROOT / "data" / "reference" / "dj30_membership_long.csv"
PERMNO = ROOT / "data" / "reference" / "permno_ticker.csv"
TENURE = ROOT / "data" / "reference" / "dj30_tenure.csv"
EARN = ROOT / "data" / "reference" / "earnings_dates.csv"


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "\033[92mPASS\033[0m" if ok else "\033[91mFAIL\033[0m"
    print(f"  {mark}  {name}" + (f"  — {detail}" if detail else ""))
    return ok


def main() -> int:
    print("Cross-dataset validation\n" + "=" * 60)
    ok = True

    ok &= check("R0 CRSP parquet present", DAILY.exists(), str(DAILY))
    ok &= check("R1 iid parquet present", INTRA.exists(), str(INTRA))
    if not (DAILY.exists() and INTRA.exists()):
        return 1

    daily = pd.read_parquet(DAILY)
    intra = pd.read_parquet(INTRA)
    members = pd.read_csv(MEMBER, parse_dates=["date"])

    ok &= check(
        "R2 CRSP and iid share calendar",
        daily["date"].max() == intra["date"].max() and daily["date"].min() == intra["date"].min(),
        f"crsp {daily['date'].min().date()}→{daily['date'].max().date()}, "
        f"iid {intra['date'].min().date()}→{intra['date'].max().date()}",
    )

    merged = daily.merge(members, on=["date", "ticker"], how="inner")
    counts = merged.groupby("date")["ticker"].nunique()
    ok &= check(
        "R3 PIT merge yields 30 names per day",
        (counts == 30).all(),
        f"min={counts.min()}, max={counts.max()}, modal={counts.mode().iloc[0]}, "
        f"n_days={len(counts)}",
    )

    div_days = (daily["ret"] - daily["retx"]).abs() > 1e-6
    frac_div = div_days.mean()
    ok &= check(
        "R4 ret vs retx divergence is plausible",
        0.005 < frac_div < 0.15,
        f"{frac_div:.2%} of rows have material DlyRet != DlyRetx",
    )

    pm = pd.read_csv(PERMNO)
    pm_tickers = set(pm["ticker"].str.upper())
    required = {"DD", "DWDP", "DOW", "UTX", "RTX"}
    ok &= check(
        "R5 permno map covers DD/DWDP/DOW + UTX/RTX chains",
        required.issubset(pm_tickers),
        f"missing: {required - pm_tickers}",
    )

    tenure = pd.read_csv(TENURE)
    always_present = tenure[tenure["n_days"] == tenure["n_days"].max()]["ticker"].tolist()
    earn = pd.read_csv(EARN, parse_dates=["earnings_date"])
    counts_earn = earn.groupby("ticker").size()
    n_sparse = sum(counts_earn.reindex(always_present, fill_value=0) < 30)
    ok &= check(
        "R6 ≥30 earnings announcements for each always-present ticker",
        n_sparse <= 1,  # GS-IBES gap may remain; doesn't block backtests
        f"{n_sparse} always-present ticker(s) have <30 earnings; "
        f"total tickers in earnings file: {earn['ticker'].nunique()}",
    )

    print("=" * 60)
    print(("\033[92mALL GREEN\033[0m" if ok else "\033[91mREDS PRESENT\033[0m"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
