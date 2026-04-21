"""Gao, Han, Li & Zhou (2018, JFE) intraday-momentum regression.

Per-ticker OLS on the PIT-filtered H2 panel:

    ret_fwd_{i,t} = α_i + β_i · signal_{i,t} + ε_{i,t}

where signal = (mid_after_open / OPrc - 1) proxies the first-30-minute
return and ret_fwd = (CPrc / mid_after_open - 1) is the rest-of-day return.
Gao finds significant positive β on S&P 500 futures 1993-2012 (intraday
momentum persistence).

Outputs (Work1.md §6.2 Step 4):

    data/processed/gao_regression.csv  — per-ticker (ticker, n, beta, t, se, r2)
    data/processed/gao_pooled.json     — cross-sectional summary:
        mean_beta, median_beta, pct_positive_beta,
        pct_t_gt_2, pct_t_lt_minus2, t_cross_section,
        [plus robustness copies on the pre-PIT panel for comparison]

The prior EDA regression in src/eda/03_intraday.py regressed
`CPrc / mid_before_close - 1` (last-30) on first-30, NOT rest-of-day. That
is a different test — it looks at whether intraday momentum shows up in the
*closing half-hour*. Work1.md spec is the full rest-of-day, which is what
this script uses.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
H2_PANEL = ROOT / "data" / "interim" / "h2_panel.parquet"
INTRA = ROOT / "data" / "interim" / "intraday.parquet"
EARLY = ROOT / "data" / "reference" / "nyse_early_closes.csv"

OUT_CSV = ROOT / "data" / "processed" / "gao_regression.csv"
OUT_JSON = ROOT / "data" / "processed" / "gao_pooled.json"

MIN_OBS = 100  # per-ticker minimum sample for a stable per-ticker estimate


def regress_per_ticker(panel: pd.DataFrame) -> pd.DataFrame:
    """Return per-ticker OLS regression of ret_fwd ~ signal.

    Computes β, its OLS SE, t-stat, and R² via closed form (no statsmodels
    dependency — the design matrix is 1D so the formulas are short).
    """
    rows = []
    for tkr, sub in panel.groupby("ticker"):
        x = sub["signal"].to_numpy(dtype=float)
        y = sub["ret_fwd"].to_numpy(dtype=float)
        n = len(x)
        if n < MIN_OBS:
            continue
        xc = x - x.mean()
        yc = y - y.mean()
        ss_x = (xc * xc).sum()
        if ss_x <= 0:
            continue
        b = (xc * yc).sum() / ss_x
        a = y.mean() - b * x.mean()
        resid = y - (a + b * x)
        sigma2 = (resid * resid).sum() / (n - 2)
        se_b = float(np.sqrt(sigma2 / ss_x))
        t = b / se_b if se_b > 0 else np.nan
        ss_tot = (yc * yc).sum()
        r2 = 1.0 - (resid * resid).sum() / ss_tot if ss_tot > 0 else np.nan
        rows.append({
            "ticker": tkr,
            "n": int(n),
            "beta": float(b),
            "alpha": float(a),
            "se_beta": se_b,
            "t": float(t) if np.isfinite(t) else np.nan,
            "r2": float(r2),
        })
    return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)


def pooled_summary(gao: pd.DataFrame) -> dict:
    n = len(gao)
    mean_b = gao["beta"].mean()
    sd_b = gao["beta"].std(ddof=1)
    t_cross = mean_b / (sd_b / np.sqrt(n)) if sd_b > 0 and n > 1 else np.nan
    return {
        "n_tickers": n,
        "mean_beta": float(mean_b),
        "median_beta": float(gao["beta"].median()),
        "std_beta": float(sd_b),
        "pct_positive_beta": float((gao["beta"] > 0).mean()),
        "pct_t_gt_2": float((gao["t"] > 2).mean()),
        "pct_t_lt_minus2": float((gao["t"] < -2).mean()),
        "pct_t_abs_gt_2": float((gao["t"].abs() > 2).mean()),
        "t_cross_section": float(t_cross) if np.isfinite(t_cross) else None,
        "median_r2": float(gao["r2"].median()),
        "total_obs": int(gao["n"].sum()),
    }


def _prepit_panel() -> pd.DataFrame:
    """Rebuild the H2 signal/forward without the PIT filter — used to compare
    how membership-filtering shifts the pooled β."""
    iid = pd.read_parquet(INTRA)[["date", "ticker", "open", "close", "mid_after_open"]]
    iid["ticker"] = iid["ticker"].astype(str)
    iid["signal"] = iid["mid_after_open"] / iid["open"] - 1.0
    iid["ret_fwd"] = iid["close"] / iid["mid_after_open"] - 1.0
    ec = pd.read_csv(EARLY, parse_dates=["date"])
    iid = iid[~iid["date"].isin(set(ec["date"]))]
    return iid.dropna(subset=["signal", "ret_fwd"])


def main() -> None:
    panel_pit = pd.read_parquet(H2_PANEL)
    gao_pit = regress_per_ticker(panel_pit)
    gao_pit.round(6).to_csv(OUT_CSV, index=False)

    summary = {"post_pit": pooled_summary(gao_pit)}

    # Robustness: same regression on the pre-PIT panel for comparability with
    # the prior EDA's number (which regressed last-30 on first-30 and got
    # mean β = -0.0292 — our regression is different: rest-of-day, not last-30).
    panel_pre = _prepit_panel()
    gao_pre = regress_per_ticker(panel_pre)
    summary["pre_pit"] = pooled_summary(gao_pre)

    OUT_JSON.write_text(json.dumps(summary, indent=2))

    print(f"wrote {OUT_CSV}  (per-ticker; {len(gao_pit)} tickers)")
    print(f"wrote {OUT_JSON}")
    print()
    print("Post-PIT pooled summary:")
    for k, v in summary["post_pit"].items():
        vs = f"{v:.4f}" if isinstance(v, float) else f"{v}"
        print(f"  {k:22s} {vs}")
    print()
    print("Post-PIT per-ticker (top 5 by |t|):")
    print(
        gao_pit.reindex(gao_pit["t"].abs().sort_values(ascending=False).index)
        .head(5)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
