"""Per-horizon cross-sectional signal moments + panel integrity.

Summarises the signal/forward distribution and panel-integrity stats across
the six horizon panels. Emits:

    data/processed/signal_moments.csv
    icm/tables/signal_moments.tex
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scst

ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
OUT_CSV = PROCESSED / "signal_moments.csv"
OUT_TEX = ROOT / "icm" / "tables" / "signal_moments.tex"

HORIZONS = ["H1", "H2", "H3", "H4", "H5", "H6"]
HORIZON_LABELS = {
    "H1": "H1 (30 min)", "H2": "H2 (intraday)",
    "H3": "H3 (1 day)",  "H4": "H4 (5 day)",
    "H5": "H5 (21 day)", "H6": "H6 (126 day)",
}


def _moments(series: np.ndarray) -> dict:
    s = series[np.isfinite(series)]
    return {
        "mean_bps": float(np.mean(s) * 1e4),
        "std_bps":  float(np.std(s, ddof=1) * 1e4),
        "skew":     float(scst.skew(s)),
        "ex_kurt":  float(scst.kurtosis(s)),
    }


def _per_date_dispersion(df: pd.DataFrame, col: str) -> float:
    """Average per-date cross-sectional std of `col`, bps."""
    return float(df.groupby("date")[col].std(ddof=1).mean() * 1e4)


def build() -> pd.DataFrame:
    rows = []
    for h in HORIZONS:
        panel_path = INTERIM / f"{h.lower()}_panel.parquet"
        if not panel_path.exists():
            continue
        panel = pd.read_parquet(panel_path)
        sig = panel["signal"].to_numpy()
        fwd = panel["ret_fwd"].to_numpy()

        meta_path = PROCESSED / f"{h.lower()}_run_meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        turnover = meta.get("avg_turnover", float("nan"))

        names_per = panel.groupby("date")["ticker"].nunique()

        sig_m = _moments(sig)
        sig_xc_disp = _per_date_dispersion(panel, "signal")

        rows.append({
            "horizon":        h,
            "rebalances":     int(panel["date"].nunique()),
            "obs":            int(len(panel)),
            "modal_n":        int(names_per.mode().iloc[0]),
            "n_short":        int((names_per < 30).sum()),
            "turnover":       float(turnover),
            "sig_mean_bps":   sig_m["mean_bps"],
            "sig_std_bps":    sig_m["std_bps"],
            "sig_xc_disp_bps": sig_xc_disp,
            "sig_skew":       sig_m["skew"],
            "sig_ex_kurt":    sig_m["ex_kurt"],
        })
    return pd.DataFrame(rows)


def to_latex(df: pd.DataFrame) -> str:
    lines = [
        r"\begin{tabular}{@{}l r r r r r r r r r@{}}",
        r"\toprule",
        (r"$h$ & rebal. & obs. & modal $N$ & short-days & turn. & "
         r"$\bar{s}$ (bps) & $\sigma_s$ (bps) & XS-$\sigma_s$ (bps) & "
         r"ex-kurt$_s$ \\"),
        r"\midrule",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"{HORIZON_LABELS[r['horizon']]} & "
            f"{int(r['rebalances']):,} & {int(r['obs']):,} & "
            f"{int(r['modal_n'])} & {int(r['n_short'])} & "
            f"{r['turnover']:.2f} & "
            f"{r['sig_mean_bps']:+.1f} & "
            f"{r['sig_std_bps']:,.0f} & "
            f"{r['sig_xc_disp_bps']:,.0f} & "
            f"{r['sig_ex_kurt']:+.2f} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(
        r"% $\bar{s}$: pooled mean signal. $\sigma_s$: pooled standard "
        r"deviation. XS-$\sigma_s$: mean per-date cross-sectional standard "
        r"deviation (the dispersion the tercile sort ranks against). "
        r"short-days: rebalance dates where the PIT merge yielded $<$30 names."
    )
    return "\n".join(lines)


def main() -> None:
    df = build()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(OUT_CSV, index=False)
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text(to_latex(df))

    disp = df.copy()
    for c in ("sig_mean_bps", "sig_std_bps", "sig_xc_disp_bps",
              "sig_skew", "sig_ex_kurt"):
        disp[c] = disp[c].apply(lambda x: f"{x:+.2f}")
    disp["turnover"] = disp["turnover"].apply(lambda x: f"{x:.2f}")
    print(disp.to_string(index=False))
    print()
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_TEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
