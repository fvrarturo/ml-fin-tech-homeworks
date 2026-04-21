"""Detailed per-horizon stats table for the ICM's methodology / comparison section.

Expands the headline Table 3 with extra columns: annualized return, annualized
vol, average turnover, break-even per-side cost. Emits:

    data/processed/per_horizon_detail.csv
    icm/tables/per_horizon_detail.tex
"""
from __future__ import annotations

from pathlib import Path

import json
import numpy as np
import pandas as pd

from src.backtest.metrics import bonferroni_threshold

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
OUT_CSV = PROCESSED / "per_horizon_detail.csv"
OUT_TEX = ROOT / "icm" / "tables" / "per_horizon_detail.tex"

HORIZONS = ["H1", "H2", "H3", "H4", "H5", "H6"]
HORIZON_LABELS = {
    "H1": "H1 (30 min)", "H2": "H2 (intraday)",
    "H3": "H3 (1 day)", "H4": "H4 (5 day)",
    "H5": "H5 (21 day)", "H6": "H6 (126 day)",
}
NW_HORIZONS = {"H6"}


def _load_row(h: str) -> dict:
    stats = pd.read_csv(PROCESSED / f"{h.lower()}_stats.csv", index_col=0)
    pnl = pd.read_parquet(PROCESSED / f"{h.lower()}_pnl.parquet")
    meta = json.loads((PROCESSED / f"{h.lower()}_run_meta.json").read_text())

    use_nw = h in NW_HORIZONS
    t_col = "t_stat_nw" if use_nw else "t_stat"

    rows = {}
    for fam in ("mom", "rev"):
        s = stats.loc[f"{fam}_net"]
        g = pnl[f"{fam}_gross"]
        turnover = pnl["turnover"].mean()
        ann_factor = meta["periods_per_year"]

        # Break-even per-side cost: gross mean / turnover (bps)
        gross_mean = g.mean()
        be_ps = (gross_mean / turnover) * 1e4 if turnover > 0 else float("nan")

        rows[fam] = {
            "n": int(s["n_obs"]),
            "ann_ret": float(s["ann_ret"]),
            "ann_vol": float(s["ann_vol"]),
            "sharpe": float(s["sharpe"]),
            "t": float(s[t_col]),
            "max_dd": float(s["max_dd"]),
            "turnover": float(turnover),
            "be_ps_bps": float(be_ps),
        }
    rows["meta"] = {"cost_bps": meta["cost_bps"],
                    "ann_factor": meta["periods_per_year"],
                    "round_trip": meta.get("round_trip", False)}
    return rows


def build_df() -> pd.DataFrame:
    rows = []
    for h in HORIZONS:
        if not (PROCESSED / f"{h.lower()}_stats.csv").exists():
            continue
        d = _load_row(h)
        for fam in ("mom", "rev"):
            r = d[fam].copy()
            r.update({"horizon": h, "family": fam.upper(),
                      "cost_bps": d["meta"]["cost_bps"]})
            rows.append(r)
    df = pd.DataFrame(rows)
    return df[["horizon", "family", "n", "cost_bps", "turnover",
               "ann_ret", "ann_vol", "sharpe", "t", "max_dd", "be_ps_bps"]]


def to_latex(df: pd.DataFrame) -> str:
    t_star = bonferroni_threshold(12, 0.05)
    lines = [
        r"\begin{tabular}{@{}l l r r r r r r r r r@{}}",
        r"\toprule",
        (r"$h$ & Fam. & $N$ & $c$ (bps) & turn. & "
         r"ann. ret & ann. vol & SR & $t$ & MDD & $c^*$ BE (bps) \\"),
        r"\midrule",
    ]
    for _, r in df.iterrows():
        star = r"^{*}" if abs(r["t"]) > t_star and r["t"] > 0 else ""
        lines.append(
            f"{HORIZON_LABELS[r['horizon']]} & {r['family']} & "
            f"{int(r['n']):,} & {r['cost_bps']:.1f} & {r['turnover']:.2f} & "
            f"{r['ann_ret']:+.2%} & {r['ann_vol']:.2%} & "
            f"{r['sharpe']:+.2f}{star} & {r['t']:+.2f} & "
            f"{r['max_dd']:.1%} & {r['be_ps_bps']:.2f} \\\\"
            .replace("%", r"\%")
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(
        rf"% ${{}}^*$ indicates the Sharpe whose $t$-stat clears the "
        rf"Bonferroni threshold $t^*\approx {t_star:.2f}$ on the correct side."
    )
    return "\n".join(lines)


def main() -> None:
    df = build_df()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.round(6).to_csv(OUT_CSV, index=False)

    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text(to_latex(df))

    disp = df.copy()
    disp["ann_ret"] = disp["ann_ret"].apply(lambda x: f"{x:+.2%}")
    disp["ann_vol"] = disp["ann_vol"].apply(lambda x: f"{x:.2%}")
    disp["max_dd"] = disp["max_dd"].apply(lambda x: f"{x:.1%}")
    disp["sharpe"] = disp["sharpe"].apply(lambda x: f"{x:+.2f}")
    disp["t"] = disp["t"].apply(lambda x: f"{x:+.2f}")
    disp["be_ps_bps"] = disp["be_ps_bps"].apply(lambda x: f"{x:.2f}")
    print(disp.to_string(index=False))
    print()
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_TEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
