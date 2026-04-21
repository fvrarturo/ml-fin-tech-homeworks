"""Figure — per-horizon signal lookback and forward-hold timelines.

Visual reference for Section 3--4 that makes the window alignment
unambiguous. Each horizon row shows:
    * the signal window $W_{past}$ (lookback, in trading days, left of t)
    * the forward-hold window $W_{fwd}$ (to the right of t)
    * the H6 skip-1-month gap between signal-end and $t$
    * the H6 forward-hold overlap with the next rebalance

Output:
    icm/figures/windowing_diagram.{pdf,png}
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from src.report._style import ACCENT, MEANREV, MOMCOL, NOTECOL, apply, style_axis

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "icm" / "figures" / "windowing_diagram"

# (label, past_start, past_end, skip_gap_present, fwd_start, fwd_end,
#  next_rebalance_days, notes)
# All offsets are in trading days from rebalance date t (=0).
SPECS = [
    # H1 is one bar = 30 min ≈ 1/13 day — show as "1 bar" annotation
    ("H1 (30 min)",    -0.08, 0.0, False, 0.0, 0.08,  0.08,
     r"bar $k\!-\!1$ $\to$ bar $k\!+\!1$; bar = 30 min"),
    ("H2 (intraday)",  -0.25, 0.0, False, 0.0, 0.75,  1.0,
     "first $\\sim$30 min $\\to$ rest-of-day (same session)"),
    ("H3 (1 day)",     -1.0,  0.0, False, 0.0, 1.0,   1.0,
     "today's ret $\\to$ tomorrow's ret"),
    ("H4 (5 day)",     -5.0,  0.0, False, 0.0, 5.0,   5.0,
     "week ending $t$ $\\to$ next week (non-overlap)"),
    ("H5 (21 day)",    -21.0, 0.0, False, 0.0, 21.0,  21.0,
     "month ending $t$ $\\to$ next month (non-overlap)"),
    ("H6 (126 day)",   -125.0, -21.0, True, 0.0, 126.0, 21.0,
     "5-month skip-ret $\\to$ 6-month hold (overlap)"),
]


def render() -> None:
    apply()
    fig, ax = plt.subplots(figsize=(9.0, 4.4))

    past_color = MEANREV
    fwd_color = MOMCOL
    bar_h = 0.55

    for i, (lab, p0, p1, skip, f0, f1, next_t, note) in enumerate(SPECS):
        y = -i
        # Signal (past) window — green
        ax.add_patch(mpatches.FancyBboxPatch(
            (p0, y - bar_h/2), p1 - p0, bar_h,
            boxstyle="round,pad=0.01", linewidth=0.4,
            facecolor=past_color, edgecolor="#333", alpha=0.8))
        # Skip gap (H6 only) — hatched / note
        if skip:
            ax.add_patch(mpatches.FancyBboxPatch(
                (p1, y - bar_h/2), 0 - p1, bar_h,
                boxstyle="round,pad=0.01", linewidth=0.4,
                facecolor="white", edgecolor="#333",
                hatch="////", alpha=0.7))
        # Forward hold — red/orange
        ax.add_patch(mpatches.FancyBboxPatch(
            (f0, y - bar_h/2), f1 - f0, bar_h,
            boxstyle="round,pad=0.01", linewidth=0.4,
            facecolor=fwd_color, edgecolor="#333", alpha=0.75))
        # Next rebalance tick (shows overlap for H6)
        if next_t < (f1 - f0) - 1e-9:
            ax.vlines(next_t, y - bar_h/2 - 0.05, y + bar_h/2 + 0.05,
                       color=NOTECOL, linestyle="--", linewidth=1.1)
            ax.annotate("next\nrebal.", xy=(next_t, y + bar_h/2 + 0.06),
                        xytext=(next_t, y + bar_h/2 + 0.3),
                        fontsize=7, color=NOTECOL, ha="center",
                        arrowprops=dict(arrowstyle="->",
                                         color=NOTECOL, lw=0.5))
        # Horizon label at left
        ax.text(-135, y, lab, va="center", ha="right",
                 fontsize=9, fontweight="bold")
        # Per-row note at right
        ax.text(133, y, note, va="center", ha="left",
                 fontsize=7.5, color="#555")

    # Rebalance axis marker at t=0
    ax.vlines(0, 0.6, -len(SPECS) + 0.4,
               color="#111", linewidth=1.1)
    ax.annotate(r"rebalance $t$", xy=(0, 0.55), xytext=(0, 1.05),
                 ha="center", fontsize=9, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color="#111", lw=0.6))

    # Axis cosmetics
    ax.set_xlim(-140, 140)
    ax.set_ylim(-len(SPECS) - 0.3, 1.6)
    ax.set_yticks([])
    ax.set_xlabel("Trading days from rebalance date $t$ "
                   "(H1, H2 zoomed; annotations at right)")
    ax.set_xticks([-125, -21, 0, 21, 126])
    ax.set_xticklabels(["$t-125$", "$t-21$", "$t$", "$t+21$", "$t+126$"])
    ax.spines["left"].set_visible(False)
    ax.xaxis.grid(True, linestyle="--", linewidth=0.4, color="#CCC", alpha=0.6)
    ax.yaxis.grid(False)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    # Legend
    legend_patches = [
        mpatches.Patch(facecolor=past_color, edgecolor="#333",
                        alpha=0.8, label="Signal window $W_{\\mathrm{past}}$"),
        mpatches.Patch(facecolor="white", edgecolor="#333",
                        hatch="////", alpha=0.8,
                        label="Skip gap (H6 only, $-21$d to $t$)"),
        mpatches.Patch(facecolor=fwd_color, edgecolor="#333",
                        alpha=0.75, label="Forward hold $W_{\\mathrm{fwd}}$"),
    ]
    ax.legend(handles=legend_patches, loc="lower left",
              bbox_to_anchor=(-0.02, -0.25), ncol=3, frameon=False, fontsize=8.5)

    fig.suptitle("Per-horizon signal / forward-hold windowing",
                  x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0.02, 1, 0.94))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT.with_suffix(".pdf"))
    fig.savefig(OUT.with_suffix(".png"), dpi=160)
    plt.close(fig)
    print(f"wrote {OUT.relative_to(ROOT)}.{{pdf,png}}")


if __name__ == "__main__":
    render()
