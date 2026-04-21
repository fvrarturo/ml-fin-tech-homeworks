"""Per-horizon equity curve + rolling drawdown panel.

For the two ICM strategies:
    icm/figures/equity_h2_rev.pdf   (Best REV — clears Bonferroni)
    icm/figures/equity_h6_mom.pdf   (Best MOM — fallback, fails Bonferroni)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.report._style import (
    ACCENT,
    MEANREV,
    MOMCOL,
    NOTECOL,
    apply,
    style_axis,
)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT_DIR = ROOT / "icm" / "figures"


def _drawdown(wealth: pd.Series) -> pd.Series:
    return wealth / wealth.cummax() - 1.0


def _render_one(horizon: str, family: str, title: str, color: str) -> None:
    """family ∈ {'mom', 'rev'}"""
    pnl = pd.read_parquet(PROCESSED / f"{horizon.lower()}_pnl.parquet")
    pnl.index = pd.to_datetime(pnl.index)
    gross = pnl[f"{family}_gross"]
    net = pnl[f"{family}_net"]
    w_gross = (1 + gross).cumprod()
    w_net = (1 + net).cumprod()
    dd_net = _drawdown(w_net)

    stats = pd.read_csv(PROCESSED / f"{horizon.lower()}_stats.csv", index_col=0)
    s = stats.loc[f"{family}_net"]
    ann_ret, ann_vol, sharpe = s["ann_ret"], s["ann_vol"], s["sharpe"]
    t_col = "t_stat_nw" if horizon == "H6" else "t_stat"
    t = s[t_col]
    mdd = s["max_dd"]

    fig = plt.figure(figsize=(7.2, 4.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.08)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    ax1.plot(w_gross.index, w_gross.values, color=color, linewidth=0.9,
             alpha=0.45, label="Gross")
    ax1.plot(w_net.index, w_net.values, color=color, linewidth=1.4,
             label="Net of 1.5 bps/side")
    ax1.axhline(1.0, color="#666", linewidth=0.5)
    ax1.set_ylabel("Cumulative wealth (×)")
    # Push title above the stats line (y=1.02) so the two don't overlap.
    ax1.set_title(title, fontweight="bold", y=1.08)
    ax1.legend(loc="upper left")
    style_axis(ax1, grid="y")

    stats_text = (
        f"$N$={int(s['n_obs']):,}   "
        f"ann.ret={ann_ret:+.2%}   ann.vol={ann_vol:.2%}   "
        f"SR={sharpe:+.2f}   $t$={t:+.2f}"
        + ("$^{NW}$" if horizon == "H6" else "")
        + f"   MDD={mdd:.1%}"
    )
    ax1.text(0.005, 1.02, stats_text, transform=ax1.transAxes,
             va="bottom", fontsize=8.5, color="#333")

    # Drawdown panel
    ax2.fill_between(dd_net.index, dd_net.values, 0, color=color, alpha=0.35,
                     linewidth=0)
    ax2.plot(dd_net.index, dd_net.values, color=color, linewidth=0.8)
    ax2.axhline(0, color="#666", linewidth=0.5)
    ax2.set_ylabel("Drawdown")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    style_axis(ax2, grid="y")
    fig.autofmt_xdate()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"equity_{horizon.lower()}_{family}"
    fig.savefig(OUT_DIR / f"{stem}.pdf")
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=160)
    plt.close(fig)
    print(f"wrote {stem}.{{pdf,png}}")


def render() -> None:
    apply()
    # Best REV — the headline ICM strategy
    _render_one("H2", "rev",
                "H2 REV — intraday first-30 → rest-of-day mean reversion",
                MEANREV)
    # Fallback MOM — H6 Jegadeesh-Titman
    _render_one("H6", "mom",
                "H6 MOM — 6-month Jegadeesh-Titman momentum (skip-1-month)",
                MOMCOL)


if __name__ == "__main__":
    render()
