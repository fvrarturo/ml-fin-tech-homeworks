"""Figure 3 — the headline cross-horizon comparison chart.

Left panel:  net Sharpe per horizon, MOM and REV side-by-side bars.
Right panel: (optional) t-stat panel with Bonferroni line at 2.87.

One figure renders to both PDF (for LaTeX \\includegraphics) and PNG (for
Markdown / quick inspection).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.backtest.metrics import bonferroni_threshold
from src.report._style import (
    MEANREV,
    MOMCOL,
    NOTECOL,
    annotate_bonferroni,
    apply,
    style_axis,
)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT_DIR = ROOT / "icm" / "figures"
HORIZONS = ["H1", "H2", "H3", "H4", "H5", "H6"]
NW_HORIZONS = {"H6"}


def load_rows() -> pd.DataFrame:
    rows = []
    for h in HORIZONS:
        p = PROCESSED / f"{h.lower()}_stats.csv"
        if not p.exists():
            continue
        s = pd.read_csv(p, index_col=0)
        use_nw = h in NW_HORIZONS
        t_col = "t_stat_nw" if use_nw else "t_stat"
        rows.append({
            "horizon": h,
            "mom_sr": float(s.loc["mom_net", "sharpe"]),
            "rev_sr": float(s.loc["rev_net", "sharpe"]),
            "mom_t":  float(s.loc["mom_net", t_col]),
            "rev_t":  float(s.loc["rev_net", t_col]),
        })
    return pd.DataFrame(rows)


def render() -> None:
    apply()
    df = load_rows()
    t_star = bonferroni_threshold(12, 0.05)

    fig, (ax_sr, ax_t) = plt.subplots(
        1, 2, figsize=(9.5, 3.8), gridspec_kw={"width_ratios": [1, 1]}
    )

    # --- Left: net Sharpe ----------------------------------------------------
    x = np.arange(len(df))
    w = 0.38
    ax_sr.bar(x - w / 2, df["mom_sr"], width=w, color=MOMCOL,
              edgecolor="#333", linewidth=0.5, label="MOM (momentum)")
    ax_sr.bar(x + w / 2, df["rev_sr"], width=w, color=MEANREV,
              edgecolor="#333", linewidth=0.5, label="REV (mean-reversion)")
    ax_sr.axhline(0, color="#333", linewidth=0.6)
    ax_sr.set_xticks(x)
    ax_sr.set_xticklabels(df["horizon"])
    ax_sr.set_ylabel("Annualized Sharpe ratio (net of cost)")
    ax_sr.set_title("(a) Net Sharpe by horizon")
    ax_sr.legend(loc="lower right")
    style_axis(ax_sr, grid="y")

    # H1 annotation: the -34 bars dwarf everything else, so note them
    h1_i = df.index[df["horizon"] == "H1"]
    if len(h1_i):
        i = h1_i[0]
        # Clip the axis; annotate the off-scale H1 values textually
        ax_sr.set_ylim(-8, max(3.2, df["rev_sr"].max() * 1.15))
        ax_sr.annotate(
            f"H1 off-scale:\nMOM {df.loc[i,'mom_sr']:+.1f}, "
            f"REV {df.loc[i,'rev_sr']:+.1f}\n(cost-dominated)",
            xy=(i, -7.5), xytext=(i, -3.5),
            ha="center", color="#444", fontsize=7.5,
            arrowprops=dict(arrowstyle="->", color="#666", lw=0.5),
        )

    # --- Right: t-stat -------------------------------------------------------
    ax_t.bar(x - w / 2, df["mom_t"], width=w, color=MOMCOL,
             edgecolor="#333", linewidth=0.5)
    ax_t.bar(x + w / 2, df["rev_t"], width=w, color=MEANREV,
             edgecolor="#333", linewidth=0.5)
    ax_t.axhline(0, color="#333", linewidth=0.6)
    ax_t.set_xticks(x)
    ax_t.set_xticklabels(df["horizon"])
    ax_t.set_ylabel(r"$t$-statistic vs zero")
    ax_t.set_title(r"(b) $t$-stat (H6 uses Newey-West $q=6$)")
    annotate_bonferroni(ax_t, t_star)
    # Clip for readability
    ax_t.set_ylim(max(-12, df["mom_t"].min() * 1.1),
                  max(10, df["rev_t"].max() * 1.15))
    if (df["mom_t"] < -12).any() or (df["mom_t"] > 10).any():
        i = int(df["mom_t"].abs().idxmax())
        ax_t.annotate(
            f"H1 off-scale\n({df.loc[i,'mom_t']:+.0f} / {df.loc[i,'rev_t']:+.0f})",
            xy=(i, -11.5), xytext=(i, -7.5), ha="center",
            color="#444", fontsize=7.5,
            arrowprops=dict(arrowstyle="->", color="#666", lw=0.5),
        )
    style_axis(ax_t, grid="y")

    fig.suptitle("Figure 3 — Horizon comparison of tercile long-short P&L",
                 x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "figure3_horizons.pdf")
    fig.savefig(OUT_DIR / "figure3_horizons.png", dpi=160)
    plt.close(fig)
    print(f"wrote {OUT_DIR.relative_to(ROOT)}/figure3_horizons.{{pdf,png}}")


if __name__ == "__main__":
    render()
