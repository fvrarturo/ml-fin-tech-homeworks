"""Return distributions and horizon autocorrelations on the CRSP daily panel."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "_info" / "eda"
OUT.mkdir(parents=True, exist_ok=True)


def load_daily() -> pd.DataFrame:
    df = pd.read_csv(ROOT / "data" / "dow_daily.csv.gz", compression="gzip", low_memory=False)
    df["DlyCalDt"] = pd.to_datetime(df["DlyCalDt"])
    df = df.sort_values(["Ticker", "DlyCalDt"]).reset_index(drop=True)
    return df


def horizon_return(g: pd.DataFrame, h: int) -> pd.Series:
    r = g["DlyRet"].astype(float)
    # h-period compounded return using log-sum is cleaner, but daily ret is small
    return (1.0 + r).rolling(h).apply(np.prod, raw=True) - 1.0


def variance_ratio(rets: np.ndarray, q: int) -> float:
    r = rets[~np.isnan(rets)]
    if len(r) < q * 10:
        return np.nan
    # VR(q) = Var(r_q)/(q * Var(r_1)), using non-overlapping q-period sums
    n = (len(r) // q) * q
    r = r[:n]
    r1_var = np.var(r, ddof=1)
    rq = r.reshape(-1, q).sum(axis=1)
    rq_var = np.var(rq, ddof=1)
    if r1_var <= 0:
        return np.nan
    return rq_var / (q * r1_var)


def main() -> None:
    df = load_daily()
    df["DlyRet"] = pd.to_numeric(df["DlyRet"], errors="coerce")

    # Per-ticker summary: lifespan, mean/vol/skew/kurt of daily returns
    g = df.groupby("Ticker")["DlyRet"]
    per_tkr = pd.DataFrame({
        "n": g.size(),
        "mean_bps": g.mean() * 1e4,
        "vol_bps": g.std() * 1e4,
        "skew": g.skew(),
        "kurt": g.apply(lambda s: s.kurt()),
        "first": df.groupby("Ticker")["DlyCalDt"].min().dt.strftime("%Y-%m-%d"),
        "last": df.groupby("Ticker")["DlyCalDt"].max().dt.strftime("%Y-%m-%d"),
    }).round(3)
    per_tkr.to_csv(OUT / "02_per_ticker_stats.csv")

    # Autocorrelations: lag 1, 5, 20 (daily, weekly-ish, monthly-ish signs)
    def acf(s: pd.Series, lag: int) -> float:
        s = s.dropna()
        if len(s) < lag + 30:
            return np.nan
        return float(s.autocorr(lag=lag))

    acfs = pd.DataFrame({
        "rho_1": g.apply(lambda s: acf(s, 1)),
        "rho_5": g.apply(lambda s: acf(s, 5)),
        "rho_20": g.apply(lambda s: acf(s, 20)),
    }).round(4)
    acfs.to_csv(OUT / "02_autocorr.csv")

    # Variance ratios for q in {2,5,10,20,60,126}
    qs = [2, 5, 10, 20, 60, 126]
    vr_rows = []
    for tkr, sub in df.groupby("Ticker"):
        row = {"Ticker": tkr}
        r = sub["DlyRet"].to_numpy()
        for q in qs:
            row[f"VR_{q}"] = variance_ratio(r, q)
        vr_rows.append(row)
    vr = pd.DataFrame(vr_rows).set_index("Ticker")
    vr.round(3).to_csv(OUT / "02_variance_ratios.csv")

    # Cross-ticker pool: pooled lag-1 and VR (mean and t on per-ticker estimates)
    def pooled(arr: pd.Series) -> dict:
        a = arr.dropna().values
        if len(a) == 0:
            return {"mean": np.nan, "t": np.nan, "n": 0}
        return {
            "mean": float(np.mean(a)),
            "t": float(np.mean(a) / (np.std(a, ddof=1) / np.sqrt(len(a)))),
            "n": int(len(a)),
        }

    pool = {
        "rho_1": pooled(acfs["rho_1"]),
        "rho_5": pooled(acfs["rho_5"]),
        "rho_20": pooled(acfs["rho_20"]),
        **{f"VR_{q}": pooled(vr[f"VR_{q}"]) for q in qs},
    }
    (OUT / "02_pooled.json").write_text(json.dumps(pool, indent=2))

    # Percent of dates with 30 active Dow tickers (point-in-time membership check)
    counts = df.groupby("DlyCalDt")["Ticker"].nunique()
    active_hist = counts.value_counts().sort_index().to_dict()
    (OUT / "02_active_ticker_counts.json").write_text(
        json.dumps({str(k): int(v) for k, v in active_hist.items()}, indent=2)
    )

    # Quick "always present" vs "churn" split
    tenure = df.groupby("Ticker")["DlyCalDt"].agg(["min", "max", "count"]).reset_index()
    tenure.columns = ["Ticker", "first", "last", "n_days"]
    max_days = tenure["n_days"].max()
    tenure["always_present"] = tenure["n_days"] == max_days
    tenure.to_csv(OUT / "02_ticker_tenure.csv", index=False)

    print("pooled autocorr / VR summary:")
    print(json.dumps(pool, indent=2))


if __name__ == "__main__":
    main()
