"""One-shot regeneration of every ICM figure and table.

    python -m src.cli.make_report

Runs the 14+ sub-scripts under src/report/, src/robustness/, and the
Table-3 renderer, in dependency order, and writes outputs to:

    icm/figures/*.pdf, *.png
    icm/tables/*.tex
    data/processed/**/*.csv

Idempotent. Safe to rerun.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

STEPS: list[tuple[str, str]] = [
    # Robustness computations that figures depend on.
    ("src.robustness.variance_ratio",        "Variance-ratio term structure"),
    ("src.robustness.factor_regression",     "FF5 + Mom regression"),
    ("src.robustness.survivorship",          "Survivorship check"),
    ("src.robustness.look_ahead_audit",      "Look-ahead audit"),
    ("src.robustness.h2_cost_sensitivity",   "H2 cost sensitivity"),
    ("src.robustness.h2_bid_ask_bounce",     "H2 bid-ask bounce diagnostic"),
    ("src.robustness.h2_regime_time",        "H2 regime + time stability"),
    ("src.robustness.h6_nw_sensitivity",     "H6 NW lag sensitivity"),
    ("src.robustness.h2_bootstrap_sensitivity","H2 bootstrap block-length sensitivity"),
    ("src.robustness.h2_halfspread_cost",    "H2 half-spread-sourced cost model"),

    # Figures.
    ("src.report.horizon_plot",              "Figure 3 — horizon comparison"),
    ("src.report.equity_curves",             "H2 + H6 equity curves"),
    ("src.report.cost_sensitivity_plot",     "H2 cost sensitivity"),
    ("src.report.beta_spread_scatter",       "β vs spread scatter"),
    ("src.report.regime_plot",               "H2 year + VIX regime"),
    ("src.report.h2_diagnostics",            "Rolling SR, distribution, ACF"),
    ("src.report.per_ticker_contribution",   "Per-ticker decomposition"),

    # Tables.
    ("src.report.headline_table",            "Table 3 — headline"),
    ("src.report.per_horizon_table",         "Per-horizon detail table"),
    ("src.report.signal_moments",            "Panel integrity + signal moments table"),
    ("src.report.windowing_diagram",         "Signal / forward windowing figure"),
]


def main() -> None:
    print("=" * 70)
    print(" make_report — regenerating every ICM figure and table")
    print("=" * 70)
    t_all = time.perf_counter()
    failures = []

    for module, description in STEPS:
        t0 = time.perf_counter()
        print(f"\n>>> [{module}]  {description}")
        result = subprocess.run(
            [sys.executable, "-m", module],
            cwd=ROOT, capture_output=True, text=True,
        )
        dt = time.perf_counter() - t0
        if result.returncode != 0:
            failures.append((module, result.stderr.strip().splitlines()[-1]
                             if result.stderr else "unknown error"))
            print(f"  FAIL in {dt:4.1f}s")
            print(result.stderr[-1000:])
        else:
            # Print last line of stdout as quick confirmation
            last = [ln for ln in result.stdout.strip().splitlines() if ln][-1:]
            tag = last[0] if last else "(ok)"
            print(f"  OK   in {dt:4.1f}s  — {tag}")

    print()
    print("=" * 70)
    total = time.perf_counter() - t_all
    if failures:
        print(f" {len(failures)} FAILURES (total wall: {total:.1f}s):")
        for module, msg in failures:
            print(f"   {module}  —  {msg}")
        sys.exit(1)
    else:
        print(f" ALL GREEN — {len(STEPS)} steps in {total:.1f}s")
        print("=" * 70)

    # Inventory
    figs = sorted((ROOT / "icm" / "figures").glob("*.pdf"))
    tabs = sorted((ROOT / "icm" / "tables").glob("*.tex"))
    print(f"\nFigures written to icm/figures/ ({len(figs)} PDFs):")
    for f in figs:
        print(f"  {f.name}")
    print(f"\nTables written to icm/tables/ ({len(tabs)} .tex):")
    for f in tabs:
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
