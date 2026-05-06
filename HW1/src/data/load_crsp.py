"""CRSP DSF loader.

Reads data/raw/dow_daily.csv.gz and writes a typed, filtered parquet to
data/interim/daily.parquet. Idempotent: run `python -m src.data.load_crsp`.

Output schema (one row per PERMNO-day):
    permno        : int
    ticker        : str
    date          : datetime64[ns]      # renamed from DlyCalDt
    open, high, low, close : float64    # abs() applied per CRSP negative-midquote convention
    bid, ask      : float64
    ret           : float64             # DlyRet (total return incl. dividends)
    retx          : float64             # DlyRetx (price-only; for dividend sanity checks)
    volume        : float64             # DlyVol shares
    dollar_volume : float64             # DlyPrcVol
    shrout        : float64
    vwretd, vwretx, ewretd, ewretx, sprtrn : float64  # CRSP-wide indexes
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "dow_daily.csv.gz"
RAW_SUPPLEMENTS = [ROOT / "data" / "raw" / "dow_daily_gs.csv.gz"]  # GS top-up pull
OUT = ROOT / "data" / "interim" / "daily.parquet"

DEFAULT_END_DATE = "2025-09-30"

RENAME = {
    "PERMNO": "permno",
    "Ticker": "ticker",
    "DlyCalDt": "date",
    "DlyOpen": "open",
    "DlyHigh": "high",
    "DlyLow": "low",
    "DlyClose": "close",
    "DlyBid": "bid",
    "DlyAsk": "ask",
    "DlyRet": "ret",
    "DlyRetx": "retx",
    "DlyVol": "volume",
    "DlyPrcVol": "dollar_volume",
    "ShrOut": "shrout",
}
KEEP = list(RENAME.values()) + ["vwretd", "vwretx", "ewretd", "ewretx", "sprtrn"]


def load(end_date: str = DEFAULT_END_DATE) -> pd.DataFrame:
    frames = [pd.read_csv(RAW, compression="gzip", low_memory=False)]
    for sup in RAW_SUPPLEMENTS:
        if sup.exists():
            frames.append(pd.read_csv(sup, compression="gzip", low_memory=False))
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns=RENAME)
    df["date"] = pd.to_datetime(df["date"])
    df["permno"] = df["permno"].astype("int64")
    df["ticker"] = df["ticker"].astype("string")
    for col in ("open", "high", "low", "close", "bid", "ask"):
        df[col] = df[col].abs()
    df = df[KEEP].sort_values(["ticker", "date"]).reset_index(drop=True)
    df = df[df["date"] <= pd.Timestamp(end_date)].copy()

    # CRSP has one known identical duplicate (RTX 2020-04-03 at the UTX→RTX ticker boundary).
    n_dup = df.duplicated(["permno", "date"]).sum()
    if n_dup:
        df = df.drop_duplicates(["permno", "date"]).reset_index(drop=True)
    assert df.duplicated(["permno", "date"]).sum() == 0, "duplicate (permno, date) after dedup"

    # Ticker-label patch at the UTX→RTX merger boundary. The UTC+Raytheon merger
    # closed 2020-04-03 Fri and CRSP immediately relabeled PERMNO 17830 as RTX,
    # but S&P DJI kept UTX in the index through 2020-04-03 and added RTX on
    # 2020-04-06 Mon (see data/reference/dj30_events.csv). To align CRSP with the
    # membership file for that single day, relabel the 2020-04-03 RTX row to UTX.
    mask = (df["permno"] == 17830) & (df["date"] == pd.Timestamp("2020-04-03"))
    df.loc[mask, "ticker"] = "UTX"
    n_tickers = df["ticker"].nunique()
    assert n_tickers == 40, f"expected 40 ever-members, got {n_tickers}"
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end-date", default=DEFAULT_END_DATE)
    args = ap.parse_args()

    df = load(end_date=args.end_date)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"wrote {OUT}  rows={len(df):,}  tickers={df['ticker'].nunique()}  "
          f"dates={df['date'].min().date()} -> {df['date'].max().date()}")


if __name__ == "__main__":
    main()
