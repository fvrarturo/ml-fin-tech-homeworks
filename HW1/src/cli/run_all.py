"""Run every signal panel in data/interim/ through the backtest engine.

Usage:
    python -m src.cli.run_all                   # all available horizons
    python -m src.cli.run_all --horizons H3 H5  # subset

Outputs per horizon Hk:
    data/processed/hk_pnl.parquet      (per-rebalance P&L, both MOM and REV)
    data/processed/hk_equity.csv       (cumulative wealth)
    data/processed/hk_stats.csv        (Table-3 row: n, ann_ret, ann_vol, SR, t, NW-t, MDD)
    data/processed/hk_run_meta.json    (reproducibility metadata)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.backtest.engine import run_horizon
from src.backtest.metrics import summarize

ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

# Per-horizon config.
#   round_trip=True  : fully unwound every rebalance (H2 only — hold 10am→4pm,
#                      close overnight). Turnover fixed at 2 × gross_leverage.
#   round_trip=False : positions carry across rebalances with incremental
#                      turnover |w_t - w_{t-1}|. H1 is bar-to-bar intraday —
#                      rebalances every 30 min but the new position is a
#                      reshuffle of the prior one, not a flat-to-position trade,
#                      so incremental turnover is the right model. The overnight
#                      unwind+reopen at the last/first bar of each day adds a
#                      bounded extra cost we absorb into the higher cost_bps=3.0.
HORIZON_CONFIG: dict[str, dict] = {
    "H1": {"cost_bps": 3.0, "periods_per_year": 2772, "nw_lags": 0, "round_trip": False},
    "H2": {"cost_bps": 1.5, "periods_per_year": 252,  "nw_lags": 0, "round_trip": True},
    "H3": {"cost_bps": 1.5, "periods_per_year": 252,  "nw_lags": 0, "round_trip": False},
    "H4": {"cost_bps": 1.5, "periods_per_year": 52,   "nw_lags": 0, "round_trip": False},
    "H5": {"cost_bps": 1.5, "periods_per_year": 12,   "nw_lags": 0, "round_trip": False},
    "H6": {"cost_bps": 1.5, "periods_per_year": 12,   "nw_lags": 6, "round_trip": False},
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()[:16]}"


def run_one(horizon: str, cfg: dict) -> None:
    panel_path = INTERIM / f"{horizon.lower()}_panel.parquet"
    if not panel_path.exists():
        print(f"  {horizon}: panel missing ({panel_path.name}); skip")
        return

    t0 = datetime.now(timezone.utc)
    panel = pd.read_parquet(panel_path)
    pnl = run_horizon(
        panel,
        cost_bps=cfg["cost_bps"],
        round_trip_each_rebalance=cfg.get("round_trip", False),
    )
    stats = summarize(
        pnl, periods_per_year=cfg["periods_per_year"], nw_lags=cfg["nw_lags"]
    )
    equity = (1 + pnl[["mom_net", "rev_net"]]).cumprod()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    pnl.to_parquet(PROCESSED / f"{horizon.lower()}_pnl.parquet")
    equity.to_csv(PROCESSED / f"{horizon.lower()}_equity.csv")
    stats.to_csv(PROCESSED / f"{horizon.lower()}_stats.csv")

    meta = {
        "horizon": horizon,
        "cost_bps": cfg["cost_bps"],
        "periods_per_year": cfg["periods_per_year"],
        "nw_lags": cfg["nw_lags"],
        "round_trip": cfg.get("round_trip", False),
        "panel_path": str(panel_path.relative_to(ROOT)),
        "panel_hash": _sha256(panel_path),
        "panel_rows": int(len(panel)),
        "n_rebalances": int(len(pnl)),
        "avg_turnover": float(pnl["turnover"].mean()),
        "start_utc": t0.isoformat(timespec="seconds"),
        "end_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with (PROCESSED / f"{horizon.lower()}_run_meta.json").open("w") as f:
        json.dump(meta, f, indent=2)

    mom = stats.loc["mom_net", ["ann_ret", "sharpe", "t_stat", "max_dd"]]
    rev = stats.loc["rev_net", ["ann_ret", "sharpe", "t_stat", "max_dd"]]
    print(
        f"  {horizon}  N={meta['n_rebalances']:4d}  "
        f"MOM: SR={mom['sharpe']:+.3f} t={mom['t_stat']:+.2f} MDD={mom['max_dd']:.1%}   "
        f"REV: SR={rev['sharpe']:+.3f} t={rev['t_stat']:+.2f} MDD={rev['max_dd']:.1%}   "
        f"turn={meta['avg_turnover']:.2f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizons", nargs="+", default=None)
    args = ap.parse_args()

    horizons = args.horizons or list(HORIZON_CONFIG.keys())
    print(f"run_all: {', '.join(horizons)}")
    print("-" * 100)
    for h in horizons:
        if h not in HORIZON_CONFIG:
            print(f"  {h}: unknown horizon; skip")
            continue
        run_one(h, HORIZON_CONFIG[h])


if __name__ == "__main__":
    main()
