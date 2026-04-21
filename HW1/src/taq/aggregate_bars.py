"""TAQ consolidated-trades aggregation to 30-minute bars.

Designed to run on MIT Engaging. The expensive I/O — reading a 4–17 GB
gzipped TAQ CSV — is wrapped around pure functions that can be unit-tested
locally on tiny synthetic data.

Pipeline per year (one SLURM task):

    TAQ{YYYY}.csv.gz
        │ pandas.read_csv(chunksize=5M, compression="gzip")
        ▼
    filter_trades()          # DJ30 tickers, regular session, valid trades
        │
        ▼
    bar_index(), aggregate_from_trades()
        │
        ▼
    one parquet per ticker:  out/bars/year=YYYY/ticker=XXX.parquet

Schema (per ticker-year parquet):
    date (datetime64[D]), bar (int1..11 on regular days, 1..5 on early-close),
    open, high, low, close, vwap (float64),
    volume, dollar_volume (int64 / float64), n_trades (int32).

Bar numbering convention (Work1.md §6.1):
    Full session 09:30-16:00 = 13 half-hour slots (k=1..13).
    Keep only k=2..12 (drop first and last 30 min to avoid auction effects).
    On early-close days 09:30-13:00 = 7 slots; keep k=2..6.
    Output uses **1-indexed "kept" bar numbers** so downstream signal
    construction sees a contiguous k=1..11 (or 1..5 on short days).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# CONSTANTS                                                                   #
# --------------------------------------------------------------------------- #

# Seconds from midnight.
REG_OPEN = 9 * 3600 + 30 * 60          # 34200  = 09:30:00
REG_CLOSE = 16 * 3600                  # 57600  = 16:00:00
EARLY_CLOSE = 13 * 3600                # 46800  = 13:00:00
BAR_SECS = 30 * 60                     # 1800   = 30 min

# TR_SCOND modifier characters that disqualify a trade from our universe.
# Reference: NYSE TAQ MTF spec; Gao et al. (2018) exclude the same set.
#   @  : primary regular sale (keep, this is the default)
#   O  : opening-auction trade — price discovery, not continuous
#   6  : cancel prior
#   L  : late sale (out-of-sequence late report)
#   Z  : out of sequence
#   T  : form-T (pre/post-market)
#   W  : average-price / weighted — stopped trade
#   I  : odd-lot (< round lot)
#   U  : extended-hours late
BAD_SCOND = re.compile(r"[O6LZTWUI]")

# NaN-safe string for pandas
SCOND_NA = ""


# --------------------------------------------------------------------------- #
# PURE FUNCTIONS (unit-tested locally)                                        #
# --------------------------------------------------------------------------- #

def parse_time_to_sec(time_col: pd.Series) -> pd.Series:
    """Convert TAQ TIME_M to integer seconds from midnight.

    TAQ ships timestamps as "H:MM:SS.fffffffff" — the hour is variable-width
    (1 or 2 digits; e.g., "4:00:00.017392614" for 04:00:00). We vectorized-split
    on ':' rather than fixed-slicing. Sub-second is discarded (bar assignment
    only needs second resolution). 10-20× faster than pd.to_datetime at TAQ
    scale.
    """
    s = time_col.astype(str)
    parts = s.str.split(":", n=2, expand=True)
    hh = parts[0].astype(np.int32)
    mm = parts[1].astype(np.int32)
    # Seconds may be "SS", "SS.fff...", or even "S" / "S.f" — split on '.' and
    # take the integer portion.
    ss = parts[2].str.split(".", n=1, expand=True)[0].astype(np.int32)
    return hh * 3600 + mm * 60 + ss


def bar_index(time_sec: pd.Series, *, is_early_close: pd.Series | bool = False) -> pd.Series:
    """Assign 1-indexed bar k given time-of-day seconds.

    Regular day (close=16:00): k ∈ {1..13} for 09:30-16:00 in 30-min slots.
    Early-close day (close=13:00): k ∈ {1..7} for 09:30-13:00.
    Returns 0 for pre/post-session trades (filtered out downstream).
    """
    # raw bar starting at k=1 for 09:30:00
    k = ((time_sec - REG_OPEN) // BAR_SECS).astype(np.int32) + 1

    # Mark invalid (pre/post-session). Use the applicable close.
    if isinstance(is_early_close, bool):
        close_sec = EARLY_CLOSE if is_early_close else REG_CLOSE
        k = k.where((time_sec >= REG_OPEN) & (time_sec < close_sec), 0)
    else:
        close_sec = pd.Series(
            np.where(is_early_close, EARLY_CLOSE, REG_CLOSE), index=time_sec.index
        )
        k = k.where((time_sec >= REG_OPEN) & (time_sec < close_sec), 0)
    return k.astype(np.int32)


def filter_trades(
    df: pd.DataFrame,
    keep_tickers: set[str],
    early_close_dates: set[pd.Timestamp],
) -> pd.DataFrame:
    """Filter a chunk of raw TAQ rows to our analysis universe.

    Applies (in order — cheapest predicate first for early exit):
        1. SYM_SUFFIX blank (common stock; drops preferreds/class-B/warrants)
        2. SYM_ROOT in keep_tickers (DJ30 40 ever-members)
        3. TR_CORR == "00"
        4. PRICE > 0 and SIZE > 0
        5. TR_SCOND has no disqualifying modifier (O, 6, L, Z, T, W, U, I)
        6. TIME_M inside the day's regular session
    """
    # (1) suffix filter  — SYM_SUFFIX is NaN or empty for common stock
    suf = df["SYM_SUFFIX"]
    if suf.dtype == object:
        mask = suf.isna() | (suf.str.len() == 0)
    else:
        mask = suf.isna()
    df = df[mask]

    # (2) ticker
    df = df[df["SYM_ROOT"].isin(keep_tickers)]
    if df.empty:
        return df

    # (3) correction flag — accept "00" / 0 / "0" only
    corr = df["TR_CORR"].astype(str).str.zfill(2)
    df = df[corr == "00"]

    # (4) price / size
    df = df[(df["PRICE"] > 0) & (df["SIZE"] > 0)]
    if df.empty:
        return df

    # (5) TR_SCOND modifier filter
    scond = df["TR_SCOND"].fillna(SCOND_NA).astype(str)
    df = df[~scond.str.contains(BAD_SCOND, regex=True)]
    if df.empty:
        return df

    # (6) time-of-day filter. Need to know the session close for the given date.
    df = df.copy()
    df["sec"] = parse_time_to_sec(df["TIME_M"])
    df["_date"] = pd.to_datetime(df["DATE"])
    df["_is_early"] = df["_date"].isin(early_close_dates)
    close_sec = np.where(df["_is_early"], EARLY_CLOSE, REG_CLOSE)
    df = df[(df["sec"] >= REG_OPEN) & (df["sec"] < close_sec)]
    return df


def aggregate_from_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate filtered trades to 30-min bars per (ticker, date).

    Input columns required: SYM_ROOT, _date, sec, _is_early, PRICE, SIZE.
    Output columns: date, ticker, bar_raw, bar, open, high, low, close, vwap,
                    volume, dollar_volume, n_trades.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["date", "ticker", "bar_raw", "bar", "open", "high", "low",
                     "close", "vwap", "volume", "dollar_volume", "n_trades"]
        )

    df = df.assign(
        bar_raw=bar_index(df["sec"], is_early_close=df["_is_early"]),
        dollar=df["PRICE"] * df["SIZE"],
    )
    # bar_raw=0 means pre/post-session (already excluded by filter_trades, but
    # be defensive).
    df = df[df["bar_raw"] > 0]

    # Drop first and last bar of each session (auction effects, Work1.md §6.1).
    n_per_day = np.where(df["_is_early"], 7, 13)
    df = df[(df["bar_raw"] > 1) & (df["bar_raw"] < pd.Series(n_per_day, index=df.index))]

    grouped = df.groupby(["_date", "SYM_ROOT", "bar_raw"], sort=True, as_index=False)
    agg = grouped.agg(
        open=("PRICE", "first"),
        high=("PRICE", "max"),
        low=("PRICE", "min"),
        close=("PRICE", "last"),
        volume=("SIZE", "sum"),
        dollar_volume=("dollar", "sum"),
        n_trades=("SIZE", "size"),
    )
    agg["vwap"] = agg["dollar_volume"] / agg["volume"]

    # Re-number bars to contiguous 1..11 (or 1..5 on early-close) so downstream
    # shift()-based logic sees a clean sequence.
    agg["bar"] = agg["bar_raw"] - 1

    agg = agg.rename(columns={"_date": "date", "SYM_ROOT": "ticker"})
    return agg[["date", "ticker", "bar_raw", "bar", "open", "high", "low",
                "close", "vwap", "volume", "dollar_volume", "n_trades"]]


# --------------------------------------------------------------------------- #
# I/O WRAPPER  (cluster-side)                                                 #
# --------------------------------------------------------------------------- #

TAQ_DTYPES = {
    "DATE": "string",
    "TIME_M": "string",
    "EX": "string",
    "SYM_ROOT": "string",
    "SYM_SUFFIX": "string",
    "TR_SCOND": "string",
    "SIZE": "int64",
    "PRICE": "float64",
    "TR_CORR": "string",
}


def iter_chunks(path: Path, chunksize: int = 5_000_000) -> Iterable[pd.DataFrame]:
    """Read a gzipped TAQ CSV in chunks. No date parsing here — that's part
    of filter_trades()."""
    return pd.read_csv(
        path,
        compression="gzip",
        dtype=TAQ_DTYPES,
        chunksize=chunksize,
        na_filter=True,
    )


def aggregate_year(
    input_path: Path,
    output_dir: Path,
    year: int,
    keep_tickers: set[str],
    early_close_dates: set[pd.Timestamp],
    chunksize: int = 5_000_000,
    progress_every: int = 5,
) -> dict:
    """Stream-read one year's TAQ file and emit a partitioned-by-ticker parquet
    tree under `output_dir / year=YYYY / ticker=XXX.parquet`.

    Returns a small meta dict with row counts and sha256(file) for auditing.
    """
    partial_frames: list[pd.DataFrame] = []
    rows_in, rows_kept = 0, 0

    for i, chunk in enumerate(iter_chunks(input_path, chunksize=chunksize)):
        rows_in += len(chunk)
        filt = filter_trades(chunk, keep_tickers, early_close_dates)
        if not filt.empty:
            rows_kept += len(filt)
            partial_frames.append(
                aggregate_from_trades(filt)
            )
        if progress_every and i % progress_every == 0:
            print(f"  [{year}] chunk {i:3d}  in={rows_in:,}  kept={rows_kept:,}", flush=True)

    if not partial_frames:
        print(f"  [{year}] no rows kept — writing empty marker")
        (output_dir / f"year={year}" / "_EMPTY").mkdir(parents=True, exist_ok=True)
        return {"year": year, "rows_in": rows_in, "rows_kept": 0,
                "rows_out": 0, "tickers": 0}

    bars = pd.concat(partial_frames, ignore_index=True)
    # A single (date, ticker, bar) may have partials across chunks if the file
    # wasn't sorted per-ticker within a day. Merge.
    merged = (
        bars.groupby(["date", "ticker", "bar_raw", "bar"], sort=True, as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            dollar_volume=("dollar_volume", "sum"),
            n_trades=("n_trades", "sum"),
        )
    )
    merged["vwap"] = merged["dollar_volume"] / merged["volume"]
    merged = merged[
        ["date", "ticker", "bar_raw", "bar", "open", "high", "low",
         "close", "vwap", "volume", "dollar_volume", "n_trades"]
    ]

    year_dir = output_dir / f"year={year}"
    year_dir.mkdir(parents=True, exist_ok=True)

    tickers_written = 0
    for tkr, sub in merged.groupby("ticker"):
        sub.drop(columns=["ticker"]).to_parquet(
            year_dir / f"ticker={tkr}.parquet", index=False
        )
        tickers_written += 1

    print(f"  [{year}] wrote {tickers_written} ticker parquets, "
          f"{len(merged):,} bars from {rows_kept:,} trades / {rows_in:,} raw rows")

    return {
        "year": year,
        "rows_in": int(rows_in),
        "rows_kept": int(rows_kept),
        "rows_out": int(len(merged)),
        "tickers": int(tickers_written),
        "file_sha256": _sha256(input_path),
    }


def _sha256(path: Path, chunk_bytes: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(chunk_bytes), b""):
            h.update(b)
    return h.hexdigest()[:16]


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #

def _load_tickers(path: Path) -> set[str]:
    """Read DJ30 tenure or membership file — either works, we just need the
    full 40-ticker ever-member list."""
    df = pd.read_csv(path)
    col = "ticker" if "ticker" in df.columns else df.columns[0]
    return set(df[col].astype(str))


def _load_early_closes(path: Path) -> set[pd.Timestamp]:
    df = pd.read_csv(path, parse_dates=["date"])
    return set(df["date"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True,
                    help="Path to TAQ{YYYY}.csv.gz")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--output-dir", type=Path, required=True,
                    help="Root of partitioned parquet output")
    ap.add_argument("--tickers", type=Path, required=True,
                    help="CSV with a `ticker` column, 40 DJ30 ever-members")
    ap.add_argument("--early-closes", type=Path, required=True)
    ap.add_argument("--chunksize", type=int, default=5_000_000)
    ap.add_argument("--meta", type=Path, default=None,
                    help="Write run metadata JSON here (defaults to stdout)")
    args = ap.parse_args()

    keep = _load_tickers(args.tickers)
    early = _load_early_closes(args.early_closes)

    print(f"aggregate_year: {args.input}  ({args.input.stat().st_size/1e9:.2f} GB)")
    print(f"  tickers: {len(keep)}   early-close days: {len(early)}")
    print(f"  chunksize: {args.chunksize:,}")

    meta = aggregate_year(
        input_path=args.input,
        output_dir=args.output_dir,
        year=args.year,
        keep_tickers=keep,
        early_close_dates=early,
        chunksize=args.chunksize,
    )

    if args.meta:
        args.meta.write_text(json.dumps(meta, indent=2))
    else:
        print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
