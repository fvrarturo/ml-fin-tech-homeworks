"""Produce two diagnostic plots: VR term structure and microstructure vs reversal."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({"figure.dpi": 120, "font.size": 9})

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "_info" / "eda"
OUT.mkdir(parents=True, exist_ok=True)


def variance_ratio(rets: np.ndarray, q: int) -> float:
    r = rets[~np.isnan(rets)]
    n = (len(r) // q) * q
    if n < q * 10:
        return np.nan
    r = r[:n]
    r1_var = np.var(r, ddof=1)
    rq = r.reshape(-1, q).sum(axis=1)
    rq_var = np.var(rq, ddof=1)
    return rq_var / (q * r1_var) if r1_var > 0 else np.nan


def main() -> None:
    df = pd.read_csv(ROOT / "data" / "dow_daily.csv.gz", compression="gzip", low_memory=False)
    df["DlyCalDt"] = pd.to_datetime(df["DlyCalDt"])
    df["DlyRet"] = pd.to_numeric(df["DlyRet"], errors="coerce")
    df = df.sort_values(["Ticker", "DlyCalDt"])

    qs = [2, 3, 5, 10, 15, 20, 40, 60, 100, 126, 200]
    curves = []
    for tkr, sub in df.groupby("Ticker"):
        r = sub["DlyRet"].values
        row = [variance_ratio(r, q) for q in qs]
        curves.append((tkr, row))

    arr = np.array([r for _, r in curves], dtype=float)
    med = np.nanmedian(arr, axis=0)
    p25 = np.nanpercentile(arr, 25, axis=0)
    p75 = np.nanpercentile(arr, 75, axis=0)

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for _, r in curves:
        ax.plot(qs, r, color="lightgray", lw=0.5, alpha=0.7)
    ax.fill_between(qs, p25, p75, color="#a31f34", alpha=0.18, label="25-75 pct")
    ax.plot(qs, med, color="#a31f34", lw=2.0, label="cross-sec median")
    ax.axhline(1.0, color="black", ls="--", lw=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("horizon q (trading days)")
    ax.set_ylabel("Variance Ratio VR(q)")
    ax.set_title("Term structure of VR on DJ30 panel (2016-2025)")
    ax.legend(loc="lower left")
    ax.grid(True, ls=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(OUT / "04_vr_term_structure.png", dpi=150)
    plt.close(fig)

    # Ticker-level spread vs rho_1 scatter
    intr = pd.read_csv(ROOT / "data" / "dow_intraday.csv.gz", compression="gzip", low_memory=False)
    intr["QS"] = pd.to_numeric(intr["QuotedSpread_Percent_tw"], errors="coerce") * 1e4
    spread = intr.groupby("SYM_ROOT")["QS"].median().rename("spread_bps")

    rho_1 = (
        df.groupby("Ticker")["DlyRet"]
        .apply(lambda s: s.autocorr(lag=1))
        .rename("rho_1")
    )
    merged = pd.concat([spread, rho_1], axis=1).dropna()

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    ax.scatter(merged["spread_bps"], merged["rho_1"], color="#145090", s=36, alpha=0.8)
    for tkr, row in merged.iterrows():
        ax.annotate(tkr, (row["spread_bps"], row["rho_1"]), fontsize=7, alpha=0.7)
    ax.axhline(0, color="black", ls="--", lw=0.7)
    ax.set_xlabel("median quoted spread (bps, intraday)")
    ax.set_ylabel(r"daily return $\rho_1$")
    ax.set_title("Microstructure vs short-term reversal")
    ax.grid(True, ls=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(OUT / "04_spread_vs_rho1.png", dpi=150)
    plt.close(fig)

    print("plots saved to _info/eda/")


if __name__ == "__main__":
    main()
