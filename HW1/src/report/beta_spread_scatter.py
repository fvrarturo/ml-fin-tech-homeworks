"""β vs spread scatter — the Roll (1984) bid-ask-bounce diagnostic visual.

Reads `data/processed/robustness/h2_beta_vs_spread.csv`.
Emits `icm/figures/h2_beta_vs_spread.{pdf,png}`.

If H2 REV were a bid-ask-bounce artifact, points would cluster on a steeply
downward-sloping line through the origin. The actual scatter shows a Pearson
ρ of roughly −0.1 (slope ≈ 0 with R² ≈ 0.01) — strong evidence *against*
the artifact hypothesis.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.report._style import ACCENT, MEANREV, NOTECOL, apply, style_axis

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "data" / "processed" / "robustness" / "h2_beta_vs_spread.csv"
OUT_DIR = ROOT / "icm" / "figures"


def render() -> None:
    apply()
    df = pd.read_csv(CSV).dropna(subset=["beta", "med_spread_bps"])

    x = df["med_spread_bps"].to_numpy()
    y = df["beta"].to_numpy()
    rho = np.corrcoef(x, y)[0, 1]
    slope, intercept = np.polyfit(x, y, 1)

    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    # Size points by |t| so IBM / CAT / SHW stand out
    sizes = 12 + 6 * df["t"].abs()
    ax.scatter(x, y, s=sizes, color=MEANREV, alpha=0.75,
               edgecolor="#333", linewidth=0.3)
    # Label the 6 most extreme tickers
    df["abs_t"] = df["t"].abs()
    for _, r in df.nlargest(6, "abs_t").iterrows():
        ax.annotate(r["ticker"], (r["med_spread_bps"], r["beta"]),
                    xytext=(4, 3), textcoords="offset points",
                    fontsize=7.5, color="#222")

    # OLS fit line
    xs = np.linspace(x.min() * 0.9, x.max() * 1.05, 100)
    ax.plot(xs, slope * xs + intercept, color=NOTECOL, linestyle="--",
            linewidth=1.0,
            label=f"OLS: $\\beta = {intercept:+.3f} {slope:+.4f}\\cdot s$")

    ax.axhline(0, color="#666", linewidth=0.5)
    ax.axhline(-1, color="#BBB", linewidth=0.4, linestyle=":")
    ax.set_xlabel("Median quoted spread (bps)")
    ax.set_ylabel(r"Per-ticker $\beta$ (rest-of-day on first-30)")
    ax.set_title("H2 REV — β vs spread (bid-ask-bounce diagnostic)",
                 fontweight="bold")
    ax.legend(loc="lower left")
    stats = (
        f"$\\rho(\\beta,\\ s)$ = {rho:+.3f}\n"
        f"slope-$t$ = {slope / (df['beta'].std()/np.sqrt(len(df))):.2f}\n"
        f"$R^2$ = {rho**2:.3f}   $N$ = {len(df)}"
    )
    ax.text(0.97, 0.02, stats, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.35", fc="white",
                      ec="#AAA", alpha=0.85))
    style_axis(ax, grid="both")
    fig.tight_layout()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "h2_beta_vs_spread.pdf")
    fig.savefig(OUT_DIR / "h2_beta_vs_spread.png", dpi=160)
    plt.close(fig)
    print(f"wrote h2_beta_vs_spread.{{pdf,png}}  (ρ = {rho:+.3f})")


if __name__ == "__main__":
    render()
