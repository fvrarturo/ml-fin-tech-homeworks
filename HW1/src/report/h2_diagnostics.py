"""Three diagnostic panels for H2 REV — statistical properties section of ICM.

(1) Rolling 252-day Sharpe ratio with overlaid average.
(2) Daily-return histogram with fitted normal + QQ vs normal.
(3) Autocorrelogram of daily P&L out to lag 30, checks for dependence.

Each panel is its own figure (easier to drop into LaTeX separately).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats as scst

from src.report._style import ACCENT, MEANREV, NOTECOL, apply, style_axis

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT_DIR = ROOT / "icm" / "figures"


def _h2_rev() -> pd.Series:
    pnl = pd.read_parquet(PROCESSED / "h2_pnl.parquet")["rev_net"]
    pnl.index = pd.to_datetime(pnl.index)
    return pnl


def render_rolling_sharpe() -> None:
    r = _h2_rev()
    window = 252
    rolling_sr = (
        r.rolling(window).mean() / r.rolling(window).std() * np.sqrt(252)
    ).dropna()
    ann_sr = r.mean() / r.std() * np.sqrt(252)

    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(rolling_sr.index, rolling_sr.values, color=MEANREV, linewidth=1.4)
    ax.axhline(ann_sr, color=NOTECOL, linestyle="--", linewidth=0.8,
               label=f"Full-sample SR = {ann_sr:+.2f}")
    ax.axhline(0, color="#333", linewidth=0.5)
    ax.set_ylabel("Rolling 252-day Sharpe ratio")
    ax.set_title("H2 REV — rolling 252-day Sharpe", fontweight="bold")
    ax.legend(loc="upper left")
    style_axis(ax, grid="y")
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "h2_rolling_sharpe.pdf")
    fig.savefig(OUT_DIR / "h2_rolling_sharpe.png", dpi=160)
    plt.close(fig)
    print("wrote h2_rolling_sharpe.{pdf,png}")


def render_return_dist() -> None:
    r = _h2_rev() * 1e4  # bps
    mu, sd = r.mean(), r.std()
    skew, kurt = scst.skew(r), scst.kurtosis(r)  # excess kurtosis
    var95 = np.percentile(r, 5)
    es95 = r[r <= var95].mean()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 3.4))

    # Histogram + normal fit
    ax1.hist(r, bins=60, color=MEANREV, alpha=0.75, edgecolor="#333",
             linewidth=0.3, density=True)
    xx = np.linspace(r.min(), r.max(), 400)
    ax1.plot(xx, scst.norm.pdf(xx, mu, sd), color=NOTECOL, linewidth=1.3,
             linestyle="--", label="Normal fit")
    ax1.axvline(var95, color=NOTECOL, linestyle=":", linewidth=0.9)
    ax1.axvline(es95, color="#884", linestyle=":", linewidth=0.9)
    ax1.annotate(f"VaR$_{{95}}$ = {var95:.1f} bps", xy=(var95, 0.003),
                 xytext=(var95 - 5, 0.005), color=NOTECOL, fontsize=8,
                 arrowprops=dict(arrowstyle="->", color=NOTECOL, lw=0.5))
    ax1.annotate(f"ES$_{{95}}$ = {es95:.1f} bps", xy=(es95, 0.0015),
                 xytext=(es95 - 8, 0.0035), color="#664", fontsize=8,
                 arrowprops=dict(arrowstyle="->", color="#664", lw=0.5))
    ax1.set_xlabel("Daily P&L (bps)")
    ax1.set_ylabel("Density")
    ax1.set_title("(a) Daily return distribution", fontweight="bold")
    ax1.legend(loc="upper right")
    style_axis(ax1, grid="y")
    stats_text = (
        f"μ = {mu:+.2f} bps,  σ = {sd:.2f} bps\n"
        f"skew = {skew:+.3f},  ex-kurt = {kurt:+.2f}"
    )
    ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes,
             va="top", fontsize=8, color="#333",
             bbox=dict(boxstyle="round,pad=0.3", fc="white",
                       ec="#AAA", alpha=0.8))

    # QQ-normal
    probplot_res = scst.probplot(r.values, dist="norm", plot=None)
    theoretical, ordered = probplot_res[0]
    slope, intercept, _ = probplot_res[1]
    ax2.plot(theoretical, ordered, ".", color=MEANREV, markersize=3, alpha=0.6)
    ax2.plot(theoretical, slope * theoretical + intercept,
             color=NOTECOL, linestyle="--", linewidth=1.0,
             label="Normal reference")
    ax2.set_xlabel("Theoretical normal quantiles")
    ax2.set_ylabel("Sample quantiles (bps)")
    ax2.set_title("(b) QQ vs normal", fontweight="bold")
    ax2.legend(loc="upper left")
    style_axis(ax2, grid="both")

    fig.suptitle("H2 REV — statistical properties",
                 x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT_DIR / "h2_return_distribution.pdf")
    fig.savefig(OUT_DIR / "h2_return_distribution.png", dpi=160)
    plt.close(fig)
    print("wrote h2_return_distribution.{pdf,png}")


def render_autocorr() -> None:
    r = _h2_rev()
    lags = 30
    # Compute ACF with 95% bars at ±1.96/√n
    n = len(r)
    acfs = [r.autocorr(lag=k) for k in range(1, lags + 1)]
    ci = 1.96 / np.sqrt(n)

    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.bar(range(1, lags + 1), acfs, color=MEANREV, width=0.7,
           edgecolor="#333", linewidth=0.4)
    ax.axhline(0, color="#333", linewidth=0.5)
    ax.axhline(ci, color=NOTECOL, linestyle="--", linewidth=0.8,
               label=f"95% CI: ±{ci:.3f}")
    ax.axhline(-ci, color=NOTECOL, linestyle="--", linewidth=0.8)
    ax.set_xlabel("Lag (days)")
    ax.set_ylabel(r"Autocorrelation $\rho_k$")
    ax.set_title("H2 REV — autocorrelogram of daily P&L", fontweight="bold")
    ax.legend(loc="upper right")
    style_axis(ax, grid="y")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "h2_autocorr.pdf")
    fig.savefig(OUT_DIR / "h2_autocorr.png", dpi=160)
    plt.close(fig)
    print("wrote h2_autocorr.{pdf,png}")


def main() -> None:
    apply()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render_rolling_sharpe()
    render_return_dist()
    render_autocorr()


if __name__ == "__main__":
    main()
