"""WRDS Intraday Indicators (iid_ms) loader.

Reads data/raw/dow_intraday.csv.gz, trims to end_date, and writes
data/interim/intraday.parquet. One row per (date, ticker).

Column rename is intentionally light — we keep the WRDS names for the
microstructure columns since they're documented in REFERENCE_DATA.md and
the prior EDA already references them.

Output columns used downstream:
    date          : datetime64[ns]
    ticker        : str (from SYM_ROOT)
    open, close   : float64 (OPrc, CPrc)
    mid_after_open, mid_before_close, mid_1pm, mid_4pm : float64
    quoted_spread_bps : float64 (QuotedSpread_Percent_tw * 1e4)
    price_impact      : float64 (PercentPriceImpact_LR_Ave)
    bs_ratio_vol      : float64 (order imbalance)
    ivol_t, ivol_q    : float64 (intraday realized vol)
    var_ratio1..5     : float64 (pre-computed variance ratios)
    ret_mkt_m         : float64 (market-sector return)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "dow_intraday.csv.gz"
RAW_SUPPLEMENTS = [ROOT / "data" / "raw" / "dow_intraday_gs.csv.gz"]  # GS top-up pull
OUT = ROOT / "data" / "interim" / "intraday.parquet"
EARLY_CLOSES = ROOT / "data" / "reference" / "nyse_early_closes.csv"

DEFAULT_END_DATE = "2025-09-30"

RENAME = {
    "DATE": "date",
    "SYM_ROOT": "ticker",
    "OPrc": "open",
    "CPrc": "close",
    "QuotedSpread_Percent_tw": "quoted_spread_frac",
    "PercentPriceImpact_LR_Ave": "price_impact",
}
KEEP = [
    "date", "ticker", "open", "close",
    "mid_after_open", "mid_before_close", "mid_1pm", "mid_4pm",
    "quoted_spread_bps", "price_impact",
    "bs_ratio_vol", "ivol_t", "ivol_q",
    "var_ratio1", "var_ratio2", "var_ratio3", "var_ratio4", "var_ratio5",
    "ret_mkt_m",
]


def load(end_date: str = DEFAULT_END_DATE) -> pd.DataFrame:
    frames = [pd.read_csv(RAW, compression="gzip", low_memory=False)]
    for sup in RAW_SUPPLEMENTS:
        if sup.exists():
            frames.append(pd.read_csv(sup, compression="gzip", low_memory=False))
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns=RENAME)
    df["date"] = pd.to_datetime(df["date"])
    df["ticker"] = df["ticker"].astype("string")
    df["quoted_spread_bps"] = df["quoted_spread_frac"] * 1e4

    # iid_ms uses SYM_ROOT only — preferreds, class-B, and warrants collapse onto
    # the same (date, ticker) key. Keep the single most-traded security per day
    # (common stock dominates by orders of magnitude).
    df = df.sort_values(["date", "ticker", "total_dollar_m"], ascending=[True, True, False])
    df = df.drop_duplicates(["date", "ticker"], keep="first").reset_index(drop=True)

    df = df[df["date"] <= pd.Timestamp(end_date)].copy()

    # Ticker-label patch at the UTX→RTX merger boundary. See the twin patch in
    # src/data/load_crsp.py for rationale. iid_ms has the same legal-entity
    # relabel on 2020-04-03; we rewrite it back to UTX so the PIT merge succeeds.
    mask = (df["ticker"] == "RTX") & (df["date"] == pd.Timestamp("2020-04-03"))
    df.loc[mask, "ticker"] = "UTX"

    df = df[KEEP].sort_values(["ticker", "date"]).reset_index(drop=True)
    assert df.duplicated(["date", "ticker"]).sum() == 0, "duplicate (date, ticker) in iid"
    return df


def audit_early_close(df: pd.DataFrame) -> pd.DataFrame:
    """REFERENCE_DATA.md §2.5 audit: on short sessions, mid_before_close should be
    timestamped in a pre-13:00 window. We can't verify timestamps from iid_ms
    directly (the schema only exposes the midprice, not its timestamp), so we
    sanity-check that mid_before_close ≠ close on those days — a proxy for
    'WRDS adjusted the window.'"""
    ec = pd.read_csv(EARLY_CLOSES, parse_dates=["date"])
    ec_set = set(ec["date"])
    sub = df[df["date"].isin(ec_set)].copy()
    sub["diff"] = (sub["mid_before_close"] - sub["close"]).abs()
    return sub.groupby("date")["diff"].mean().reset_index()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end-date", default=DEFAULT_END_DATE)
    ap.add_argument("--audit-early-close", action="store_true")
    args = ap.parse_args()

    df = load(end_date=args.end_date)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"wrote {OUT}  rows={len(df):,}  tickers={df['ticker'].nunique()}  "
          f"dates={df['date'].min().date()} -> {df['date'].max().date()}")

    if args.audit_early_close:
        rep = audit_early_close(df)
        print("\nEarly-close audit (mean |mid_before_close - close| per date; "
              "non-zero = WRDS re-windowed the mid on short sessions):")
        print(rep.to_string(index=False))


if __name__ == "__main__":
    main()
