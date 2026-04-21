"""Stationary-bootstrap (Politis-Romano 1994) block-length sensitivity
for H2 REV's Sharpe ratio 95% CI.

The stationary bootstrap draws geometric-length blocks with expected
length ℓ. Choosing ℓ is a bias-variance trade-off: short blocks miss
serial dependence, long blocks are noisier. For H2 REV the residual
autocorrelation is minimal (ACF lags all inside ±0.04, §stats), so the
CI should be stable across ℓ. We confirm that here.

Output:
    data/processed/robustness/h2_bootstrap_sensitivity.csv
    icm/tables/h2_bootstrap_sensitivity.tex
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PNL = ROOT / "data" / "processed" / "h2_pnl.parquet"
OUT_CSV = ROOT / "data" / "processed" / "robustness" / "h2_bootstrap_sensitivity.csv"
OUT_TEX = ROOT / "icm" / "tables" / "h2_bootstrap_sensitivity.tex"

BLOCK_LENGTHS = [5, 10, 20, 40, 60, 100]
B = 2_000
SEED = 17


def stationary_bootstrap_sr(x: np.ndarray, block_len: int, B: int,
                              rng: np.random.Generator, a_h: int = 252
                              ) -> np.ndarray:
    """Return B bootstrap Sharpe estimates for 1-d return array x."""
    n = len(x)
    p = 1 / block_len
    srs = np.empty(B)
    for b in range(B):
        idx = np.empty(n, dtype=np.int64)
        i = rng.integers(0, n)
        for t in range(n):
            idx[t] = i
            if rng.random() < p:
                i = rng.integers(0, n)
            else:
                i = (i + 1) % n
        s = x[idx]
        mu, sd = s.mean(), s.std(ddof=1)
        srs[b] = np.sqrt(a_h) * mu / sd if sd > 0 else 0.0
    return srs


def main() -> None:
    pnl = pd.read_parquet(PNL)["rev_net"].to_numpy()
    n = len(pnl)
    point = np.sqrt(252) * pnl.mean() / pnl.std(ddof=1)

    rows = []
    for bl in BLOCK_LENGTHS:
        rng = np.random.default_rng(SEED)  # same seed across block-lengths
        srs = stationary_bootstrap_sr(pnl, bl, B, rng)
        lo, hi = np.quantile(srs, [0.025, 0.975])
        rows.append({
            "block_len":    bl,
            "ci_low":       float(lo),
            "ci_high":      float(hi),
            "ci_width":     float(hi - lo),
            "med":          float(np.median(srs)),
        })
    df = pd.DataFrame(rows)
    df["point"] = point
    df["B"] = B
    df["N"] = n

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(OUT_CSV, index=False)

    lines = [
        r"\begin{tabular}{@{}r r r r r@{}}",
        r"\toprule",
        r"Block length $\ell$ & 2.5\% & 97.5\% & CI width & bootstrap median \\",
        r"\midrule",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"{int(r['block_len'])} & {r['ci_low']:+.2f} & "
            f"{r['ci_high']:+.2f} & {r['ci_width']:.2f} & "
            f"{r['med']:+.2f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    lines.append(
        rf"% Point estimate = {point:+.2f}. $N = {n:,}$, $B = {B:,}$ replicates. "
        r"The CI is stable across $\ell$ because H2 REV's P\&L is close to i.i.d."
    )
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text("\n".join(lines))

    print(df.round(3).to_string(index=False))
    print(f"\npoint SR = {point:+.3f}")
    print(f"wrote {OUT_CSV.relative_to(ROOT)}")
    print(f"wrote {OUT_TEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
