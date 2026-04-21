"""Intraday panel: check AM/PM decomposition, Gao-et-al regression, spread stats."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "_info" / "eda"
OUT.mkdir(parents=True, exist_ok=True)


def load_intra() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "dow_intraday.csv.gz", compression="gzip", low_memory=False)
    df["DATE"] = pd.to_datetime(df["DATE"])
    df = df.sort_values(["SYM_ROOT", "DATE"]).reset_index(drop=True)
    return df


def main() -> None:
    df = load_intra()

    # Returns we can derive from the midpoint columns.
    # OPrc -> mid_after_open : opening auction to early-morning equilibrium
    # mid_after_open -> mid_before_close : intraday drift
    # mid_before_close -> CPrc : closing auction
    # OPrc -> CPrc : open-to-close (day) return
    for c in ["OPrc", "CPrc", "mid_after_open", "mid_before_close", "mid_1pm", "mid_4pm"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["ret_o2c"] = df["CPrc"] / df["OPrc"] - 1.0
    df["ret_first30"] = df["mid_after_open"] / df["OPrc"] - 1.0
    df["ret_last30"] = df["CPrc"] / df["mid_before_close"] - 1.0
    df["ret_midday"] = df["mid_before_close"] / df["mid_after_open"] - 1.0
    df["ret_am"] = df["mid_1pm"] / df["OPrc"] - 1.0
    df["ret_pm"] = df["CPrc"] / df["mid_1pm"] - 1.0

    # Summary stats per return type (bps)
    ret_cols = ["ret_o2c", "ret_first30", "ret_last30", "ret_midday", "ret_am", "ret_pm"]
    stats = pd.DataFrame(
        {
            c: {
                "mean_bps": df[c].mean() * 1e4,
                "std_bps": df[c].std() * 1e4,
                "p01_bps": df[c].quantile(0.01) * 1e4,
                "p99_bps": df[c].quantile(0.99) * 1e4,
                "pct_nan": df[c].isna().mean() * 100,
            }
            for c in ret_cols
        }
    ).T.round(2)
    stats.to_csv(OUT / "03_intraday_return_stats.csv")

    # Gao et al. (2018) - style regression: ret_last30 ~ a + b * ret_first30 per ticker
    rows = []
    pooled = df.dropna(subset=["ret_first30", "ret_last30"])
    for tkr, sub in pooled.groupby("SYM_ROOT"):
        if len(sub) < 100:
            continue
        x = sub["ret_first30"].values
        y = sub["ret_last30"].values
        b, a = np.polyfit(x, y, 1)
        yhat = a + b * x
        resid = y - yhat
        # OLS SE
        n = len(x)
        xc = x - x.mean()
        ss = (xc ** 2).sum()
        sigma2 = (resid ** 2).sum() / (n - 2)
        se_b = np.sqrt(sigma2 / ss)
        t = b / se_b if se_b > 0 else np.nan
        rows.append({"ticker": tkr, "n": n, "beta": b, "t": t})
    gao = pd.DataFrame(rows)
    gao.round(4).to_csv(OUT / "03_gao_regression.csv", index=False)

    pooled_stats = {
        "beta_mean": float(gao["beta"].mean()),
        "beta_median": float(gao["beta"].median()),
        "pct_positive_beta": float((gao["beta"] > 0).mean()),
        "pct_t_gt_2": float((gao["t"] > 2).mean()),
        "pct_t_lt_minus2": float((gao["t"] < -2).mean()),
        "t_cross_section": float(
            gao["beta"].mean()
            / (gao["beta"].std(ddof=1) / np.sqrt(len(gao)))
        ),
    }
    (OUT / "03_gao_pooled.json").write_text(json.dumps(pooled_stats, indent=2))

    # Spread / impact summary
    spread_cols = {
        "QuotedSpread_Percent_tw": "quoted_spread_pct",
        "PercentPriceImpact_LR_Ave": "impact_pct_avg",
        "PercentPriceImpact_LR_SW": "impact_pct_sw",
        "ivol_t": "ivol_trade",
        "ivol_q": "ivol_quote",
        "HIndex": "h_index",
        "var_ratio1": "vr1_intraday",
        "var_ratio2": "vr2_intraday",
        "var_ratio3": "vr3_intraday",
    }
    micro = {}
    for raw, label in spread_cols.items():
        if raw not in df:
            continue
        s = pd.to_numeric(df[raw], errors="coerce")
        micro[label] = {
            "mean": float(s.mean()),
            "median": float(s.median()),
            "p01": float(s.quantile(0.01)),
            "p99": float(s.quantile(0.99)),
            "pct_missing": float(s.isna().mean() * 100),
        }
    (OUT / "03_micro_stats.json").write_text(json.dumps(micro, indent=2))

    # Per-ticker median quoted spread (bps)
    q = pd.to_numeric(df["QuotedSpread_Percent_tw"], errors="coerce") * 1e4
    q_by = q.groupby(df["SYM_ROOT"]).median().sort_values()
    q_by.to_csv(OUT / "03_spread_by_ticker_bps.csv", header=["median_spread_bps"])

    # Buy-sell imbalance
    df["OIB"] = (df["BuyVol_LR"] - df["SellVol_LR"]) / (df["BuyVol_LR"] + df["SellVol_LR"])
    oib = df.groupby("SYM_ROOT")["OIB"].describe().round(4)
    oib.to_csv(OUT / "03_oib_by_ticker.csv")

    # Correlation of OIB with same-day return and next-day return
    df["ret_next"] = df.groupby("SYM_ROOT")["ret_o2c"].shift(-1)
    corr_same = df.groupby("SYM_ROOT").apply(
        lambda s: s[["OIB", "ret_o2c"]].corr().iloc[0, 1]
    )
    corr_next = df.groupby("SYM_ROOT").apply(
        lambda s: s[["OIB", "ret_next"]].corr().iloc[0, 1]
    )
    pd.DataFrame(
        {"corr_OIB_same_day": corr_same, "corr_OIB_next_day": corr_next}
    ).round(3).to_csv(OUT / "03_oib_vs_return_corr.csv")

    print(json.dumps(pooled_stats, indent=2))
    print("quoted spreads (bps) top 5 widest:")
    print(q_by.tail(5))
    print("quoted spreads (bps) top 5 tightest:")
    print(q_by.head(5))


if __name__ == "__main__":
    main()
