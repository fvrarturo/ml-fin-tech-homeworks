"""Render Table 3 — the headline cross-horizon comparison.

Reads per-horizon stats CSVs from data/processed/ and assembles:

    data/processed/headline_table.csv    (machine-readable)
    icm/tables/headline.tex              (LaTeX booktabs fragment)

The "Winner" column is MOM or REV — whichever has the larger |Sharpe|, subject
to |t| > t* (Bonferroni two-sided threshold for 12 tests at α=5%, ≈2.87). For
H6, the NW-corrected t-stat is used instead of the naive one. If neither
family clears significance, Winner = "N.S." (not significant).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.backtest.metrics import bonferroni_threshold

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
ICM_TABLES = ROOT / "icm" / "tables"

HORIZONS = ["H1", "H2", "H3", "H4", "H5", "H6"]
HORIZON_LABELS = {
    "H1": "H1 (30min)",
    "H2": "H2 (IID)",
    "H3": "H3 (1d)",
    "H4": "H4 (5d)",
    "H5": "H5 (21d)",
    "H6": "H6 (126d)",
}
NW_HORIZONS = {"H6"}  # use NW t instead of naive


def _row_from_stats(stats: pd.DataFrame, family: str, use_nw: bool) -> dict:
    s = stats.loc[f"{family}_net"]
    return {
        "sharpe": float(s["sharpe"]),
        "t_stat": float(s["t_stat_nw"] if use_nw else s["t_stat"]),
        "mdd": float(s["max_dd"]),
    }


def assemble() -> pd.DataFrame:
    t_star = bonferroni_threshold(n_tests=12, alpha=0.05)
    rows = []
    for h in HORIZONS:
        stats_path = PROCESSED / f"{h.lower()}_stats.csv"
        if not stats_path.exists():
            rows.append({"horizon": HORIZON_LABELS[h], "n_obs": None,
                         "mom_sr": None, "mom_t": None, "mom_mdd": None,
                         "rev_sr": None, "rev_t": None, "rev_mdd": None,
                         "winner": "—"})
            continue
        s = pd.read_csv(stats_path, index_col=0)
        use_nw = h in NW_HORIZONS
        mom = _row_from_stats(s, "mom", use_nw)
        rev = _row_from_stats(s, "rev", use_nw)
        # Winner logic: profitable AND Bonferroni-significant. A massively
        # negative t (e.g., H1 cost-dead regime) does not qualify.
        mom_sig = mom["t_stat"] > t_star
        rev_sig = rev["t_stat"] > t_star
        if mom_sig and not rev_sig:
            winner = "MOM"
        elif rev_sig and not mom_sig:
            winner = "REV"
        elif mom_sig and rev_sig:
            winner = "MOM" if mom["sharpe"] >= rev["sharpe"] else "REV"
        else:
            winner = "N.S."
        rows.append({
            "horizon": HORIZON_LABELS[h],
            "n_obs":   int(s.loc["mom_net", "n_obs"]),
            "mom_sr":  mom["sharpe"],
            "mom_t":   mom["t_stat"],
            "mom_mdd": mom["mdd"],
            "rev_sr":  rev["sharpe"],
            "rev_t":   rev["t_stat"],
            "rev_mdd": rev["mdd"],
            "winner":  winner,
        })
    return pd.DataFrame(rows)


def _format_percent(x, for_latex: bool = False):
    if pd.isna(x):
        return ""
    s = f"{x:.1%}"
    return s.replace("%", r"\%") if for_latex else s


def _format_number(x, spec):
    return "" if pd.isna(x) else format(x, spec)


def to_latex(df: pd.DataFrame, t_star: float) -> str:
    lines = [
        r"\begin{tabular}{@{}l r r r r r r r l@{}}",
        r"\toprule",
        r" & & \multicolumn{3}{c}{\textbf{Momentum (MOM-$h$)}} & \multicolumn{3}{c}{\textbf{Mean-Reversion (REV-$h$)}} & \\",
        r"\cmidrule(lr){3-5} \cmidrule(lr){6-8}",
        r"\textbf{$h$} & \textbf{$N$} & SR net & $t$-stat & MDD & SR net & $t$-stat & MDD & \textbf{Winner} \\",
        r"\midrule",
    ]
    for _, r in df.iterrows():
        n_obs = "" if pd.isna(r["n_obs"]) else f"{int(r['n_obs']):,}"
        lines.append(
            f"{r['horizon']} & {n_obs} & "
            f"{_format_number(r['mom_sr'], '+.2f')} & "
            f"{_format_number(r['mom_t'],  '+.2f')} & "
            f"{_format_percent(r['mom_mdd'], for_latex=True)} & "
            f"{_format_number(r['rev_sr'], '+.2f')} & "
            f"{_format_number(r['rev_t'],  '+.2f')} & "
            f"{_format_percent(r['rev_mdd'], for_latex=True)} & "
            f"{r['winner']} \\\\"
        )
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
    ]
    lines.append(
        rf"% Bonferroni two-sided $t^* \approx {t_star:.2f}$ (12 tests, $\alpha=0.05$). "
        r"N.S. = no strategy clears family-wise significance. H6 uses Newey-West $q=6$ $t$."
    )
    return "\n".join(lines)


def main() -> None:
    df = assemble()
    t_star = bonferroni_threshold(n_tests=12, alpha=0.05)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    ICM_TABLES.mkdir(parents=True, exist_ok=True)

    csv_path = PROCESSED / "headline_table.csv"
    tex_path = ICM_TABLES / "headline.tex"
    df.to_csv(csv_path, index=False)
    tex_path.write_text(to_latex(df, t_star))

    # Console render
    print(f"Bonferroni t* = {t_star:.4f} (12 tests, α = 0.05)")
    print()
    disp = df.copy()
    for c in ("mom_sr", "mom_t", "rev_sr", "rev_t"):
        disp[c] = disp[c].apply(lambda x: "" if pd.isna(x) else f"{x:+.3f}")
    for c in ("mom_mdd", "rev_mdd"):
        disp[c] = disp[c].apply(lambda x: "" if pd.isna(x) else f"{x:.1%}")
    print(disp.to_string(index=False))
    print()
    print(f"wrote {csv_path.relative_to(ROOT)}")
    print(f"wrote {tex_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
