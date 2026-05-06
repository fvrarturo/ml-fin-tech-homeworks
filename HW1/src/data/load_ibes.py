"""IBES earnings announcement loader.

Reads data/raw/IBES.csv.gz (quarterly EPS announcements for DJ30 ever-members)
and writes data/reference/earnings_dates.csv with one row per announcement:

    ticker        : str          # IBES TICKER (maps to CRSP ticker in most cases)
    earnings_date : date         # announcement date (ANNDATS)
    ann_time_et   : time         # announcement time (ANNTIMS)
    timing        : str          # BMO | AMC | INTRADAY
    period_end    : date         # fiscal period end (PENDS)
    eps_actual    : float

Blackout convention (consumed by src/robustness/earnings_blackout.py):
    BMO: blackout = [D-1, D]          (announced before open → D-1 signal already stale)
    AMC: blackout = [D, D+1]          (announced after close → D's close signal stale)
    INTRADAY: blackout = [D-1, D+1]   (rare; conservative)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "IBES.csv.gz"
OUT = ROOT / "data" / "reference" / "earnings_dates.csv"

DEFAULT_END_DATE = "2025-09-30"


def classify_timing(ann_time: pd.Timestamp) -> str:
    if pd.isna(ann_time):
        return "INTRADAY"
    h = ann_time.hour + ann_time.minute / 60.0
    if h < 9.5:          # before 09:30 ET open
        return "BMO"
    if h >= 16.0:        # at or after 16:00 ET close
        return "AMC"
    return "INTRADAY"


def load(end_date: str = DEFAULT_END_DATE) -> pd.DataFrame:
    raw = pd.read_csv(RAW, compression="gzip")
    raw["ANNDATS"] = pd.to_datetime(raw["ANNDATS"])
    raw["PENDS"] = pd.to_datetime(raw["PENDS"])
    raw["ANNTIMS"] = pd.to_datetime(raw["ANNTIMS"], format="%H:%M:%S", errors="coerce")

    raw["timing"] = raw["ANNTIMS"].apply(classify_timing)

    # IBES `TICKER` is a legacy code (NIKE, VISA, UNIH, CHV, WAG, XON, ...). Use
    # `OFTIC` (original ticker) as the stable ID that aligns with CRSP.
    df = pd.DataFrame({
        "ticker": raw["OFTIC"].astype(str),
        "earnings_date": raw["ANNDATS"],
        "ann_time_et": raw["ANNTIMS"].dt.time,
        "timing": raw["timing"],
        "period_end": raw["PENDS"],
        "eps_actual": pd.to_numeric(raw["VALUE"], errors="coerce"),
    })
    df = df[df["earnings_date"] <= pd.Timestamp(end_date)]
    df = df.drop_duplicates(["ticker", "earnings_date"])
    df = df.sort_values(["ticker", "earnings_date"]).reset_index(drop=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end-date", default=DEFAULT_END_DATE)
    args = ap.parse_args()

    df = load(end_date=args.end_date)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)

    by_timing = df["timing"].value_counts().to_dict()
    print(f"wrote {OUT}  rows={len(df):,}  tickers={df['ticker'].nunique()}  "
          f"dates={df['earnings_date'].min().date()} -> {df['earnings_date'].max().date()}")
    print(f"timing breakdown: {by_timing}")


if __name__ == "__main__":
    main()
