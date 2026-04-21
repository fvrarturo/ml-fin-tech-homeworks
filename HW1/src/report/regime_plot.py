"""H2 REV stability visuals — year-by-year and VIX-quintile bar charts.

Reads the existing CSVs built by src/robustness/h2_regime_time.py:
    data/processed/robustness/h2_by_year.csv
    data/processed/robustness/h2_by_vix_quintile.csv

Emits:
    icm/figures/h2_by_year.{pdf,png}
    icm/figures/h2_by_vix_quintile.{pdf,png}
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.backtest.metrics import bonferroni_threshold
from src.report._style import ACCENT, MEANREV, NOTECOL, apply, style_axis

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "icm" / "figures"
BY_YEAR = ROOT / "data" / "processed" / "robustness" / "h2_by_year.csv"
BY_VIX = ROOT / "data" / "processed" / "robustness" / "h2_by_vix_quintile.csv"


def render_year() -> None:
    df = pd.read_csv(BY_YEAR)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(9.5, 3.5), gridspec_kw={"width_ratios": [1, 1]}
    )

    ax1.bar(df["year"].astype(str), df["sharpe"], color=MEANREV,
            edgecolor="#333", linewidth=0.5)
    ax1.axhline(0, color="#333", linewidth=0.6)
    ax1.set_ylabel("Sharpe ratio")
    ax1.set_title("(a) Sharpe by calendar year", fontweight="bold")
    style_axis(ax1, grid="y")
    for i, (y, sr) in enumerate(zip(df["year"], df["sharpe"])):
        ax1.annotate(f"{sr:+.2f}", (i, sr), ha="center",
                     va="bottom" if sr >= 0 else "top",
                     fontsize=7.5, color="#444")

    ax2.bar(df["year"].astype(str), df["ann_ret"] * 100,
            color=MEANREV, edgecolor="#333", linewidth=0.5)
    ax2.axhline(0, color="#333", linewidth=0.6)
    ax2.set_ylabel("Annualized return (%)")
    ax2.set_title("(b) Annualized return by calendar year", fontweight="bold")
    style_axis(ax2, grid="y")
    for i, (y, r) in enumerate(zip(df["year"], df["ann_ret"])):
        ax2.annotate(f"{r*100:+.1f}%", (i, r * 100), ha="center",
                     va="bottom" if r >= 0 else "top",
                     fontsize=7.5, color="#444")

    fig.suptitle("H2 REV — year-by-year stability",
                 x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "h2_by_year.pdf")
    fig.savefig(OUT_DIR / "h2_by_year.png", dpi=160)
    plt.close(fig)
    print("wrote h2_by_year.{pdf,png}")


def render_vix() -> None:
    df = pd.read_csv(BY_VIX)
    t_star = bonferroni_threshold(12, 0.05)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(9.5, 3.5), gridspec_kw={"width_ratios": [1, 1]}
    )

    labels = [f"{q}\n(VIX {lo:.0f}–{hi:.0f})"
              for q, lo, hi in zip(df["quintile"], df["vix_low"], df["vix_high"])]
    x = range(len(df))
    ax1.bar(x, df["sharpe"], color=MEANREV, edgecolor="#333", linewidth=0.5)
    ax1.set_xticks(list(x)); ax1.set_xticklabels(labels, fontsize=8)
    ax1.axhline(0, color="#333", linewidth=0.6)
    ax1.set_ylabel("Sharpe ratio")
    ax1.set_title("(a) Sharpe by VIX regime", fontweight="bold")
    style_axis(ax1, grid="y")
    for i, sr in enumerate(df["sharpe"]):
        ax1.annotate(f"{sr:+.2f}", (i, sr), ha="center",
                     va="bottom", fontsize=8, color="#444")

    ax2.bar(x, df["t"], color=MEANREV, edgecolor="#333", linewidth=0.5)
    ax2.set_xticks(list(x)); ax2.set_xticklabels(labels, fontsize=8)
    ax2.axhline(0, color="#333", linewidth=0.6)
    ax2.axhline(t_star, color=NOTECOL, linestyle="--", linewidth=0.8,
                label=f"$t^*={t_star:.2f}$")
    ax2.set_ylabel(r"$t$-statistic")
    ax2.set_title(r"(b) $t$-stat by VIX regime (within-bucket)", fontweight="bold")
    ax2.legend(loc="upper left")
    style_axis(ax2, grid="y")

    fig.suptitle("H2 REV — stability across VIX regimes",
                 x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT_DIR / "h2_by_vix_quintile.pdf")
    fig.savefig(OUT_DIR / "h2_by_vix_quintile.png", dpi=160)
    plt.close(fig)
    print("wrote h2_by_vix_quintile.{pdf,png}")


def main() -> None:
    apply()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render_year()
    render_vix()


if __name__ == "__main__":
    main()
