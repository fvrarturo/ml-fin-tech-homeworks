"""Lo-MacKinlay (1988) variance ratio term structure — Work1.md §8.1.

For a log-return series r_t, the q-period variance ratio is

    VR(q) = Var(r_{t,q}) / (q · Var(r_{t,1}))

If the series is a random walk, VR(q) = 1. VR < 1 is the reversal signature
(autocovariances negative on net); VR > 1 is trending.

Heteroskedasticity-robust M2 z-statistic (Lo & MacKinlay 1988, Theorem 3) is
    M2 = (VR(q) − 1) / sqrt(theta_hat / n)
where theta_hat sums squared products of lagged returns.

For DJ30 we compute VR(q) per ticker for q ∈ {2, 5, 21, 63, 126, 252}, pool
across tickers, and produce a term-structure figure. The continuous-horizon
reading should corroborate Table 3: strong <1 in the 5-to-monthly band,
near/above 1 at the 6-month horizon.

Outputs:
    data/processed/robustness/vr_term_structure.csv
    icm/figures/vr_term_structure.{pdf,png}
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.report._style import ACCENT, MEANREV, MOMCOL, apply, style_axis

ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / "data" / "interim" / "daily.parquet"
Q_GRID = [2, 5, 21, 63, 126, 252]
OUT_CSV = ROOT / "data" / "processed" / "robustness" / "vr_term_structure.csv"
OUT_FIG = ROOT / "icm" / "figures" / "vr_term_structure"


def _vr_m2(r: np.ndarray, q: int) -> tuple[float, float]:
    """Return (VR(q), M2 z-statistic) for a 1-D log-return array."""
    n = len(r)
    if n < q + 2:
        return np.nan, np.nan
    mu = r.mean()
    var_1 = ((r - mu) ** 2).mean()
    if var_1 <= 0:
        return np.nan, np.nan

    # Aggregated q-period returns using overlapping windows, per LM88 eq. 3a
    nq = n - q + 1
    rq = np.convolve(r, np.ones(q), mode="valid") - q * mu
    var_q = (rq * rq).sum() / (n * q * (1 - q / n))
    vr = var_q / var_1

    # Heteroskedasticity-robust variance of VR-1 — LM88 Theorem 3 / Cochrane.
    theta = 0.0
    rc = r - mu
    for k in range(1, q):
        delta_k = ((rc[k:] * rc[:-k]) ** 2).sum() / (rc * rc).sum() ** 2 * n
        theta += (2 * (q - k) / q) ** 2 * delta_k
    if theta <= 0:
        return vr, np.nan
    m2 = (vr - 1) / np.sqrt(theta)
    return float(vr), float(m2)


def compute() -> pd.DataFrame:
    daily = pd.read_parquet(DAILY)[["ticker", "date", "ret"]]
    daily["log_r"] = np.log1p(daily["ret"])

    rows = []
    for tkr, sub in daily.groupby("ticker"):
        r = sub["log_r"].dropna().to_numpy()
        if len(r) < max(Q_GRID) + 2:
            continue
        for q in Q_GRID:
            vr, m2 = _vr_m2(r, q)
            rows.append({"ticker": tkr, "q": q, "vr": vr, "m2": m2,
                         "n": len(r)})
    return pd.DataFrame(rows)


def render(df: pd.DataFrame) -> None:
    apply()
    piv_vr = df.pivot(index="q", columns="ticker", values="vr").sort_index()
    median = piv_vr.median(axis=1)
    q25 = piv_vr.quantile(0.25, axis=1)
    q75 = piv_vr.quantile(0.75, axis=1)

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    # Per-ticker light grey lines
    for tkr in piv_vr.columns:
        ax.plot(piv_vr.index, piv_vr[tkr], color="#BBB", linewidth=0.6,
                alpha=0.6, zorder=1)
    # Shaded IQR band
    ax.fill_between(piv_vr.index, q25, q75, color=MEANREV, alpha=0.2,
                    linewidth=0, zorder=2, label="IQR")
    # Cross-sectional median
    ax.plot(median.index, median.values, color=MEANREV, linewidth=1.8,
            marker="o", markersize=4, zorder=3,
            label="Cross-sectional median")
    # Random-walk null
    ax.axhline(1.0, color="#444", linestyle="--", linewidth=0.8,
               label="Random-walk null")
    ax.set_xscale("log")
    ax.set_xlabel("$q$ (trading days, log scale)")
    ax.set_ylabel(r"$\mathrm{VR}(q)$")
    ax.set_title("Variance-ratio term structure — 40 DJ30 ever-members",
                 fontweight="bold")
    ax.legend(loc="upper right")
    style_axis(ax, grid="both")

    # Annotate pooled extreme reads.
    for q in Q_GRID:
        m = median.loc[q]
        ax.annotate(f"{m:.2f}", xy=(q, m), xytext=(0, -12),
                    textcoords="offset points", ha="center",
                    color=MEANREV, fontsize=7.5)

    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG.with_suffix(".pdf"))
    fig.savefig(OUT_FIG.with_suffix(".png"), dpi=160)
    plt.close(fig)


def main() -> None:
    df = compute()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.round(6).to_csv(OUT_CSV, index=False)
    render(df)

    # Console summary
    pooled = df.groupby("q")[["vr", "m2"]].agg(
        vr_median=("vr", "median"),
        vr_mean=("vr", "mean"),
        m2_median=("m2", "median"),
        pct_vr_lt_1=("vr", lambda s: (s < 1).mean()),
    )
    print("Pooled variance-ratio term structure:")
    print(pooled.round(3).to_string())
    print(f"\nwrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_FIG.relative_to(ROOT)}.{{pdf,png}}")


if __name__ == "__main__":
    main()
