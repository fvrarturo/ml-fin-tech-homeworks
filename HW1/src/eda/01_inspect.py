"""Schema + shape inspection for the two WRDS pulls.

Outputs a JSON summary and small human-readable tables to _info/eda/.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "_info" / "eda"
OUT.mkdir(parents=True, exist_ok=True)


def describe_frame(df: pd.DataFrame, name: str) -> dict:
    out = {
        "name": name,
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "columns": [],
        "mem_mb": float(df.memory_usage(deep=True).sum() / 1e6),
    }
    for c in df.columns:
        s = df[c]
        col = {
            "name": c,
            "dtype": str(s.dtype),
            "n_missing": int(s.isna().sum()),
            "pct_missing": float(s.isna().mean()),
            "n_unique": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s):
            desc = s.describe(percentiles=[0.01, 0.5, 0.99])
            col.update(
                {
                    "min": float(desc.get("min", np.nan)),
                    "p01": float(desc.get("1%", np.nan)),
                    "median": float(desc.get("50%", np.nan)),
                    "p99": float(desc.get("99%", np.nan)),
                    "max": float(desc.get("max", np.nan)),
                    "mean": float(desc.get("mean", np.nan)),
                    "std": float(desc.get("std", np.nan)),
                }
            )
        out["columns"].append(col)
    return out


def load_daily() -> pd.DataFrame:
    p = DATA / "dow_daily.csv.gz"
    df = pd.read_csv(p, compression="gzip", low_memory=False)
    if "DlyCalDt" in df:
        df["DlyCalDt"] = pd.to_datetime(df["DlyCalDt"])
    return df


def load_intraday() -> pd.DataFrame:
    p = DATA / "dow_intraday.csv.gz"
    df = pd.read_csv(p, compression="gzip", low_memory=False)
    if "DATE" in df:
        df["DATE"] = pd.to_datetime(df["DATE"])
    return df


def panel_summary(df: pd.DataFrame, date_col: str, ticker_col: str, name: str) -> dict:
    info = {
        "name": name,
        "date_min": str(df[date_col].min().date()),
        "date_max": str(df[date_col].max().date()),
        "n_dates": int(df[date_col].nunique()),
        "n_tickers": int(df[ticker_col].nunique()),
        "tickers": sorted(df[ticker_col].dropna().unique().tolist()),
    }
    # panel completeness: rows per ticker / rows per date
    rpt = df.groupby(ticker_col).size().describe().to_dict()
    rpd = df.groupby(date_col).size().describe().to_dict()
    info["rows_per_ticker"] = {k: float(v) for k, v in rpt.items()}
    info["rows_per_date"] = {k: float(v) for k, v in rpd.items()}
    # ticker lifespans
    span = df.groupby(ticker_col)[date_col].agg(["min", "max", "count"]).reset_index()
    span.columns = [ticker_col, "first", "last", "n_days"]
    span["first"] = span["first"].dt.strftime("%Y-%m-%d")
    span["last"] = span["last"].dt.strftime("%Y-%m-%d")
    info["ticker_spans"] = span.to_dict(orient="records")
    return info


def main() -> None:
    print("[1/2] loading daily ...")
    daily = load_daily()
    print(f"  daily shape = {daily.shape}")
    print("[2/2] loading intraday ...")
    intra = load_intraday()
    print(f"  intraday shape = {intra.shape}")

    daily_desc = describe_frame(daily, "dow_daily")
    intra_desc = describe_frame(intra, "dow_intraday")

    daily_panel = panel_summary(daily, "DlyCalDt", "Ticker", "dow_daily")
    intra_panel = panel_summary(intra, "DATE", "SYM_ROOT", "dow_intraday")

    summary = {
        "daily": {"describe": daily_desc, "panel": daily_panel},
        "intraday": {"describe": intra_desc, "panel": intra_panel},
    }
    with open(OUT / "01_schema_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # Quick markdown cheat sheet
    lines = ["# Schema summary", ""]
    for k, d in summary.items():
        lines.append(f"## {k}")
        p = d["panel"]
        dz = d["describe"]
        lines.append(
            f"- rows = {dz['n_rows']:,}  cols = {dz['n_cols']}  mem ~{dz['mem_mb']:.1f} MB"
        )
        lines.append(
            f"- dates: {p['date_min']} -> {p['date_max']}  "
            f"(ndates={p['n_dates']}, ntickers={p['n_tickers']})"
        )
        lines.append(f"- tickers: {', '.join(p['tickers'])}")
        lines.append("")
    (OUT / "01_schema_summary.md").write_text("\n".join(lines))
    print("done -> _info/eda/01_schema_summary.{json,md}")


if __name__ == "__main__":
    main()
