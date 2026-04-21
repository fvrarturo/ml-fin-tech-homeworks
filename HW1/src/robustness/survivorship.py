"""Survivorship robustness — Work1.md §8.5.

Re-run every horizon's backtest restricted to the 23 always-present tickers
(those with full 2,514-day membership tenure per `dj30_tenure.csv`).

Expected direction (Work1.md §13.1): survivorship bias typically inflates
momentum Sharpe (winners are added to the index because they kept winning,
losers are dropped). Restricting to always-present should attenuate MOM
Sharpes and have a smaller effect on REV.

Outputs:
    data/processed/robustness/survivorship_check.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.engine import run_horizon
from src.backtest.metrics import bonferroni_threshold, summarize
from src.cli.run_all import HORIZON_CONFIG

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
TENURE = ROOT / "data" / "reference" / "dj30_tenure.csv"
OUT = PROCESSED / "robustness" / "survivorship_check.csv"


def _always_present() -> set[str]:
    tenure = pd.read_csv(TENURE)
    max_days = tenure["n_days"].max()
    always = set(tenure[tenure["n_days"] == max_days]["ticker"].astype(str))
    return always


def main() -> None:
    always = _always_present()
    print(f"always-present tickers: {len(always)} — {sorted(always)}")

    rows = []
    for h, cfg in HORIZON_CONFIG.items():
        panel_path = ROOT / "data" / "interim" / f"{h.lower()}_panel.parquet"
        if not panel_path.exists():
            continue
        panel = pd.read_parquet(panel_path)
        panel_always = panel[panel["ticker"].isin(always)].copy()
        if panel_always.empty:
            continue

        for label, df in [("pit", panel), ("always", panel_always)]:
            pnl = run_horizon(df, cost_bps=cfg["cost_bps"],
                              round_trip_each_rebalance=cfg.get("round_trip", False))
            stats = summarize(pnl, periods_per_year=cfg["periods_per_year"],
                              nw_lags=cfg["nw_lags"])
            for fam in ("mom", "rev"):
                s = stats.loc[f"{fam}_net"]
                t_col = "t_stat_nw" if cfg["nw_lags"] else "t_stat"
                rows.append({
                    "horizon": h,
                    "universe": label,
                    "family": fam.upper(),
                    "n_obs": int(s["n_obs"]),
                    "ann_ret": float(s["ann_ret"]),
                    "sharpe": float(s["sharpe"]),
                    "t": float(s[t_col]) if t_col in s else float(s["t_stat"]),
                    "max_dd": float(s["max_dd"]),
                })
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(OUT, index=False)

    # Pivot to diff for readability
    piv = df.pivot_table(index=["horizon", "family"],
                          columns="universe",
                          values=["sharpe", "t"])
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    piv["sharpe_delta"] = piv["sharpe_always"] - piv["sharpe_pit"]

    t_star = bonferroni_threshold(12, 0.05)
    print(f"\nBonferroni t* = {t_star:.3f}")
    print("\nSharpe / t-stat under PIT vs always-present universe:")
    print(piv.round(3).to_string())
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
