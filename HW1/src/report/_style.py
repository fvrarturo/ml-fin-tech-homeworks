"""Shared matplotlib style + palette for ICM figures.

Colors match the LaTeX source in `_info/main_plan.tex` so figures and prose
use the same visual identity:

    mitred   (163, 31, 52)   — headline colour, risk callouts
    accent   (20, 80, 140)   — neutral accent
    meanrev  (50, 120, 90)   — REV strategies (green)
    momcol   (190, 80, 50)   — MOM strategies (red)
    softgray (245, 245, 245) — background fills
    notecol  (50, 90, 130)   — annotations

Every figure in the ICM that includes MOM and REV series uses the same
two colours so a reader can identify them at a glance.
"""
from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt


MITRED = "#A31F34"
ACCENT = "#14508C"
MEANREV = "#327858"
MOMCOL = "#BE5032"
SOFTGRAY = "#F5F5F5"
NOTECOL = "#325A82"

GRID_KW = dict(linestyle="--", linewidth=0.4, color="#999", alpha=0.5)


def apply() -> None:
    """Install project-wide matplotlib defaults.

    Idempotent. Call once at the top of any script that produces figures.
    """
    mpl.rcParams.update({
        "figure.figsize": (6.5, 3.8),
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,

        "font.family": "serif",
        "font.size": 9.5,
        "axes.titlesize": 10.5,
        "axes.labelsize": 9.5,
        "legend.fontsize": 8.5,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,

        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#333",
        "axes.linewidth": 0.7,
        "axes.titlelocation": "left",
        "axes.titlepad": 8,
        "axes.labelpad": 4,

        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.color": "#333",
        "ytick.color": "#333",

        "grid.linestyle": "--",
        "grid.linewidth": 0.4,
        "grid.color": "#999",
        "grid.alpha": 0.5,

        "legend.frameon": False,
        "legend.handlelength": 1.5,

        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def mom_color(alpha: float = 1.0) -> tuple:
    """Matplotlib-style RGBA tuple for MOM strategies."""
    rgb = mpl.colors.to_rgb(MOMCOL)
    return (*rgb, alpha)


def rev_color(alpha: float = 1.0) -> tuple:
    rgb = mpl.colors.to_rgb(MEANREV)
    return (*rgb, alpha)


def style_axis(ax: plt.Axes, *, grid: str = "y") -> None:
    """Standard per-axis tidy-up used by every chart."""
    if grid == "y":
        ax.yaxis.grid(True, **GRID_KW)
        ax.xaxis.grid(False)
    elif grid == "x":
        ax.xaxis.grid(True, **GRID_KW)
        ax.yaxis.grid(False)
    elif grid == "both":
        ax.grid(True, **GRID_KW)
    else:
        ax.grid(False)
    ax.set_axisbelow(True)


def annotate_bonferroni(ax: plt.Axes, t_star: float, *, axis: str = "y") -> None:
    """Dashed line at ±t_star with inline label."""
    kw = dict(color=NOTECOL, linestyle="--", linewidth=0.8, alpha=0.8)
    if axis == "y":
        ax.axhline(t_star, **kw)
        ax.axhline(-t_star, **kw)
        ax.annotate(f"$t^*={t_star:.2f}$", xy=(0.99, t_star), xycoords=("axes fraction", "data"),
                    ha="right", va="bottom", color=NOTECOL, fontsize=8.5)
    else:
        ax.axvline(t_star, **kw)
        ax.axvline(-t_star, **kw)
