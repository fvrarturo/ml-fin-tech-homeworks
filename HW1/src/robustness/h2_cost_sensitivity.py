"""H2 cost-sensitivity curve + break-even cost.

Reruns H2 at a grid of per-side costs and reports where net Sharpe crosses
zero and where the t-stat drops below the Bonferroni threshold. H2 round-trips
every day (turnover fixed at 2.0), so the relationship is exactly

    ann_ret_net(c) = ann_ret_gross - 2 * c * periods_per_year

and the break-even is closed-form, but we still materialize the full curve
for the IC exhibit.

Output:
    data/processed/robustness/h2_cost_sensitivity.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import run_horizon
from src.backtest.metrics import bonferroni_threshold, summarize

ROOT = Path(__file__).resolve().parents[2]
H2_PANEL = ROOT / "data" / "interim" / "h2_panel.parquet"
OUT = ROOT / "data" / "processed" / "robustness" / "h2_cost_sensitivity.csv"

COST_GRID_BPS = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0, 20.0]


def main() -> None:
    panel = pd.read_parquet(H2_PANEL)
    t_star = bonferroni_threshold(12, 0.05)

    rows = []
    for c in COST_GRID_BPS:
        pnl = run_horizon(panel, cost_bps=c, round_trip_each_rebalance=True)
        stats = summarize(pnl, periods_per_year=252)
        rev = stats.loc["rev_net"]
        mom = stats.loc["mom_net"]
        rows.append({
            "cost_bps_per_side": c,
            "round_trip_bps":    2 * c,
            "rev_ann_ret":   float(rev["ann_ret"]),
            "rev_sharpe":    float(rev["sharpe"]),
            "rev_t":         float(rev["t_stat"]),
            "rev_clears_bonf": bool(abs(rev["t_stat"]) > t_star),
            "mom_sharpe":    float(mom["sharpe"]),
            "mom_t":         float(mom["t_stat"]),
        })
    df = pd.DataFrame(rows)

    # Closed-form break-evens (gross ret and vol independent of c; t ∝ mean/vol).
    gross = run_horizon(panel, cost_bps=0.0, round_trip_each_rebalance=True)
    mu_gross = gross["rev_gross"].mean()
    sd = gross["rev_gross"].std(ddof=1)
    n = len(gross)
    # c_zero: net Sharpe = 0 → mu - 2c = 0 → c = mu / 2
    c_zero_bps = (mu_gross / 2.0) * 1e4
    # c_bonf: t-stat = t_star → (mu - 2c)/sd * √n = t_star
    c_bonf_bps = ((mu_gross - t_star * sd / np.sqrt(n)) / 2.0) * 1e4

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.round(6).to_csv(OUT, index=False)

    print("H2 cost sensitivity (grid, per-side bps):")
    disp = df.copy()
    for col in ("rev_ann_ret",):
        disp[col] = disp[col].apply(lambda x: f"{x:+.2%}")
    for col in ("rev_sharpe", "rev_t", "mom_sharpe", "mom_t"):
        disp[col] = disp[col].apply(lambda x: f"{x:+.3f}")
    print(disp.to_string(index=False))
    print()
    print(f"Gross daily P&L mean = {mu_gross*1e4:.2f} bps, σ = {sd*1e4:.2f} bps, N = {n}")
    print(f"Break-even (net SR = 0)            → per-side c = {c_zero_bps:.2f} bps  (round-trip {2*c_zero_bps:.1f} bps)")
    print(f"Break-even (t = Bonferroni 2.87)   → per-side c = {c_bonf_bps:.2f} bps  (round-trip {2*c_bonf_bps:.1f} bps)")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
