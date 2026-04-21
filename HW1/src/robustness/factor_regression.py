"""Fama-French 5-factor + momentum regression for the two selected strategies.

For each strategy P&L series {r_t}, estimate:

    r_t = α + β_MKT·MKT_t + β_SMB·SMB_t + β_HML·HML_t
             + β_RMW·RMW_t + β_CMA·CMA_t + β_MOM·MOM_t + ε_t

using OLS, with HAC (Newey-West) standard errors at q=6 for the monthly H6
series (overlapping forecasts) and q=0 for the daily H2.

An IC wants to see: does the strategy deliver alpha after controlling for
standard risk factors? For H2 REV we expect α ≈ ann. return (intraday
process, minimal factor loading); for H6 MOM we expect material loading on
the momentum factor.

Outputs:
    data/processed/robustness/factor_regression.csv
    icm/tables/factor_regression.tex
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
FF5 = ROOT / "data" / "reference" / "ff_fivefactors.csv"
FF_MOM = ROOT / "data" / "reference" / "ff_mom.csv"
OUT_CSV = PROCESSED / "robustness" / "factor_regression.csv"
OUT_TEX = ROOT / "icm" / "tables" / "factor_regression.tex"

FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]


def _load_factors() -> pd.DataFrame:
    """Both files are already well-formed CSVs with a single header row. The
    Fama-French factors are reported in percent — divide by 100 so they align
    with our decimal-return P&L."""
    ff = pd.read_csv(FF5).rename(columns={"Unnamed: 0": "date"})
    ff["date"] = pd.to_datetime(ff["date"], format="%Y%m%d")
    for c in ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]:
        ff[c] = ff[c].astype(float) / 100.0

    mom = pd.read_csv(FF_MOM).rename(columns={"Unnamed: 0": "date"})
    mom["date"] = pd.to_datetime(mom["date"], format="%Y%m%d")
    mom["Mom"] = mom["Mom"].astype(float) / 100.0

    return ff.merge(mom[["date", "Mom"]], on="date", how="inner")


def _run_regression(
    pnl_series: pd.Series, factors: pd.DataFrame, nw_lags: int = 0
) -> pd.DataFrame:
    df = factors.merge(
        pnl_series.rename("ret").reset_index().rename(columns={"index": "date"}),
        on="date", how="inner",
    )
    df = df.dropna(subset=FACTORS + ["ret"])
    if len(df) < len(FACTORS) + 5:
        raise ValueError(f"not enough observations after merge: {len(df)}")

    X = sm.add_constant(df[FACTORS].values)
    y = df["ret"].values
    if nw_lags:
        res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": nw_lags})
    else:
        res = sm.OLS(y, X).fit()

    out = pd.DataFrame({
        "coef":   res.params,
        "se":     res.bse,
        "t":      res.tvalues,
        "p":      res.pvalues,
    }, index=["alpha"] + FACTORS)
    out.index.name = "term"
    out["n"] = len(df)
    out["r2"] = res.rsquared
    return out


def _run_monthly(pnl_series: pd.Series, factors: pd.DataFrame) -> pd.DataFrame:
    """H6 P&L is monthly. Aggregate factors to monthly and regress with NW q=6."""
    # Align factor series to monthly sums of daily factor returns (standard
    # approach — factors are monthly observed via daily; summation yields
    # monthly return).
    f_month = factors.copy()
    f_month["_m"] = f_month["date"].dt.to_period("M")
    f_sum = f_month.groupby("_m")[FACTORS].sum()
    f_sum.index = f_sum.index.to_timestamp(how="end")

    # H6 P&L is indexed by rebalance date (month-end). Align by month-end.
    p = pnl_series.rename("ret").reset_index().rename(columns={"index": "date"})
    p["_m"] = pd.to_datetime(p["date"]).dt.to_period("M").dt.to_timestamp(how="end")
    merged = p.merge(f_sum.reset_index().rename(columns={"_m": "_m"}),
                      left_on="_m", right_on="_m", how="inner")

    # Run as before
    X = sm.add_constant(merged[FACTORS].values)
    y = merged["ret"].values
    res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    out = pd.DataFrame({
        "coef":   res.params,
        "se":     res.bse,
        "t":      res.tvalues,
        "p":      res.pvalues,
    }, index=["alpha"] + FACTORS)
    out.index.name = "term"
    out["n"] = len(merged)
    out["r2"] = res.rsquared
    return out


def _to_latex(h2: pd.DataFrame, h6: pd.DataFrame) -> str:
    def fmt(df, col_prefix):
        return [
            (df.loc[k, "coef"], df.loc[k, "t"])
            for k in ["alpha"] + FACTORS
        ]
    rows = []
    rows.append(r"\begin{tabular}{@{}l r r c r r@{}}")
    rows.append(r"\toprule")
    rows.append(r" & \multicolumn{2}{c}{H2 REV (daily, OLS)} & & \multicolumn{2}{c}{H6 MOM (monthly, NW $q$=6)} \\")
    rows.append(r"\cmidrule(lr){2-3} \cmidrule(lr){5-6}")
    rows.append(r"Term & coef & $t$ & & coef & $t$ \\")
    rows.append(r"\midrule")
    # Scale daily alpha to annualized, monthly to annualized.
    ann_h2 = 252
    ann_h6 = 12
    for k in ["alpha"] + FACTORS:
        a2 = h2.loc[k, "coef"] * (ann_h2 if k == "alpha" else 1)
        t2 = h2.loc[k, "t"]
        a6 = h6.loc[k, "coef"] * (ann_h6 if k == "alpha" else 1)
        t6 = h6.loc[k, "t"]
        name = r"$\alpha$ (annualized)" if k == "alpha" else k
        rows.append(
            f"{name} & {a2:+.4f} & {t2:+.2f} & & {a6:+.4f} & {t6:+.2f} \\\\"
        )
    rows.append(r"\midrule")
    rows.append(f"$N$ & {int(h2['n'].iloc[0]):,} & & & {int(h6['n'].iloc[0]):,} & \\\\")
    rows.append(f"$R^2$ & {h2['r2'].iloc[0]:.3f} & & & {h6['r2'].iloc[0]:.3f} & \\\\")
    rows.append(r"\bottomrule")
    rows.append(r"\end{tabular}")
    return "\n".join(rows)


def main() -> None:
    factors = _load_factors()
    h2_pnl = pd.read_parquet(PROCESSED / "h2_pnl.parquet")["rev_net"]
    h2_pnl.index = pd.to_datetime(h2_pnl.index)
    h6_pnl = pd.read_parquet(PROCESSED / "h6_pnl.parquet")["mom_net"]
    h6_pnl.index = pd.to_datetime(h6_pnl.index)

    h2_res = _run_regression(h2_pnl, factors, nw_lags=0)
    h6_res = _run_monthly(h6_pnl, factors)

    combined = pd.concat(
        [h2_res.assign(strategy="H2_REV"),
         h6_res.assign(strategy="H6_MOM")],
    )
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.reset_index().round(6).to_csv(OUT_CSV, index=False)

    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text(_to_latex(h2_res, h6_res))

    print("=== H2 REV (daily, OLS) ===")
    print(h2_res.round(4).to_string())
    print()
    print("=== H6 MOM (monthly, NW q=6) ===")
    print(h6_res.round(4).to_string())
    print()
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_TEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
