"""H3 — one-day close-to-close reversal (Lehmann 1990).

Rebalance every trading day. Signal = today's total return; forward = next
day's total return. PIT-filtered against DJ30 membership.

Output: data/interim/h3_panel.parquet with columns [date, ticker, signal, ret_fwd].
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._common import apply_pit_filter, load_daily_returns, log_panel_stats

OUT = Path(__file__).resolve().parents[2] / "data" / "interim" / "h3_panel.parquet"


def build() -> pd.DataFrame:
    d = load_daily_returns()
    d["signal"] = d["ret"]
    d["ret_fwd"] = d.groupby("ticker", sort=False)["ret"].shift(-1)
    d = d.dropna(subset=["signal", "ret_fwd"])
    d = apply_pit_filter(d[["date", "ticker", "signal", "ret_fwd"]], strict=True)
    return d[["date", "ticker", "signal", "ret_fwd"]].reset_index(drop=True)


def main() -> None:
    panel = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUT, index=False)
    log_panel_stats("H3", panel)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
