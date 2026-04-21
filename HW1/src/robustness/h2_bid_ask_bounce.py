"""Roll (1984) bid-ask-bounce diagnostic for H2.

The null hypothesis an IC will raise: the negative intraday β that drives
H2 REV is a mechanical artifact of noisy `mid_after_open`. If the first-30
proxy contains a half-spread or transient-quote component ε, and that
component mean-reverts over the rest of the day, we'd observe a negative
regression of rest-of-day on first-30 even if the *fundamental* process is
a random walk.

Roll's closed-form: for a pure random walk fundamental with bid-ask bounce,
first-order autocorrelation of observed returns equals -(s/2)² / σ² where
s is the effective spread and σ is the fundamental-return std.

Two diagnostics:

    D1. Per-ticker β (from src/signals/h2_gao_regression.py) regressed
        against per-ticker median quoted spread. A real intraday reversal
        should be uncorrelated with spread; an artifact should have
        more-negative β on wider-spread names.

    D2. Rerun the H2 REV backtest restricted to the tightest-spread half
        of the universe. If the effect is mostly artifact, it should
        weaken or reverse; if it's real, it should survive with similar
        magnitude.

Outputs:
    data/processed/robustness/h2_beta_vs_spread.csv
    data/processed/robustness/h2_tight_spread_backtest.csv
    stdout: OLS of β vs spread, backtest on tight-half subset.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.engine import run_horizon
from src.backtest.metrics import bonferroni_threshold, summarize

ROOT = Path(__file__).resolve().parents[2]
H2_PANEL = ROOT / "data" / "interim" / "h2_panel.parquet"
INTRA = ROOT / "data" / "interim" / "intraday.parquet"
GAO = ROOT / "data" / "processed" / "gao_regression.csv"
OUT_SPREAD = ROOT / "data" / "processed" / "robustness" / "h2_beta_vs_spread.csv"
OUT_BT = ROOT / "data" / "processed" / "robustness" / "h2_tight_spread_backtest.csv"


def _median_spread_bps() -> pd.Series:
    """Per-ticker median of `quoted_spread_bps` across the trimmed iid panel."""
    iid = pd.read_parquet(INTRA)[["ticker", "quoted_spread_bps"]]
    return iid.groupby("ticker")["quoted_spread_bps"].median().rename("med_spread_bps")


def _median_ivol() -> pd.Series:
    """Per-ticker median of quote-based intraday vol (a proxy for noise in
    `mid_after_open`)."""
    iid = pd.read_parquet(INTRA)[["ticker", "ivol_q"]]
    return iid.groupby("ticker")["ivol_q"].median().rename("med_ivol_q")


def d1_beta_vs_spread() -> pd.DataFrame:
    gao = pd.read_csv(GAO)
    spread = _median_spread_bps().reset_index()
    ivol = _median_ivol().reset_index()
    df = gao.merge(spread, on="ticker").merge(ivol, on="ticker")

    # OLS β ~ spread
    x = df["med_spread_bps"].to_numpy(float)
    y = df["beta"].to_numpy(float)
    n = len(x)
    xc = x - x.mean()
    yc = y - y.mean()
    ss_x = (xc * xc).sum()
    b = (xc * yc).sum() / ss_x
    a = y.mean() - b * x.mean()
    resid = y - (a + b * x)
    sigma2 = (resid * resid).sum() / (n - 2)
    se_b = float(np.sqrt(sigma2 / ss_x))
    t = b / se_b
    r2 = 1.0 - (resid * resid).sum() / (yc * yc).sum()

    # Pearson correlation (more robust for a diagnostic)
    corr = np.corrcoef(x, y)[0, 1]

    df = df.sort_values("med_spread_bps").reset_index(drop=True)
    df.round(4).to_csv(OUT_SPREAD, index=False)

    print(f"D1 — per-ticker β vs. median quoted spread (bps):")
    print(f"    OLS:     β = {a:.3f} + {b:+.4f} * spread,  t_slope = {t:+.2f}, R² = {r2:.3f}")
    print(f"    Pearson ρ (β, spread) = {corr:+.3f}")
    print(f"    Interpretation: ρ < 0 → wider-spread names have more-negative β"
          f" (bid-ask bounce artifact).")
    print()
    print("Top-5 tightest spreads:")
    print(df.head(5)[["ticker", "med_spread_bps", "beta", "t"]].to_string(index=False))
    print("Top-5 widest spreads:")
    print(df.tail(5)[["ticker", "med_spread_bps", "beta", "t"]].to_string(index=False))
    print()
    return df


def d2_tight_spread_backtest(beta_vs_spread: pd.DataFrame) -> pd.DataFrame:
    """Restrict the H2 panel to the tightest-half-spread tickers (by median)
    and rerun the REV backtest."""
    spread = beta_vs_spread[["ticker", "med_spread_bps", "beta", "t"]].copy()
    thresh = spread["med_spread_bps"].median()
    tight = set(spread[spread["med_spread_bps"] <= thresh]["ticker"])
    wide = set(spread[spread["med_spread_bps"] > thresh]["ticker"])

    panel = pd.read_parquet(H2_PANEL)
    rows = []
    for label, keep in [("full", None), ("tight_half", tight), ("wide_half", wide)]:
        sub = panel if keep is None else panel[panel["ticker"].isin(keep)].copy()
        pnl = run_horizon(sub, cost_bps=1.5, round_trip_each_rebalance=True)
        stats = summarize(pnl, periods_per_year=252)
        rev = stats.loc["rev_net"]
        rows.append({
            "subset":        label,
            "n_tickers":     int(sub["ticker"].nunique()),
            "n_obs":         int(sub.shape[0]),
            "rev_ann_ret":   float(rev["ann_ret"]),
            "rev_sharpe":    float(rev["sharpe"]),
            "rev_t":         float(rev["t_stat"]),
            "avg_spread_bps": float(
                spread[spread["ticker"].isin(keep)]["med_spread_bps"].mean()
                if keep else spread["med_spread_bps"].mean()
            ),
        })
    out = pd.DataFrame(rows)
    out.round(4).to_csv(OUT_BT, index=False)

    t_star = bonferroni_threshold(12, 0.05)
    print(f"D2 — REV backtest on tight-spread vs wide-spread subset (cost 1.5 bps/side, round-trip):")
    disp = out.copy()
    disp["rev_ann_ret"] = disp["rev_ann_ret"].apply(lambda x: f"{x:+.2%}")
    for c in ("rev_sharpe", "rev_t"):
        disp[c] = disp[c].apply(lambda x: f"{x:+.3f}")
    disp["avg_spread_bps"] = disp["avg_spread_bps"].apply(lambda x: f"{x:.2f}")
    print(disp.to_string(index=False))
    print()
    print(f"Bonferroni t* = {t_star:.3f}")
    print(f"Interpretation: if the effect is real, REV Sharpe on the tight subset is "
          f"close to the full-universe Sharpe; if it's an artifact, the tight subset "
          f"should be much weaker than wide.")
    return out


def main() -> None:
    beta_df = d1_beta_vs_spread()
    d2_tight_spread_backtest(beta_df)


if __name__ == "__main__":
    main()
