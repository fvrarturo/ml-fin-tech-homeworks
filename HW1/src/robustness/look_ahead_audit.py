"""Look-ahead audit — Work1.md §8.6.

For each horizon panel, shift the signal back by one additional rebalance
(i.e., use s_{t-1} instead of s_t to predict r^fwd_t) and rerun the backtest.
A strategy that's genuinely ex-ante will lose some Sharpe but remain
directional; a strategy with look-ahead leakage will collapse completely
(Sharpe → 0 or invert).

We shift per ticker, per rebalance — same for H2's intraday signal.

    Expected decay: 10% – 70% of Sharpe lost. Catastrophic drop (>90%)
    flags a bug.

Output:
    data/processed/robustness/look_ahead_audit.csv
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.engine import run_horizon
from src.backtest.metrics import bonferroni_threshold, summarize
from src.cli.run_all import HORIZON_CONFIG

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT = PROCESSED / "robustness" / "look_ahead_audit.csv"


def main() -> None:
    rows = []
    for h, cfg in HORIZON_CONFIG.items():
        panel_path = ROOT / "data" / "interim" / f"{h.lower()}_panel.parquet"
        if not panel_path.exists():
            continue
        panel = pd.read_parquet(panel_path)

        # Shifted signal: use prior rebalance's signal. Within ticker, sort by
        # date, shift(1).
        panel_shift = panel.sort_values(["ticker", "date"]).copy()
        panel_shift["signal"] = (
            panel_shift.groupby("ticker", sort=False)["signal"].shift(1)
        )
        panel_shift = panel_shift.dropna(subset=["signal", "ret_fwd"])

        for label, df in [("baseline", panel), ("shift_back_1", panel_shift)]:
            pnl = run_horizon(df, cost_bps=cfg["cost_bps"],
                              round_trip_each_rebalance=cfg.get("round_trip", False))
            stats = summarize(pnl, periods_per_year=cfg["periods_per_year"],
                              nw_lags=cfg["nw_lags"])
            for fam in ("mom", "rev"):
                s = stats.loc[f"{fam}_net"]
                t_col = "t_stat_nw" if cfg["nw_lags"] else "t_stat"
                rows.append({
                    "horizon": h,
                    "variant": label,
                    "family": fam.upper(),
                    "sharpe": float(s["sharpe"]),
                    "t": float(s[t_col]) if t_col in s else float(s["t_stat"]),
                })
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(OUT, index=False)

    # Pivot for readability
    piv = df.pivot_table(index=["horizon", "family"], columns="variant",
                          values=["sharpe", "t"])
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    piv["sharpe_retained_pct"] = (
        piv["sharpe_shift_back_1"] / piv["sharpe_baseline"] * 100
    )

    t_star = bonferroni_threshold(12, 0.05)
    print(f"Bonferroni t* = {t_star:.3f}")
    print("\nLook-ahead audit (baseline vs signal shifted back 1 period):")
    cols = ["sharpe_baseline", "sharpe_shift_back_1", "sharpe_retained_pct",
            "t_baseline", "t_shift_back_1"]
    print(piv[cols].round(2).to_string())
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
