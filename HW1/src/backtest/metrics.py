"""Summary stats for P&L series (Work1.md §5.5–5.6).

Every horizon's P&L columns (`mom_gross`, `mom_net`, `rev_gross`, `rev_net`) go
through `summarize` to produce one row of Table 3. H6 additionally calls
`newey_west_tstat` with q=6 for the overlapping-forecast adjustment (§6.6).

Bonferroni threshold for 12 tests × α = 5% → t* ≈ 2.874.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm


def max_drawdown(cum_wealth: pd.Series) -> float:
    """Peak-to-trough drawdown of a wealth series. Returns a negative number
    (e.g., -0.11 = 11% drawdown)."""
    running_max = cum_wealth.cummax()
    dd = (cum_wealth - running_max) / running_max
    return float(dd.min())


def newey_west_tstat(x: pd.Series, lags: int) -> float:
    """NW-HAC-adjusted t-stat of the mean of `x` against zero. Used for H6."""
    x = x.dropna().astype(float).values
    n = len(x)
    if n < lags + 2:
        return np.nan
    X = np.ones((n, 1))
    res = sm.OLS(x, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(res.tvalues[0])


def _stats(x: pd.Series, periods_per_year: int, nw_lags: int = 0) -> pd.Series:
    x = x.dropna().astype(float)
    n = len(x)
    if n < 2:
        return pd.Series({"n_obs": n, "mean": np.nan, "std": np.nan,
                          "ann_ret": np.nan, "ann_vol": np.nan,
                          "sharpe": np.nan, "t_stat": np.nan,
                          "t_stat_nw": np.nan, "max_dd": np.nan})
    mu, sd = x.mean(), x.std(ddof=1)
    sr = np.sqrt(periods_per_year) * mu / sd if sd > 0 else np.nan
    t = np.sqrt(n) * mu / sd if sd > 0 else np.nan
    t_nw = newey_west_tstat(x, nw_lags) if nw_lags else np.nan
    mdd = max_drawdown((1 + x).cumprod())
    return pd.Series({
        "n_obs": n,
        "mean": mu,
        "std": sd,
        "ann_ret": mu * periods_per_year,
        "ann_vol": sd * np.sqrt(periods_per_year),
        "sharpe": sr,
        "t_stat": t,
        "t_stat_nw": t_nw,
        "max_dd": mdd,
    })


def summarize(
    pnl: pd.DataFrame,
    periods_per_year: int,
    cols: Iterable[str] | None = None,
    nw_lags: int = 0,
) -> pd.DataFrame:
    """One row per P&L column."""
    if cols is None:
        cols = [c for c in pnl.columns if c != "turnover"]
    rows = {c: _stats(pnl[c], periods_per_year, nw_lags) for c in cols}
    out = pd.DataFrame(rows).T
    out.index.name = "column"
    return out


def bonferroni_threshold(n_tests: int = 12, alpha: float = 0.05) -> float:
    """Two-sided z-critical at family-wise error rate `alpha` across `n_tests`."""
    return float(norm.ppf(1 - (alpha / n_tests) / 2))


if __name__ == "__main__":
    rng = np.random.default_rng(3)
    x = pd.Series(rng.normal(0.0005, 0.01, 2500))
    s = _stats(x, periods_per_year=252, nw_lags=6)
    print(s.to_frame("value"))
    print(f"\nBonferroni t* for 12 tests: {bonferroni_threshold():.4f}")
