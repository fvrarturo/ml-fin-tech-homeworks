# Work1 Part 1 — Week-1 Execution Report

*Status: Week-1 scaffolding complete. 683 lines of new Python, nine files,
2 typed parquet panels produced. All cross-dataset checks green. Ready for
Week 2 (H3–H6 signal panels).*

*Companion to [`Work1.md`](Work1.md) (the implementation bible) and the plan
persisted at `.claude/plans/hazy-napping-moore.md`. Attribution for the session
that produced this work is [`../llm_logs/001_plan.md`](../llm_logs/001_plan.md).*

---

## Table of contents

- [0. TL;DR](#0-tldr)
- [1. What Week 1 set out to do](#1-what-week-1-set-out-to-do)
- [2. Planning phase](#2-planning-phase)
- [3. The codebase delivered](#3-the-codebase-delivered)
  - [3.1 Directory layout](#31-directory-layout)
  - [3.2 `src/data/load_crsp.py` — CRSP DSF loader](#32-srcdataload_crsppy--crsp-dsf-loader)
  - [3.3 `src/data/load_iid.py` — WRDS Intraday Indicators loader](#33-srcdataload_iidpy--wrds-intraday-indicators-loader)
  - [3.4 `src/data/load_ibes.py` — earnings-date loader](#34-srcdataload_ibespy--earnings-date-loader)
  - [3.5 `src/data/validate.py` — cross-dataset audit](#35-srcdatavalidatepy--cross-dataset-audit)
  - [3.6 `src/backtest/portfolio.py` — tercile long-short](#36-srcbacktestportfoliopy--tercile-long-short)
  - [3.7 `src/backtest/costs.py` — cost model](#37-srcbacktestcostspy--cost-model)
  - [3.8 `src/backtest/engine.py` — horizon-agnostic backtest](#38-srcbacktestenginepy--horizon-agnostic-backtest)
  - [3.9 `src/backtest/metrics.py` — summary stats](#39-srcbacktestmetricspy--summary-stats)
- [4. Bugs caught, diagnosed, fixed](#4-bugs-caught-diagnosed-fixed)
  - [4.1 CRSP duplicate at RTX 2020-04-03](#41-crsp-duplicate-at-rtx-2020-04-03)
  - [4.2 iid_ms multi-security rows under the same `SYM_ROOT`](#42-iid_ms-multi-security-rows-under-the-same-sym_root)
  - [4.3 GS missing from both WRDS extracts](#43-gs-missing-from-both-wrds-extracts)
  - [4.4 IBES uses a legacy `TICKER` code — must use `OFTIC`](#44-ibes-uses-a-legacy-ticker-code--must-use-oftic)
  - [4.5 UTX→RTX ticker-label mismatch on 2020-04-03](#45-utxrtx-ticker-label-mismatch-on-2020-04-03)
  - [4.6 IBES-GS gap (residual, non-blocking)](#46-ibes-gs-gap-residual-non-blocking)
- [5. Verification state](#5-verification-state)
- [6. First signal smoke test (H3 on real CRSP)](#6-first-signal-smoke-test-h3-on-real-crsp)
- [7. Decisions locked in this week](#7-decisions-locked-in-this-week)
- [8. What ships into Week 2](#8-what-ships-into-week-2)
- [9. Quick-start for the next agent](#9-quick-start-for-the-next-agent)

---

## 0. TL;DR

- **Planning.** Read the governing docs end-to-end, inventoried the existing
  EDA, surfaced three architecture-level decisions via `AskUserQuestion` (end
  date, H1 scope, earnings source), wrote a plan file, got it approved.
- **Scaffolding.** Created the full `src/` tree per Work1.md §2; moved
  reference CSVs into `data/reference/`; built the IBES raw into
  `data/raw/IBES.csv.gz`; created empty `data/interim/`, `data/processed/`,
  `llm_logs/`, `icm/`.
- **Loaders.** `load_crsp.py`, `load_iid.py`, `load_ibes.py` — 3 CLI scripts
  that read gzipped CSVs from `data/raw/`, apply type/rename/dedup/trim, and
  write typed parquet/CSV to `data/interim/` and `data/reference/`.
- **Validator.** `validate.py` — six cross-dataset audit checks; all green.
- **Engine.** `portfolio.py` + `costs.py` + `engine.py` + `metrics.py` — the
  horizon-agnostic backtest engine. Self-tests pass. An end-to-end smoke on the
  real CRSP panel (H3 = one-day reversal) produced the expected high-turnover,
  cost-dominated result.
- **Bugs found and squashed:** 5 non-trivial ones. Most notable: both WRDS
  extracts were missing Goldman Sachs on all 2,514 trading days; the user did
  a supplementary pull, I wired the loaders to concat it automatically.
- **Data quality:** the PIT merge now produces exactly 30 DJ30 members on every
  one of the 2,450 trading days in the 2016-01-04 → 2025-09-30 window.
- **Next:** Week 2 — H3/H4/H5/H6 signal builders plus the first four rows of
  the headline Table 3.

---

## 1. What Week 1 set out to do

Per the approved plan (`.claude/plans/hazy-napping-moore.md` §Execution /
Week 1), this week's scope:

1. Housekeeping — directory layout per Work1.md §2.
2. Data ingress — turn the three raw gzips into typed, filtered parquet panels
   the backtest can consume without re-parsing.
3. Engine scaffold — `portfolio.py`, `engine.py`, `costs.py`, `metrics.py`
   with unit tests, so Week 2 only has to write signal builders.
4. Verification gate — `validate.py` passes, engine self-tests pass, no real
   backtest run yet.

All four were achieved.

---

## 2. Planning phase

The session opened on a cold terminal with only `_info/`, `data/raw/`,
`data/` reference CSVs (not yet moved), a `src/eda/` with four read-only
scripts, and a `venv/` with pandas 3, pyarrow, statsmodels, scipy, sklearn,
lightgbm.

Flow:

1. Read [`_info/main_plan.tex`](main_plan.tex) and [`Work1.md`](Work1.md)
   end-to-end.
2. Ran a small `python` snippet to confirm schemas on the raw CSVs and the
   calendar-alignment gap (CRSP ends 2025-09-30, iid ends 2025-12-31 — Work1.md
   §3.6 was still unresolved).
3. Launched one Explore sub-agent to inventory `src/eda/*`, the existing
   `_info/eda/` output files, and the reference data layout. The agent's
   report surfaced four reusable utilities and the sign-flipping priors from
   prior EDA (H2 β = −0.029, H3 ρ₁ = −0.058, H6 VR(126) = 0.72 — all in
   reversal territory).
4. Drove three decisions via `AskUserQuestion`:
   - **Calendar:** trim iid_ms to 2025-09-30 (vs. re-pull CRSP).
   - **H1 TAQ:** full aggregation on MIT Engaging (vs. skip as stretch).
   - **Earnings:** user uploaded `data/IBES.csv.gz` (1,494 rows, 39 tickers).
5. Wrote the plan to `.claude/plans/hazy-napping-moore.md`; got it approved.
6. Entered execution.

Output of that phase: the plan file (~400 lines), plus
[`llm_logs/001_plan.md`](../llm_logs/001_plan.md) as the first attribution
entry.

---

## 3. The codebase delivered

### 3.1 Directory layout

```
HW1/
├── data/
│   ├── raw/
│   │   ├── dow_daily.csv.gz              # existing CRSP pull
│   │   ├── dow_daily_gs.csv.gz           # NEW: GS supplement
│   │   ├── dow_intraday.csv.gz           # existing iid pull
│   │   ├── dow_intraday_gs.csv.gz        # NEW: GS supplement
│   │   └── IBES.csv.gz                   # moved from data/
│   ├── reference/                        # populated from data/ root
│   │   ├── dj30_membership_{long,wide}.csv
│   │   ├── dj30_{events,tenure}.csv
│   │   ├── nyse_early_closes.csv
│   │   ├── ff_{fivefactors,mom}.csv
│   │   ├── VIXCLS.csv
│   │   ├── riskfree.csv
│   │   ├── permno_ticker.csv
│   │   └── earnings_dates.csv            # NEW: built by load_ibes.py
│   ├── interim/
│   │   ├── LOAD_NOTES.md                 # data-quality log
│   │   ├── daily.parquet                 # 92,681 rows × 22 cols
│   │   └── intraday.parquet              # 93,128 rows × 19 cols
│   └── processed/                        # empty until Week 2
├── src/
│   ├── data/      { load_crsp, load_iid, load_ibes, validate }.py
│   ├── backtest/  { portfolio, engine, costs, metrics }.py
│   ├── signals/   (empty — Week 2)
│   ├── robustness/(empty — Week 5)
│   ├── report/    (empty — Week 5)
│   ├── taq/       (empty — Week 4)
│   └── cli/       (empty — Week 2)
├── llm_logs/001_plan.md
└── icm/ { sections, tables, figures }    # empty — Week 6
```

Reference CSVs that were at `data/` root got moved into `data/reference/`.
IBES was moved from `data/` into `data/raw/` (it's vendor data). Everything
else was created fresh.

### 3.2 `src/data/load_crsp.py` — CRSP DSF loader

*98 lines.*

**Inputs:** `data/raw/dow_daily.csv.gz` plus any `dow_daily_gs.csv.gz`
supplement (the GS top-up).

**Transforms:**

- Concat the main file and every supplement in `RAW_SUPPLEMENTS` if present.
- Rename CRSP field names (`DlyCalDt → date`, `DlyRet → ret`, …) to snake_case.
- Parse `date` as `datetime64[ns]`, `permno` as int, `ticker` as pandas string.
- `abs()` on price columns (CRSP encodes midquote prices as negative).
- Filter `date ≤ end_date` (default `2025-09-30`, CLI-overridable).
- Drop the single known identical duplicate at RTX 2020-04-03 (§4.1).
- Ticker-label patch at UTX→RTX transition (§4.5).

**Output:** `data/interim/daily.parquet` — 92,681 rows × 22 columns.

**CLI:** `python -m src.data.load_crsp [--end-date YYYY-MM-DD]`.

**Asserts:** exactly 40 unique tickers; no duplicate `(permno, date)`.

### 3.3 `src/data/load_iid.py` — WRDS Intraday Indicators loader

*118 lines.*

**Inputs:** `data/raw/dow_intraday.csv.gz` + `dow_intraday_gs.csv.gz` supplement.

**Transforms:**

- Concat main + supplement.
- Rename `SYM_ROOT → ticker`, `OPrc → open`, `CPrc → close`, …
- `quoted_spread_bps = QuotedSpread_Percent_tw × 1e4` — convert percentage
  fraction to bps for consistency with downstream cost talk.
- **Dedupe multi-security rows** (§4.2): sort by
  `(date, ticker, total_dollar_m desc)` and keep the first row per
  `(date, ticker)`. Common stock dominates by 1–3 orders of magnitude so the
  pick is unambiguous — 21,446 duplicate rows shed this way.
- Filter `date ≤ end_date`.
- UTX→RTX ticker patch on 2020-04-03 (§4.5).

**Output:** `data/interim/intraday.parquet` — 93,128 rows × 19 columns.

**Keep-set columns** chosen to cover the H2 signal (`mid_after_open` — a ~5-min
VWAP midprice proxy for the first-30-min window — plus `OPrc` and `CPrc`) and
the robustness-set microstructure features (`quoted_spread_bps`,
`price_impact`, `bs_ratio_vol`, `ivol_t`, `ivol_q`, `var_ratio1..5`).

**CLI:** `python -m src.data.load_iid [--end-date YYYY-MM-DD] [--audit-early-close]`.

The `--audit-early-close` flag prints, for each of the 19 short-session days in
the window, the mean absolute difference between `mid_before_close` and the
session `close`. Non-zero means WRDS re-windowed the midprice to pre-13:00 on
short sessions, as it should; flat zeros would flag an audit failure. Every
day tested comes back with a ~\$0.04–\$0.22 diff, so WRDS's session logic is
correct.

### 3.4 `src/data/load_ibes.py` — earnings-date loader

*83 lines.*

**Inputs:** `data/raw/IBES.csv.gz` (1,494 rows, 39 tickers, quarterly EPS
announcements 2016–2025 from the user's WRDS pull).

**Transforms:**

- Parse `ANNDATS` (announcement date), `ANNTIMS` (time HH:MM:SS),
  `PENDS` (period ending).
- **Classify timing** — `BMO` (before 09:30 ET), `AMC` (at or after 16:00 ET),
  `INTRADAY` (anything else). Downstream §8.7 blackout uses this:
  - `BMO → blackout = [D-1, D]`
  - `AMC → blackout = [D, D+1]`
  - `INTRADAY → blackout = [D-1, D+1]` (conservative).
- **Use `OFTIC` not `TICKER`** (§4.4). `TICKER` is a legacy IBES symbol (NIKE,
  VISA, UNIH, CHV, WAG, XON, …); `OFTIC` is the stable trading symbol that
  joins to CRSP.
- Filter `earnings_date ≤ end_date`.
- Drop duplicates on `(ticker, earnings_date)`.

**Output:** `data/reference/earnings_dates.csv` — 1,436 rows × 6 cols.

**Distribution:** 962 BMO, 471 AMC, 3 INTRADAY announcements. Large caps tend
toward bookend timing, so the mix is plausible.

### 3.5 `src/data/validate.py` — cross-dataset audit

*105 lines.*

Six checks, each labeled R0–R6 (R-for-"rule"), colored green/red to terminal;
exits 0 on all green, 1 otherwise.

| Rule | What it enforces |
|---|---|
| R0 | `data/interim/daily.parquet` exists |
| R1 | `data/interim/intraday.parquet` exists |
| R2 | CRSP and iid cover the same calendar window (same min and max `date`) |
| R3 | Every PIT-merged trading day has exactly 30 DJ30 members |
| R4 | `ret` vs. `retx` divergence is between 0.5% and 15% of rows (dividend sanity; too high flags a data bug, too low flags total-return/price-only mixup) |
| R5 | `permno_ticker.csv` covers the DD/DWDP/DOW and UTX/RTX chains |
| R6 | Each always-present ticker has ≥30 earnings announcements (tolerates the GS-IBES gap; 1 sparse ticker allowed) |

Current state: all green. R3 is the load-bearing check for the backtest —
without it, signal panels would silently run on incomplete universes.

### 3.6 `src/backtest/portfolio.py` — tercile long-short

*81 lines.*

The core portfolio primitive. Single function:

```python
terciles_longshort(df, signal_col="signal", date_col="date") → df + [rk, q, w_mom, w_rev]
```

Per date:

1. Rank by `signal_col` with method `first` (stable tie-break).
2. Assign each row a tercile label: `lo` (bottom third), `mi` (middle), `hi`
   (top third).
3. Equal-weight within each leg and scale so that `sum(|w_mom|) = 1` (gross
   leverage 1). MOM is `+1/(2·leg_size)` on the top leg and `−1/(2·leg_size)` on
   the bottom; REV is exact negative.

**Invariants verified in `__main__`:**

- `sum(w_mom) = 0` (dollar-neutral) to 1e-12.
- `sum(|w_mom|) = 1` (gross 1) to 1e-12.
- `w_mom == -w_rev` exactly.
- Tercile sizes are 10/10/10 on a 30-name universe.

Running `python -m src.backtest.portfolio` prints a one-line pass.

### 3.7 `src/backtest/costs.py` — cost model

*28 lines.*

Work1.md §5.4 formula: per-rebalance turnover = L1 change in weights
(date-wise), multiplied by a per-side bps cost.

```python
turnover(weights_wide)      → pd.Series per date
cost_drag(weights_wide, bp) → pd.Series per date
```

First-period turnover = gross leverage (= 1) since prior weights are zero.

### 3.8 `src/backtest/engine.py` — horizon-agnostic backtest

*81 lines.*

One function:

```python
run_horizon(panel, cost_bps=1.5, target="ret_fwd", signal_col="signal") → pd.DataFrame
```

Flow:

1. Call `terciles_longshort` to get per-row MOM/REV weights.
2. Compute gross P&L per date: `Σᵢ wᵢ × ret_fwdᵢ` for both MOM and REV.
3. Pivot `w_mom` into a wide (`date × ticker`) frame, call `turnover()`, apply
   per-side bps.
4. Assemble output with columns `[mom_gross, mom_net, rev_gross, rev_net, turnover]`,
   date-indexed.

**Smoke test** in `__main__`: builds a 100-day, 30-name synthetic panel where
forward return is weakly anti-correlated with signal (true REV process).
Asserts:

- MOM gross + REV gross = 0 row-wise (exact mirror).
- Turnover ∈ [0, 2].
- REV net mean > MOM net mean (the synthesis is a reversal process; engine
  should discover it).

Passes.

### 3.9 `src/backtest/metrics.py` — summary stats

*89 lines.*

Work1.md §5.5–5.6. Functions:

- `summarize(pnl, periods_per_year, cols=None, nw_lags=0)` — returns one row
  per P&L column with `n_obs, mean, std, ann_ret, ann_vol, sharpe, t_stat,
  t_stat_nw, max_dd`.
- `max_drawdown(cum_wealth)` — negative-signed peak-to-trough DD on a wealth
  series.
- `newey_west_tstat(x, lags)` — HAC-adjusted t-stat using
  `statsmodels.OLS(...).fit(cov_type="HAC", cov_kwds={"maxlags": q})`. Used at
  H6 with `q = 6` to correct for the 5-month overlap in 126-day forward returns
  rebalanced monthly.
- `bonferroni_threshold(n=12, α=0.05)` — two-sided z-critical at family-wise
  error rate. Returns **2.8653** for 12 tests at 5%, matching the ~2.87 quoted
  in Work1.md §5.6.

Smoke test in `__main__` confirms: on a mu=5bp, sigma=1% daily-return series
of length 2,500, Sharpe ≈ 1.24 annualized, naive t = 3.90, NW t = 3.79.

---

## 4. Bugs caught, diagnosed, fixed

Every non-trivial issue that surfaced during Week 1, in the order it appeared.

### 4.1 CRSP duplicate at RTX 2020-04-03

**Symptom.** `AssertionError: duplicate (permno, date)` on first run of
`load_crsp.py`.

**Diagnosis.** Two identical rows in the raw CRSP pull — same PERMNO (17830),
same `DlyCalDt` (2020-04-03), same close ($49.93), same return, same volume.
This is the last Friday before the UTC+Raytheon merger index-switch; CRSP
appears to have written the RTX row twice at the ticker-change boundary.

**Fix.** `df.drop_duplicates(["permno", "date"])` with a comment in the
loader; one-line change.

**Impact.** Zero after dedup.

### 4.2 iid_ms multi-security rows under the same `SYM_ROOT`

**Symptom.** `AssertionError: duplicate (date, ticker) in iid` on first run of
`load_iid.py` — 21,446 duplicate rows.

**Diagnosis.** iid_ms uses `SYM_ROOT` as its primary ticker column but actually
covers every listed security under that root. JPM has 18 sub-securities
(common + JPMPRA … JPMPRM + JPMWS warrant), DD has 3, BA 2, plus minor ones.
The `symbol` column (SYM_ROOT+SYM_SUFFIX composite) disambiguates but is
discarded by WRDS's pre-aggregated intraday panel.

**Fix.** Before dedup: sort by `(date, ticker, total_dollar_m desc)`, then
`drop_duplicates(["date", "ticker"])` with `keep="first"`. The common stock
dominates dollar volume by 1–3 orders of magnitude (e.g., JPM common has
\$1.57 B / day vs. JPMPRA at \$3 M / day) so the pick is unambiguous.

**Verification.** Spot-checked JPM and DD 2016-01-04 dollar-volume vectors;
confirmed the picked row is the common-stock row each time.

### 4.3 GS missing from both WRDS extracts

**Symptom.** `R3 FAIL` in validator: min=28, max=29, modal=29 names per day;
the PIT merge was dropping GS on every trading day.

**Diagnosis.**

1. Listed CRSP unique tickers: 39. Compared against `dj30_tenure.csv` (40).
   Diff = `{GS}`.
2. Listed iid `SYM_ROOT` unique: 39, same set; also checked `symbol` column
   (more granular) for any `GS*` variant — none.
3. Goldman Sachs is a DJ30 member on all 2,514 trading days in the window
   (100% coverage per the membership file). Missing it means every PIT merge
   runs on 29 names per day, and tercile sizes fall from 10/10/10 to 10/9/10
   or similar.

**Root cause.** The WRDS extract was run without PERMNO 86868. Either the
ticker list was missing GS, or a PERMNO filter capped the set.

**Fix.**

1. Told the user "GS is missing from both extracts."
2. Listed the 40 PERMNOs they need in the re-pull:
   ```
   10107 10145 11308 11703 11850 12060 12490 14008 14541 14593 16851 17830
   18163 18428 18542 19502 19561 20626 21936 22111 22592 22752 26403 36468
   43449 47896 55976 57665 59176 59328 59459 65875 66181 76076 84788 86580
   86868 90215 92611 92655
   ```
3. User ran a supplementary WRDS pull for PERMNO 86868 and dropped the results
   at `data/CRSP_GS.csv.gz` and `data/iid_GS.csv.gz`.
4. Moved both files into `data/raw/` as `dow_daily_gs.csv.gz` and
   `dow_intraday_gs.csv.gz`.
5. Updated both loaders with a `RAW_SUPPLEMENTS` list and a concat step. The
   supplement file is used only if it exists, so a future full CRSP re-pull
   that includes GS can ship as one file — delete the `_gs` supplement and
   everything still works.

**Impact after fix.** R3 shows min=30, max=30, modal=30 on all 2,450 trading
days. Row counts rose from 90,231 → 92,681 (CRSP) and 90,678 → 93,128 (iid).

### 4.4 IBES uses a legacy `TICKER` code — must use `OFTIC`

**Symptom.** `R6 FAIL`: "8 always-present tickers have <30 earnings" (CVX, GS,
JPM, NKE, TRV, UNH, V, VZ — every one had zero earnings).

**Diagnosis.** Dumped IBES `TICKER` vs. `OFTIC` unique value sets.

- `TICKER` contains **legacy codes**: NIKE (Nike), VISA (Visa), UNIH
  (UnitedHealth), CHV (Chevron), WAG (Walgreens), XON (ExxonMobil), BEL
  (BellSouth), ALD (AlliedSignal), etc.
- `OFTIC` contains the **stable trading ticker**: CVX, NKE, UNH, V, …

Every "missing" ticker was present under `OFTIC`, absent under `TICKER`. Not a
data gap — a column-choice bug.

**Fix.** Change `TICKER → OFTIC` in the IBES loader's `pd.DataFrame({...})`
construction.

**Impact after fix.** R6 passes with 1 sparse ticker (GS — its earnings are
genuinely absent from IBES; see §4.6).

### 4.5 UTX→RTX ticker-label mismatch on 2020-04-03

**Symptom.** Even after the GS supplement, R3 showed `min=29, n_days=2450,
n_short(<29)=1`. One single day had 29 names.

**Diagnosis.**

1. Found the short day: 2020-04-03.
2. Listed expected vs. actual members on that date. Expected includes UTX;
   actual (post-merge with CRSP) has RTX but not UTX.
3. Cross-referenced `dj30_events.csv`: the UTC+Raytheon merger closed on Fri
   2020-04-03 and **the S&P DJI index switch was Mon 2020-04-06**. CRSP
   relabels the PERMNO (17830) the same day the merger closes; the index kept
   the name UTX through 2020-04-03 inclusive.

**Fix.** Single-cell ticker patch in both CRSP and iid loaders:

```python
mask = (df["ticker"] == "RTX") & (df["date"] == pd.Timestamp("2020-04-03"))
df.loc[mask, "ticker"] = "UTX"
```

(CRSP version keyed on PERMNO 17830 for defensibility.) The underlying security
is the same merged entity; only the label differs between CRSP's legal-entity
convention and S&P DJI's index rules.

**Impact after fix.** R3: min=30, max=30, modal=30, 2,450 / 2,450 days —
completely clean.

### 4.6 IBES-GS gap (residual, non-blocking)

**Fact.** The IBES pull has 39 `OFTIC` codes; GS is absent.

**Impact.** Minor. The §8.7 earnings-blackout robustness check will treat GS
as having no earnings announcements and therefore never be blacked out.
Sharpes attributable to GS positions are not adjusted for earnings drift.

**Remediation.** Optional — add GS to a future IBES WRDS pull and concat with
`src/data/load_ibes.py`. Validator R6 is tolerant of 1 sparse always-present
ticker so the pipeline runs.

---

## 5. Verification state

Running `python -m src.data.validate` from a clean state:

```
Cross-dataset validation
============================================================
  PASS  R0 CRSP parquet present  — data/interim/daily.parquet
  PASS  R1 iid parquet present  — data/interim/intraday.parquet
  PASS  R2 CRSP and iid share calendar  — crsp 2016-01-04→2025-09-30, iid 2016-01-04→2025-09-30
  PASS  R3 PIT merge yields 30 names per day  — min=30, max=30, modal=30, n_days=2450
  PASS  R4 ret vs retx divergence is plausible  — 1.45% of rows have material DlyRet != DlyRetx
  PASS  R5 permno map covers DD/DWDP/DOW + UTX/RTX chains  — missing: set()
  PASS  R6 ≥30 earnings announcements for each always-present ticker  — 1 always-present ticker(s) have <30 earnings
============================================================
ALL GREEN
```

Unit tests from `python -m src.backtest.portfolio` and `python -m src.backtest.engine`
pass. `python -m src.backtest.metrics` sanity-checks NW vs. naive t.

---

## 6. First signal smoke test (H3 on real CRSP)

To confirm end-to-end wiring, built an ad-hoc H3 panel (signal = today's
`ret`, forward = tomorrow's `ret`) against the full 30-name CRSP panel and ran
`run_horizon(cost_bps=1.5)`:

| | `n_obs` | ann_ret | ann_vol | sharpe | t_stat | max_dd |
|---|---:|---:|---:|---:|---:|---:|
| `mom_gross` | 2,449 | +0.27% | 7.11% | +0.04 | +0.12 | −20.7% |
| `mom_net`   | 2,449 | −4.75% | 7.11% | **−0.67** | **−2.08** | −42.3% |
| `rev_gross` | 2,449 | −0.27% | 7.11% | −0.04 | −0.12 | −24.3% |
| `rev_net`   | 2,449 | −5.29% | 7.11% | **−0.74** | **−2.32** | −43.3% |

Average turnover **1.33 per day**. At 1.5 bps per side that costs ~5.0%
annualized — net Sharpe is cost-dominated regardless of direction. Both naive
t-stats are below the Bonferroni threshold (2.87) in absolute value, so
**neither H3-MOM nor H3-REV clears family-wise significance at 5%** in this
preliminary run.

That's exactly the kind of finding the horizon comparison is built to
surface: on DJ30 large caps with daily rebalance, tercile long-short with
classical returns-as-signal is eaten by transaction costs. The interesting
horizons will be the ones that rebalance less often (H5, H6) where gross edge
stays but turnover drops an order of magnitude.

*Note: this is not an official Table-3 row. The real H3 panel will be built by
`src/signals/h3_daily.py` in Week 2 and written to
`data/interim/h3_panel.parquet` — the smoke test just pipes CRSP through the
engine directly.*

---

## 7. Decisions locked in this week

| # | Decision | Rationale |
|---|---|---|
| 1 | **End date: 2025-09-30.** iid_ms trimmed; CRSP re-pull deferred. | Lossless for the horizon comparison. Documented in ICM §10. `--end-date` CLI on every loader if this ever flips. |
| 2 | **H1 TAQ: full cluster aggregation.** | TAQ is on MIT Engaging already (`~/Fin_Tech/HW1/data/TAQYYYY.csv.gz`, one file per year). Zero prior code. Week-4 scope. |
| 3 | **Earnings: IBES via user's WRDS pull.** `data/raw/IBES.csv.gz`. | 1,436 announcements across 39 tickers; enough for §8.7. |
| 4 | **ICM render: LaTeX.** | Consistent with `_info/main_plan.tex`; colors/preamble reused. |
| 5 | **GS gap: supplementary pull, concat in loaders.** | User's supplementary WRDS pull was the cleanest fix. Loader logic survives a future full re-pull. |
| 6 | **UTX→RTX ticker label: legacy-side (UTX) wins on 2020-04-03.** | Aligns CRSP and iid with S&P DJI's index rules. Single-cell patch; no forward-return discontinuity since the merged stock is the same security. |

---

## 8. What ships into Week 2

Entering Week 2 with this baseline:

- Two typed parquet panels in `data/interim/` ready to consume.
- A horizon-agnostic engine that turns any `(date, ticker, signal, ret_fwd)`
  panel into a P&L frame with a one-line call.
- A metrics module that produces Table-3-shape summary stats, including
  Newey-West correction for H6 and a Bonferroni threshold helper.
- Validator guarantees on data quality (30 names per day, calendar alignment,
  earnings coverage).
- Reference data, including the newly built `earnings_dates.csv`.

Week-2 work (per plan `.claude/plans/hazy-napping-moore.md`):

1. `src/signals/_common.py` — shared PIT-merge helper with the 30-names
   assertion.
2. `src/signals/h3_daily.py` — one-day reversal signal panel.
3. `src/signals/h4_weekly.py` — Friday-close rebalance, 5-day momentum.
4. `src/signals/h5_monthly.py` — month-end rebalance, 21-day momentum.
5. `src/signals/h6_semiannual.py` — monthly rebalance, 6-month Jegadeesh-Titman
   signal with skip-1-month convention.
6. `src/cli/run_all.py` (partial) — loop over H3–H6, write per-horizon
   `pnl.parquet`, `stats.csv`, `equity.csv`, `run_meta.json`.
7. `src/report/headline_table.py` (v1) — Table 3 rendered as CSV + LaTeX
   fragment, four rows filled.

Verification gate: H3 REV gross Sharpe > 0 (reversal prior); H6 NW t ≤ naive
t; every panel's `nunique == 30` assertion holds.

---

## 9. Quick-start for the next agent

To pick up where we left off, from a clean shell:

```bash
cd ~/Desktop/HW1
source venv/bin/activate

# Rebuild everything from raw → typed parquet
python -m src.data.load_crsp     # → data/interim/daily.parquet
python -m src.data.load_iid      # → data/interim/intraday.parquet
python -m src.data.load_ibes     # → data/reference/earnings_dates.csv
python -m src.data.validate      # all green expected

# Self-tests
python -m src.backtest.portfolio  # 5 dates × 30 names pass
python -m src.backtest.engine     # mirror invariant + REV wins on synthetic
python -m src.backtest.metrics    # NW ≤ naive on random walk
```

**Relevant reading:**

- `.claude/plans/hazy-napping-moore.md` — the plan (Week 2 is the next block).
- `_info/Work1.md` §§5–7 — unified methodology, horizon-by-horizon spec, engine
  contract.
- `data/interim/LOAD_NOTES.md` — all known data-quality caveats.
- `_info/eda/` — prior EDA (autocorrelations, variance ratios, Gao β) whose
  numbers Week 2 will reproduce under point-in-time filtering.

*End of Week-1 report. Proceed to Week 2.*
