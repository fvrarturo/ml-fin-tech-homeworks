"""Plot the H2 cost-sensitivity curve with break-even annotations.

Reads `data/processed/robustness/h2_cost_sensitivity.csv` produced earlier.
Emits `icm/figures/h2_cost_sensitivity.{pdf,png}`.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.backtest.metrics import bonferroni_threshold
from src.report._style import MEANREV, NOTECOL, annotate_bonferroni, apply, style_axis

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "data" / "processed" / "robustness" / "h2_cost_sensitivity.csv"
OUT_DIR = ROOT / "icm" / "figures"


def render() -> None:
    apply()
    df = pd.read_csv(CSV).sort_values("cost_bps_per_side")
    t_star = bonferroni_threshold(12, 0.05)

    # Solve break-evens by linear interp of the curves.
    import numpy as np

    def _crossing(y_col: str, y_target: float) -> float:
        y = df[y_col].values
        x = df["cost_bps_per_side"].values
        # Find the first interval where the curve crosses the target.
        for i in range(len(x) - 1):
            y0, y1 = y[i], y[i + 1]
            if (y0 - y_target) * (y1 - y_target) <= 0 and y1 != y0:
                frac = (y_target - y0) / (y1 - y0)
                return x[i] + frac * (x[i + 1] - x[i])
        return float("nan")

    c_zero = _crossing("rev_sharpe", 0.0)
    c_bonf = _crossing("rev_t", t_star)

    fig, (ax_sr, ax_t) = plt.subplots(1, 2, figsize=(9.5, 3.6))
    ax_sr.plot(df["cost_bps_per_side"], df["rev_sharpe"],
               marker="o", markersize=3, color=MEANREV, linewidth=1.5,
               label="REV")
    ax_sr.axhline(0, color="#666", linewidth=0.5)
    ax_sr.axvline(c_zero, color=NOTECOL, linestyle="--", linewidth=0.8)
    ax_sr.annotate(
        f"break-even\n$c^*$ = {c_zero:.2f} bps",
        xy=(c_zero, 0), xytext=(c_zero + 0.5, 2),
        color=NOTECOL, fontsize=8,
        arrowprops=dict(arrowstyle="->", color=NOTECOL, lw=0.5),
    )
    ax_sr.set_xlabel("Per-side cost (bps)")
    ax_sr.set_ylabel("Net Sharpe ratio")
    ax_sr.set_title("(a) H2 REV net Sharpe vs cost")
    style_axis(ax_sr, grid="y")

    ax_t.plot(df["cost_bps_per_side"], df["rev_t"],
              marker="o", markersize=3, color=MEANREV, linewidth=1.5,
              label="REV")
    ax_t.axhline(0, color="#666", linewidth=0.5)
    ax_t.axhline(t_star, color=NOTECOL, linestyle="--", linewidth=0.8)
    ax_t.axvline(c_bonf, color=NOTECOL, linestyle="--", linewidth=0.8)
    ax_t.annotate(
        f"Bonferroni\n$c^*$ = {c_bonf:.2f} bps",
        xy=(c_bonf, t_star), xytext=(c_bonf + 0.5, t_star + 3),
        color=NOTECOL, fontsize=8,
        arrowprops=dict(arrowstyle="->", color=NOTECOL, lw=0.5),
    )
    ax_t.set_xlabel("Per-side cost (bps)")
    ax_t.set_ylabel(r"$t$-statistic")
    ax_t.set_title(r"(b) H2 REV $t$-stat vs cost")
    style_axis(ax_t, grid="y")

    fig.suptitle("H2 REV cost sensitivity",
                 x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "h2_cost_sensitivity.pdf")
    fig.savefig(OUT_DIR / "h2_cost_sensitivity.png", dpi=160)
    plt.close(fig)
    print(f"wrote h2_cost_sensitivity.{{pdf,png}}   "
          f"(break-even: Sharpe=0 @ {c_zero:.2f}, Bonferroni @ {c_bonf:.2f} bps)")


if __name__ == "__main__":
    render()
