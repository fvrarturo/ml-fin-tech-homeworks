"""Half-spread-sourced cost model for H2 REV.

Instead of charging a flat 1.5 bps per side (round-trip 3 bps), we
use the actual per-(ticker, date) quoted spread from the WRDS iid_ms
panel. Per-side execution is assumed to cross half the quoted spread,
so per-day cost per dollar traded is

    c_{i,t} = (quoted_spread_bps_{i,t} / 2) * 2 = quoted_spread_bps

(The half-spread for entry + half-spread for exit gives one full spread
per day on dollar-neutral rebalance.) Additionally we add a fixed 0.5
bps per side impact floor to reflect realistic implementation friction
above the quoted spread at non-trivial size.

Compares four scenarios:
    1. Flat 1.5 bps/side (the paper's headline).
    2. Flat 1.0 bps/side (aggressive — mid-or-better execution).
    3. Half-spread-sourced (optimistic, pure half-spread crossing).
    4. Half-spread + 0.5 bps impact floor (realistic).

Outputs:
    data/processed/robustness/h2_halfspread_cost.csv
    icm/tables/h2_halfspread_cost.tex
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.metrics import bonferroni_threshold, summarize
from src.backtest.portfolio import terciles_longshort

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "data" / "interim" / "h2_panel.parquet"
INTRA = ROOT / "data" / "interim" / "intraday.parquet"
OUT_CSV = ROOT / "data" / "processed" / "robustness" / "h2_halfspread_cost.csv"
OUT_TEX = ROOT / "icm" / "tables" / "h2_halfspread_cost.tex"


def _gross_pnl() -> pd.DataFrame:
    """Return gross MOM/REV P&L and per-date turnover for H2."""
    panel = pd.read_parquet(PANEL)
    p = terciles_longshort(panel)
    gross = (
        p.assign(m=p["w_mom"] * p["ret_fwd"], r=p["w_rev"] * p["ret_fwd"])
         .groupby("date")[["m", "r"]].sum()
         .rename(columns={"m": "mom_gross", "r": "rev_gross"})
    )
    gross["turnover"] = 2.0  # round-trip intraday
    return gross, p


def _avg_day_spread() -> pd.Series:
    """Per-date average quoted_spread_bps across currently-held positions."""
    iid = pd.read_parquet(INTRA)[["date", "ticker", "quoted_spread_bps"]]
    # Use the average per-date spread as the proxy for the day's average
    # per-dollar cost; weights on the H2 portfolio are ±1/20 across 20 names,
    # so per-day aggregate cost proportional to average spread across the
    # held set. We approximate with the average across the currently-traded
    # names per date via a join to the tercile panel.
    return iid


def _portfolio_spread(weights: pd.DataFrame, iid: pd.DataFrame) -> pd.Series:
    """|w|-weighted mean quoted spread per rebalance date — exactly the
    cross-the-spread cost the strategy actually pays per dollar traded."""
    w = weights[["date", "ticker", "w_mom"]].copy()
    w["absw"] = w["w_mom"].abs()
    joined = w.merge(iid, on=["date", "ticker"], how="inner")
    # Weighted mean per date: Σ |w| * spread / Σ |w|
    num = (joined["absw"] * joined["quoted_spread_bps"]).groupby(
        joined["date"]).sum()
    den = joined["absw"].groupby(joined["date"]).sum()
    return (num / den).rename("spread_bps")


def _summarise(pnl_series: pd.Series, cost_series: pd.Series) -> dict:
    """Given a gross P&L and a per-day cost (decimal), compute net stats."""
    net = pnl_series - cost_series
    n = len(net)
    mu, sd = net.mean(), net.std(ddof=1)
    sr = np.sqrt(252) * mu / sd if sd > 0 else np.nan
    t = np.sqrt(n) * mu / sd if sd > 0 else np.nan
    return {"ann_ret": mu * 252, "sharpe": float(sr), "t": float(t),
            "avg_cost_ann": cost_series.mean() * 252}


def main() -> None:
    gross, p = _gross_pnl()
    iid = pd.read_parquet(INTRA)[["date", "ticker", "quoted_spread_bps"]]
    iid["quoted_spread_bps"] = iid["quoted_spread_bps"].fillna(
        iid["quoted_spread_bps"].median())
    spread_per_day = _portfolio_spread(p, iid).reindex(gross.index)
    spread_per_day = spread_per_day.fillna(spread_per_day.median())

    # Per-day cost (decimal). Round-trip = one full cross the spread;
    # half-spread per side × 2 sides = full spread per day (the mid→ask or
    # mid→bid cost times 2).
    cost_halfspread = (spread_per_day / 1e4)

    # Scenarios — each is a pd.Series indexed by rebalance date.
    flat = pd.Series(np.ones(len(gross)), index=gross.index)
    scenarios = {
        "1.5 bps/side (flat, baseline)":
            flat * (1.5 * 2 / 1e4),
        "1.0 bps/side (aggressive)":
            flat * (1.0 * 2 / 1e4),
        "Half-spread per side (optimistic)":
            cost_halfspread,
        "Half-spread + 0.5 bps impact":
            cost_halfspread + flat * (0.5 * 2 / 1e4),
    }

    rows = []
    for label, c in scenarios.items():
        rev = _summarise(gross["rev_gross"], c)
        rows.append({
            "scenario":        label,
            "avg_cost_bps_rt": c.mean() * 1e4,
            "rev_ann_ret":     rev["ann_ret"],
            "rev_sharpe":      rev["sharpe"],
            "rev_t":           rev["t"],
        })
    df = pd.DataFrame(rows)
    t_star = bonferroni_threshold(12, 0.05)
    df["clears_bonf"] = df["rev_t"] > t_star

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(OUT_CSV, index=False)

    lines = [
        r"\begin{tabular}{@{}l r r r r c@{}}",
        r"\toprule",
        (r"Scenario & avg.\ cost (bps, round-trip) & ann.\ ret & "
         r"Sharpe & $t$ & clears $t^*$? \\"),
        r"\midrule",
    ]
    for _, r in df.iterrows():
        mark = r"\checkmark" if r["clears_bonf"] else r"$\times$"
        lines.append(
            f"{r['scenario']} & {r['avg_cost_bps_rt']:.2f} & "
            f"{r['rev_ann_ret']:+.2%} & {r['rev_sharpe']:+.2f} & "
            f"{r['rev_t']:+.2f} & {mark} \\\\"
            .replace("%", r"\%")
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    lines.append(
        rf"% Bonferroni threshold $t^*\approx {t_star:.2f}$. "
        r"Half-spread per side means on each open/close we cross half the "
        r"quoted spread; the day's round-trip cost is one full quoted spread "
        r"on average."
    )
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text("\n".join(lines))

    disp = df.copy()
    disp["avg_cost_bps_rt"] = disp["avg_cost_bps_rt"].apply(lambda x: f"{x:.2f}")
    disp["rev_ann_ret"] = disp["rev_ann_ret"].apply(lambda x: f"{x:+.2%}")
    disp["rev_sharpe"] = disp["rev_sharpe"].apply(lambda x: f"{x:+.2f}")
    disp["rev_t"] = disp["rev_t"].apply(lambda x: f"{x:+.2f}")
    print(disp.to_string(index=False))
    print(f"\nBonferroni t* = {t_star:.3f}")
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_TEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
