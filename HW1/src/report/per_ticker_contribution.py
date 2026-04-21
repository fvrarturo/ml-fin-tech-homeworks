"""Per-ticker P&L contribution for H2 REV.

Diversification sanity: how much of the strategy's return comes from a
handful of tickers vs being spread across the cross-section?

Contribution computation: for each ticker i, total P&L = sum over days of
(w_rev_{i,t} * ret_fwd_{i,t}). We rerun the tercile construction on the
H2 panel and decompose.

Output:
    icm/figures/h2_ticker_contribution.{pdf,png}
    data/processed/robustness/h2_ticker_contribution.csv
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from src.backtest.portfolio import terciles_longshort
from src.report._style import MEANREV, NOTECOL, apply, style_axis

ROOT = Path(__file__).resolve().parents[2]
H2 = ROOT / "data" / "interim" / "h2_panel.parquet"
OUT_CSV = ROOT / "data" / "processed" / "robustness" / "h2_ticker_contribution.csv"
OUT_FIG = ROOT / "icm" / "figures"


def compute() -> pd.DataFrame:
    panel = pd.read_parquet(H2)
    p = terciles_longshort(panel)
    p["pnl_contrib"] = p["w_rev"] * p["ret_fwd"]
    # Total P&L per ticker (sum of all daily contributions)
    out = (
        p.groupby("ticker")["pnl_contrib"]
        .agg(total="sum", mean="mean", std="std", n="size")
    )
    out["ann_ret_contrib"] = out["mean"] * 252  # each ticker's share of ann ret
    return out.sort_values("total", ascending=False)


def render(df: pd.DataFrame) -> None:
    apply()
    fig, ax = plt.subplots(figsize=(8.0, 4.8))

    df = df.sort_values("ann_ret_contrib", ascending=True)
    colors = [MEANREV if v >= 0 else "#A33" for v in df["ann_ret_contrib"]]
    ax.barh(df.index, df["ann_ret_contrib"] * 100, color=colors,
            edgecolor="#333", linewidth=0.4)
    ax.axvline(0, color="#666", linewidth=0.5)
    ax.set_xlabel("Contribution to annualized REV return (percentage points)")
    ax.set_title("H2 REV — per-ticker contribution to annualized return",
                 fontweight="bold")
    style_axis(ax, grid="x")

    # Cumulative contribution: fraction of total return from top-N tickers
    total = df["ann_ret_contrib"].sum()
    sorted_desc = df.sort_values("ann_ret_contrib", ascending=False)
    cum = sorted_desc["ann_ret_contrib"].cumsum() / total * 100
    top5 = float(cum.iloc[4]) if len(cum) >= 5 else float("nan")
    top10 = float(cum.iloc[9]) if len(cum) >= 10 else float("nan")

    note = (
        f"Top-5 tickers contribute {top5:.0f}% of total\n"
        f"Top-10 tickers contribute {top10:.0f}% of total\n"
        f"N tickers = {len(df)}"
    )
    ax.text(0.98, 0.05, note, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8.5,
            bbox=dict(boxstyle="round,pad=0.35", fc="white",
                      ec="#AAA", alpha=0.85))

    fig.tight_layout()
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG / "h2_ticker_contribution.pdf")
    fig.savefig(OUT_FIG / "h2_ticker_contribution.png", dpi=160)
    plt.close(fig)
    print(f"wrote h2_ticker_contribution.{{pdf,png}}   "
          f"(top-5 = {top5:.0f}% of ann ret)")


def main() -> None:
    df = compute()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.round(6).to_csv(OUT_CSV)
    render(df)


if __name__ == "__main__":
    main()
