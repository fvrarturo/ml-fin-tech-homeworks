"""Audit an aggregation run.

Two reports:
    bar_counts.csv   — one row per (trading_date, ticker). Expected bar count
                        is 11 on regular sessions, 5 on early-close days.
    vwap_sanity.csv  — on 5 sampled ticker-days, compare daily volume-weighted
                        average price reconstructed from bars vs CRSP's
                        DlyPrcVol/DlyVol. Agreement within ~5% is the target
                        (Work1.md §6.1 verification).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_all_bars(bars_dir: Path) -> pd.DataFrame:
    parts = sorted(bars_dir.glob("year=*/ticker=*.parquet"))
    frames = []
    for p in parts:
        tkr = p.stem.split("=", 1)[1]
        df = pd.read_parquet(p)
        df["ticker"] = tkr
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out


def audit_bar_counts(
    bars: pd.DataFrame, early_close_dates: set
) -> pd.DataFrame:
    counts = (
        bars.groupby(["date", "ticker"], sort=True)
        .size()
        .rename("bar_count")
        .reset_index()
    )
    counts["is_early_close"] = counts["date"].isin(early_close_dates)
    counts["expected"] = np.where(counts["is_early_close"], 5, 11)
    counts["delta"] = counts["bar_count"] - counts["expected"]
    return counts


def audit_vwap(
    bars: pd.DataFrame,
    crsp_path: Path,
    n_samples: int = 5,
    seed: int = 17,
) -> pd.DataFrame:
    """Reconstruct daily VWAP from bars and compare to CRSP's DlyPrcVol/DlyVol."""
    day_vwap = (
        bars.groupby(["date", "ticker"], sort=False)
        .apply(
            lambda g: (g["vwap"] * g["volume"]).sum() / g["volume"].sum(),
            include_groups=False,
        )
        .rename("bar_vwap")
        .reset_index()
    )

    crsp = pd.read_parquet(crsp_path)[["date", "ticker", "dollar_volume", "volume"]]
    crsp["crsp_vwap"] = crsp["dollar_volume"] / crsp["volume"]
    merged = day_vwap.merge(crsp, on=["date", "ticker"], how="inner")
    merged["rel_err"] = (merged["bar_vwap"] - merged["crsp_vwap"]) / merged["crsp_vwap"]

    rng = np.random.default_rng(seed)
    idx = rng.choice(len(merged), size=min(n_samples, len(merged)), replace=False)
    sample = merged.iloc[idx].sort_values(["date", "ticker"]).reset_index(drop=True)
    return sample


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars-dir", type=Path, required=True)
    ap.add_argument("--early-closes", type=Path, required=True)
    ap.add_argument("--crsp", type=Path, default=None,
                    help="data/interim/daily.parquet (optional; skip VWAP audit if missing)")
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    bars = load_all_bars(args.bars_dir)
    ec = set(pd.read_csv(args.early_closes, parse_dates=["date"])["date"])

    counts = audit_bar_counts(bars, ec)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    counts.to_csv(args.out_dir / "bar_counts.csv", index=False)

    # Summary
    n_short = (counts["delta"] < 0).sum()
    n_over = (counts["delta"] > 0).sum()
    print(f"bar count audit: {len(counts):,} (ticker-day) cells")
    print(f"  correct:      {(counts['delta'] == 0).sum():,}")
    print(f"  short (<exp): {n_short:,}")
    print(f"  over  (>exp): {n_over:,}")

    vwap_summary = {}
    if args.crsp is not None and args.crsp.exists():
        sample = audit_vwap(bars, args.crsp)
        sample.to_csv(args.out_dir / "vwap_sanity.csv", index=False)
        print()
        print("VWAP sanity sample (bar-derived vs CRSP dollar_vol/volume):")
        print(sample.to_string(index=False))
        vwap_summary = {
            "n_samples": int(len(sample)),
            "max_abs_rel_err": float(sample["rel_err"].abs().max()),
            "mean_abs_rel_err": float(sample["rel_err"].abs().mean()),
        }

    summary = {
        "n_ticker_days": int(len(counts)),
        "n_correct": int((counts["delta"] == 0).sum()),
        "n_short_days": int(n_short),
        "n_over_days": int(n_over),
        "unique_tickers": int(bars["ticker"].nunique()),
        "unique_dates": int(bars["date"].nunique()),
        "vwap_audit": vwap_summary,
    }
    (args.out_dir / "validate_summary.json").write_text(json.dumps(summary, indent=2))
    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
