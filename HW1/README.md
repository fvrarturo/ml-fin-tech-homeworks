# HW1 — Proprietary Trading on the Dow Jones 30

*15.C51 Project #1 (Spring 2026). Mean-reversion vs. momentum across six
horizons spanning nine orders of magnitude in time.*

**Team:** Arturo Favara, Eric Pan, Luke Miniutti.

## The assignment

> Using the last 10 years of daily stock price data for the Dow Jones 30,
> develop and backtest two proprietary trading strategies, one based on the
> idea of mean reversion, the other based on momentum. Provide an
> Investment Committee Memorandum (ICM) covering the rationale, profit/loss
> conditions, statistical properties of the cash flows and returns, and
> historical performance over the last 10 years.
>
> — *Project #1 handout, 15.C51 Spring 2026*

## Research frame

Rather than picking one mean-reversion and one momentum specification a
priori, we run **the same tercile long-short methodology at six horizons**
and let the data pick the winners. The methodological move is the novelty.


| Tag | Horizon                | Data                                | Construction                                 |
| --- | ---------------------- | ----------------------------------- | -------------------------------------------- |
| H1  | 30 min, intraday TAQ   | NYSE TAQ tick (Engaging cluster)    | Stretch goal — full TAQ aggregation pipeline |
| H2  | First-30 / rest-of-day | WRDS Intraday Indicators (`iid_ms`) | Gao et al. 2018 replication on DJ30          |
| H3  | 1 day                  | CRSP DSF                            | Lehmann (1990) one-day reversal              |
| H4  | 5 days (weekly)        | CRSP DSF                            | Lo–MacKinlay (1990)                          |
| H5  | 21 days (monthly)      | CRSP DSF                            | Jegadeesh (1990)                             |
| H6  | 126 days (semiannual)  | CRSP DSF                            | Jegadeesh–Titman (1993) with skip-1-month    |


At every horizon we run **both directions** (MOM and REV), giving 12
backtests under a uniform pipeline. The headline deliverable is a six-row
table of net Sharpe + Newey-West *t* + max drawdown, with a
Bonferroni-corrected significance threshold (`t* = 2.87` for 12 tests at
α=5%). The two strategies that ship into the ICM are the highest net
Sharpe in each family, conditional on clearing Bonferroni.

## Headline finding

After ~3 weeks of execution (Apr 13 → Apr 21, 2026), one horizon clears
Bonferroni: **H2 REV** — the intraday first-30/rest-of-day reversal — runs
at **net Sharpe +2.53, t = +7.86** with 1.5 bps per-side cost. Three
academic stress tests pass:

- **Cost.** Bonferroni break-even is 2.80 bps/side (round-trip 5.6 bps);
realistic DJ30 execution is ~1–1.5 bps/side.
- **Roll bid-ask bounce.** β-vs-spread cross-section ρ = −0.10 (R² = 0.01);
the tight-spread half of the universe still produces net Sharpe +1.23,
t +3.81.
- **Regime / time stability.** 10 / 10 calendar years positive, 5 / 5 VIX
quintiles positive; effect strengthened post-2020.

The classical daily-and-longer horizons (H3–H6) all fail Bonferroni on
DJ30 in this window — H6-MOM is the closest call but a Newey-West q=6
correction for 5-month overlap drops its t-stat from 2.43 to 1.37.

See `[_info/Work1_Part3_h2_stress_tests.md](_info/Work1_Part3_h2_stress_tests.md)`
for the H2 robustness write-up.

## Repository layout

```
HW1/
├── _info/                     # specifications and execution reports
│   ├── Work1.md                       # implementation bible (60+ KB, the source of truth)
│   ├── Work1_Part1_report.md          # Week-1 execution report — data + engine scaffold
│   ├── Work1_Part2_report.md          # Week-2 execution report — H3–H6 signals + Table 3
│   ├── Work1_Part3_h2_stress_tests.md # H2 REV cost / Roll / regime stress tests
│   └── eda/                           # earlier exploratory schema summary
├── data/
│   ├── REFERENCE_DATA.md              # DJ30 membership, NYSE early-close days, TAQ note
│   ├── interim/LOAD_NOTES.md          # ongoing data-quality log (CRSP/iid gaps)
│   ├── raw/                           # CRSP, iid_ms, IBES, GS supplements (gitignored)
│   ├── reference/                     # small CSVs in version control
│   ├── interim/                       # typed parquet panels, ready-to-backtest
│   └── processed/                     # backtest outputs (regenerated)
├── src/
│   ├── data/                          # CRSP / iid_ms / IBES loaders + cross-dataset validator
│   ├── signals/                       # one panel builder per horizon (H2 … H6)
│   ├── backtest/                      # tercile long-short engine, cost model, NW + Bonferroni
│   ├── robustness/                    # cost/Roll/regime tests, factor regression, audits
│   ├── report/                        # Table 3, equity curves, plots, headline LaTeX
│   ├── taq/                           # H1 stretch — bar aggregation for the Engaging cluster
│   └── cli/run_all.py                 # entry point: runs every horizon end-to-end
├── tests/                             # pytest tests for the TAQ aggregation layer
└── llm_logs/                          # one file per non-trivial LLM session (attribution)
```

## How the code is structured

A single CLI (`python -m src.cli.run_all`) walks the `HORIZON_CONFIG` list
and, for each horizon:

1. Loads the typed panel from `data/interim/{h2,h3,h4,h5,h6}_panel.parquet`.
2. Calls `src/backtest/engine.run_horizon` with the right cost model and
  `round_trip_each_rebalance` flag (intraday horizons round-trip every
   day, daily-and-longer horizons reuse positions across rebalances).
3. Writes `pnl.parquet`, `equity.csv`, `stats.csv`, `run_meta.json` to
  `data/processed/<horizon>/`.
4. `src/report/headline_table.py` collates the `stats.csv` files into
  Table 3 (CSV + LaTeX) with the Bonferroni "Winner" / "N.S." column.

The `signals/` modules all emit a uniform `(date, ticker, signal, ret_fwd)` schema so the engine is horizon-agnostic.

## Key design decisions

These were either surfaced via `AskUserQuestion` and locked in by the user,
or are non-obvious calls worth flagging:

- **Calendar.** CRSP ends 2025-09-30 and iid_ms ends 2025-12-31; we trim to
the CRSP end rather than re-pulling.
- **Universe completeness.** The PIT membership matrix produces exactly 30
DJ30 names on every one of 2,450 trading days, after concatenating a
supplementary GS pull (`*_gs.csv.gz`) that fills a gap in the original
WRDS extracts.
- **iid_ms dedup.** `SYM_ROOT` collapses preferreds, class-B shares, and
warrants onto common stock; we pick the security with the highest
`total_dollar_m` per `(date, ticker)`.
- **IBES join key.** Use `OFTIC` (the stable original ticker), not the
legacy `TICKER` field, which still carries old codes (NIKE, VISA, …).
- **Bonferroni.** 12 tests × α=5% two-sided ⇒ `t* = Φ⁻¹(1 − 0.00417/2) = 2.8653`.
- **Intraday cost accounting.** H1 and H2 round-trip every rebalance, so
the standard `|w_t − w_{t-1}|` turnover formula undercounts. The engine
has a `round_trip_each_rebalance` flag that forces turnover = 2 × gross
leverage at each rebalance for those horizons.

The full design discussion lives in
`[_info/Work1.md](_info/Work1.md)`. Everything else (`Part1`, `Part2`,
`Part3`) is week-by-week execution narrative for the next agent picking
up the project.

## Reproducing the results

From this directory:

```bash
# 1. Build typed panels from raw vendor pulls (one-time, ~1 minute):
python -m src.data.load_crsp
python -m src.data.load_iid
python -m src.data.load_ibes
python -m src.data.validate           # cross-dataset audit, must be all-green

# 2. Build per-horizon signal panels:
python -m src.signals.h2_iid
python -m src.signals.h3_daily
python -m src.signals.h4_weekly
python -m src.signals.h5_monthly
python -m src.signals.h6_semiannual

# 3. Run all 12 backtests + assemble Table 3:
python -m src.cli.run_all              # ~3 seconds end-to-end on a clean tree
python -m src.cli.make_report          # PDF/LaTeX exhibits

# 4. Robustness suite:
python -m src.robustness.h2_cost_sensitivity
python -m src.robustness.h2_bid_ask_bounce
python -m src.robustness.h2_regime_time
python -m src.robustness.factor_regression
python -m src.robustness.look_ahead_audit
# ... etc — see src/robustness/ for the full list
```

H1 (TAQ) runs separately on the **MIT Engaging cluster**. The
`src/taq/` module aggregates raw `TAQYYYY.csv.gz` ticks into 30-min bars;
the resulting `h1_panel.parquet` is rsync'd back to `data/interim/`
before being plugged into the same engine.

## LLM attribution

Each non-trivial Claude session is logged in `[llm_logs/](llm_logs/)` with
the prompt(s), the model (Opus 4.7, 1M context), the date, and a summary
of decisions and code produced:

- `[001_plan.md](llm_logs/001_plan.md)` — initial planning + Week-1 scaffolding
- `[002_week2.md](llm_logs/002_week2.md)` — H3–H6 signals + first 4 rows of Table 3
- `[003_week3.md](llm_logs/003_week3.md)` — H2 intraday + Gao et al. (2018) replication

## Status


| Week    | Scope                                                         | Status                         |
| ------- | ------------------------------------------------------------- | ------------------------------ |
| 1       | Loaders, engine scaffold, cross-dataset validator             | ✅ complete                     |
| 2       | H3 / H4 / H5 / H6 signal panels, Table 3 v1                   | ✅ complete                     |
| 3       | H2 intraday, Gao replication, intraday cost model, Table 3 v2 | ✅ complete                     |
| 4       | H2 robustness (cost / Roll / regime)                          | ✅ complete                     |
| 5       | Full robustness suite + ICM draft                             | in progress                    |
| Stretch | H1 TAQ on Engaging                                            | scaffolded, not run end-to-end |


