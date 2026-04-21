# Work1.md — Implementation Bible

*15.C51 Project 1 — Proprietary Trading Track. Horizon Comparison on DJ30, 2016–2026.*

*Companion to [`_info/FinTech1_MainPlan.pdf`](FinTech1_MainPlan.pdf) (the v3 project guide). Reference datasets are documented in [`REFERENCE_DATA.md`](REFERENCE_DATA.md).*

---

## 0. How to read this document

This file is the bridge between the plan (which is deliberately lean on implementation detail) and the code that has to run. Every subsection that begins with **Task** is a concrete deliverable: inputs specified, outputs specified, verification steps specified. Every subsection that begins with **Reference** is context — read once, come back when needed.

If you are an agent (human or LLM) picking up a chunk of this project, find the relevant horizon section (§6) or robustness task (§8), read its Task block, and do exactly what it says. When a choice of convention arises that the plan leaves loose, §6 and §8 commit to one and explain why.

The two governing documents take precedence in this order:

1. [`FinTech1_MainPlan.pdf`](FinTech1_MainPlan.pdf) — the assignment and the research frame
2. This file — concrete implementation
3. Prior docs (old `Work1.md`, `WORK2.md`, `LEAN.md`) — **deprecated**, superseded by this file. Delete them after reading once; they describe an older strategy architecture that the v3 plan walks back from.

---

## Table of contents

- [1. Project overview](#1-project-overview)
- [2. Repository structure](#2-repository-structure)
- [3. Data sources](#3-data-sources)
- [4. Universe construction](#4-universe-construction-complete)
- [5. Unified methodology](#5-unified-methodology)
- [6. Horizon-by-horizon specification](#6-horizon-by-horizon-specification)
- [7. Core engine](#7-core-engine)
- [8. Robustness suite](#8-robustness-suite)
- [9. The headline comparison](#9-the-headline-comparison)
- [10. Strategy selection for the ICM](#10-strategy-selection-for-the-icm)
- [11. ICM structure](#11-icm-structure)
- [12. Week-by-week plan](#12-week-by-week-plan)
- [13. Pitfalls catalog](#13-pitfalls-catalog)
- [14. Methods references](#14-methods-references)
- [15. LLM attribution protocol](#15-llm-attribution-protocol)
- [Appendix A. Code skeletons](#appendix-a-code-skeletons)
- [Appendix B. Expected output files](#appendix-b-expected-output-files)
- [Appendix C. Agent interaction protocol for cluster work](#appendix-c-agent-interaction-protocol-for-cluster-work)

---

## 1. Project overview

### 1.1 What the assignment asks

*(Verbatim from the project handout, paraphrased in Plan §1.1.)* Using 10 years of daily price data for the Dow Jones 30, develop and backtest two proprietary trading strategies — one mean-reversion, one momentum — and deliver an Investment Committee Memorandum (ICM) describing each strategy's rationale, profit/loss conditions, statistical properties of the cash flows and returns, and historical performance over the last 10 years.

### 1.2 The v3 plan we are implementing

The v3 plan (`FinTech1_MainPlan.pdf`) keeps the assignment's two-strategy deliverable but enriches the study with one methodological move: **we run the same strategy at six horizons spanning nine orders of magnitude in time and let the data pick the winners.**

- Six horizons: H1 (30 min, TAQ) → H6 (6 months, CRSP)
- One uniform methodology: at each horizon, rank the DJ30 by past-horizon return, go long the top tercile and short the bottom tercile (momentum); reverse the signs to get the mean-reversion version
- Twelve backtests total (6 horizons × 2 directions)
- Headline deliverable is a six-row table of net Sharpe + t-stat + max drawdown for each of the twelve strategies
- The two strategies that go in the ICM are whichever MOM-h and REV-h have the highest net Sharpe subject to passing a Bonferroni-corrected significance threshold

### 1.3 Deliverable

One ICM document, roughly 20–25 pages (plan §9.1), containing:

1. Executive summary (1 page)
2. Research frame (1 page) — the horizon-comparison thesis + Figure 1
3. Unified methodology (2 pages)
4. The horizon comparison (3 pages) — Table 3 + Figure 3
5. Selected Strategy #1 "Best Mean-Reversion" (3–4 pages)
6. Selected Strategy #2 "Best Momentum" (3–4 pages)
7. Statistical properties (2 pages)
8. Robustness (2 pages)
9. Implementation & risk (1 page)
10. Limitations (1 page)
11. Appendix

### 1.4 Grading axes (25 points each)

| Axis | What moves the needle |
|---|---|
| Completeness | All 12 backtests run; robustness suite complete; cost model applied uniformly |
| Novelty | The cross-horizon comparison is the novelty; the sign-flipping-across-horizons story is what nobody else will have |
| Readability | Sell-side memo style; numbers in tables; no hedging without quantification |
| Attribution | Every non-trivial LLM interaction logged; §15 protocol |

### 1.5 Status as of today (2026-04-17)

**Complete:**

- Point-in-time DJ30 membership matrix, 2016-01-04 → 2025-12-31, 2,514 trading days, 40 ever-members, 30 per day (see `dj30_membership_long.csv` and [`REFERENCE_DATA.md`](REFERENCE_DATA.md))
- Index event log (10 events from 2017-09 to 2024-11)
- NYSE early-close day list (21 short sessions for intraday logic)
- Fama-French 5-factor daily (available; needed only if we add a factor regression to the robustness suite)

**In progress:**

- CRSP DSF extract (`dow_daily.csv.gz`) and iid_ms panel (`dow_intraday.csv.gz`) pulled, not yet loaded/typed into `interim/` parquet
- TAQ consolidated-trades pull in progress on MIT Engaging cluster

**Not started:**

- Signal construction at any horizon
- The backtest engine
- Any robustness analysis
- The ICM

**Blocking cross-cutting prerequisites:**

- VIX daily close series (for regime split in §8.3) — CBOE public CSV, trivial to pull
- Earnings date calendar for the 40 ever-members (for earnings-blackout robustness) — IBES on WRDS or free scrape
- Optional: Fama-French momentum factor (`F-F_Momentum_Factor_daily`) if we add a factor regression

---

## 2. Repository structure

```
HW1/
├── _info/
│   ├── FinTech1_MainPlan.pdf       # the project guide (v3)
│   ├── Work1.md                     # this file
│   └── REFERENCE_DATA.md            # documents reference datasets
├── data/
│   ├── raw/                         # vendor data, never edited
│   │   ├── dow_daily.csv.gz
│   │   └── dow_intraday.csv.gz
│   ├── reference/                   # small, version-controlled, human-inspectable
│   │   ├── dj30_membership_long.csv
│   │   ├── dj30_membership_wide.csv
│   │   ├── dj30_events.csv
│   │   ├── dj30_tenure.csv
│   │   ├── nyse_early_closes.csv
│   │   └── F-F_Research_Data_5_Factors_2x3_daily.csv
│   ├── interim/                     # typed Parquet, ready-to-backtest panels
│   │   ├── daily.parquet            # CRSP typed
│   │   ├── intraday.parquet         # iid_ms typed
│   │   ├── h3_panel.parquet         # one file per horizon
│   │   ├── h4_panel.parquet
│   │   ├── h5_panel.parquet
│   │   ├── h6_panel.parquet
│   │   ├── h2_panel.parquet
│   │   └── taq_summaries/           # rsync'd back from Engaging
│   │       ├── h1_panel.parquet
│   │       ├── bar_counts.csv
│   │       └── vwap_sanity.csv
│   └── processed/                   # backtest outputs (written fresh on each run)
├── src/
│   ├── data/
│   │   ├── load_crsp.py
│   │   ├── load_iid.py
│   │   └── validate.py
│   ├── signals/
│   │   ├── h1_taq.py
│   │   ├── h2_iid.py
│   │   ├── h3_daily.py
│   │   ├── h4_weekly.py
│   │   ├── h5_monthly.py
│   │   └── h6_semiannual.py
│   ├── backtest/
│   │   ├── portfolio.py             # terciles_longshort
│   │   ├── engine.py                # run_horizon
│   │   ├── costs.py                 # cost model
│   │   └── metrics.py               # summarize, Bonferroni
│   ├── robustness/
│   │   ├── variance_ratio.py
│   │   ├── ml_benchmark.py
│   │   ├── regime_split.py
│   │   ├── cost_sensitivity.py
│   │   ├── survivorship.py
│   │   └── look_ahead_audit.py
│   ├── report/
│   │   ├── headline_table.py
│   │   ├── horizon_plot.py          # Figure 3 in plan
│   │   ├── vr_plot.py
│   │   └── equity_curves.py
│   ├── taq/                         # Engaging-side code
│   │   ├── aggregate_bars.py
│   │   ├── validate_bars.py
│   │   └── cluster/
│   │       └── aggregate.slurm
│   └── cli/
│       └── run_all.py               # entry point; runs everything
├── llm_logs/                        # one file per non-trivial LLM interaction
└── Makefile                         # `make all` reproducibility target
```

The rule: if a file isn't in this tree, it doesn't exist yet and creating it is a task. If it's in `data/raw/` or `data/reference/`, do not modify it.

---

## 3. Data sources

### 3.1 CRSP Daily (serves H3, H4, H5, H6)

Pulled as `data/raw/dow_daily.csv.gz`. Contains the standard CRSP DSF fields for all 40 ever-members over 2016-01-04 → 2025-09-30 (calendar alignment note: this is three months short of the iid_ms end date; see §3.6).

Fields we use:

| Field | Use | Quirks |
|---|---|---|
| `PERMNO` | Stable ID across ticker changes | Use instead of ticker for identity |
| `Ticker` | For merging with membership matrix | Changes across DD→DWDP→DOW chain |
| `DlyCalDt` | Trading date | ISO date |
| `DlyOpen`, `DlyClose`, `DlyHigh`, `DlyLow` | Prices | Raw, not adjusted |
| `DlyBid`, `DlyAsk` | Daily NBBO endpoints | Used only if iid_ms spread is unavailable |
| `DlyRet` | Daily total return (dividends reinvested) | **Use this for returns, not DlyRetx** |
| `DlyRetx` | Price-only return | Only for dividend-handling sanity checks |
| `DlyVol` | Share volume | |
| `DlyPrcVol` | Dollar volume | |
| `sprtrn` | S&P 500 total return | For factor regression if included |

CRSP is canonical for H3–H6. Long-horizon returns are constructed by compounding `(1 + DlyRet)` within the horizon window.

### 3.2 WRDS Intraday Indicators iid_ms (serves H2)

Pulled as `data/raw/dow_intraday.csv.gz`. One row per (ticker, date). 2016-01-04 → 2025-12-31.

Fields we use for H2:

| Field | Use |
|---|---|
| `OPrc`, `CPrc` | Session open, close prices |
| `mid_after_open` | Midprice in the ~5-min window after the open (used as first-30 proxy) |
| `mid_before_close` | Midprice in the ~5-min window before the close |
| `mid_1pm` | Midprice around 13:00 ET |

Schema note: `mid_after_open` is **not** a clean 10:00 ET midquote — in the WRDS IID spec it's the volume-weighted mid in the first 5 minutes of regular trading. For H2 this is a measurement compromise: we use it as a proxy for the "first-half-hour" return and note the discrepancy in methodology. If it turns out to materially skew the Gao β vs. the proper TAQ-based 30-min version, that's a finding.

Plus these microstructure columns for robustness:

| Field | Use |
|---|---|
| `QuotedSpread_Percent_tw` | Per-day time-weighted quoted spread; our horizon-appropriate cost floor |
| `PercentPriceImpact_LR_Ave` | Lee-Ready price impact, robustness conditioning |
| `bs_ratio_vol` | Buy-sell volume ratio (order imbalance) |
| `ivol_t`, `ivol_q` | Intraday realized volatility (trade- and quote-based) |
| `var_ratio1` … `var_ratio5` | Pre-computed variance ratios over five horizons |

### 3.3 TAQ Millisecond (serves H1, stretch)

Raw TAQ files (`taq.ctm_YYYYMMDD`, consolidated trades, no quotes) are being pulled onto MIT Engaging cluster. Ten-year pull is ~10 TB raw; never transferred off the cluster.

Engaging-side processing produces 30-min OHLCV bars per ticker-day: 40 ever-members × ~2,500 days × 13 bars = ~1.3M rows on disk as partitioned Parquet (~100 MB). Only the bar panel (`h1_panel.parquet`), per-ticker coefficient summaries, and sanity-check outputs are rsync'd back. See §6.1 for aggregation specification and Appendix C for the agent interaction protocol.

### 3.4 Reference data (complete)

Documented in [`REFERENCE_DATA.md`](REFERENCE_DATA.md). Summary:

- `dj30_membership_long.csv`: 75,420 rows (date, ticker) point-in-time member-days
- `dj30_membership_wide.csv`: 2,514 × 40 matrix
- `dj30_events.csv`: 10-event log
- `dj30_tenure.csv`: per-ticker first/last/count
- `nyse_early_closes.csv`: 21 short-session days
- `F-F_Research_Data_5_Factors_2x3_daily.csv`: FF5 + RF (no MOM)

### 3.5 Auxiliary data to pull

These are small, free, and must exist before §8 robustness runs:

| File | Source | Used in |
|---|---|---|
| `vix_daily.csv` | CBOE public CSV | §8.3 regime split |
| `earnings_dates.csv` | IBES on WRDS (preferred) or scrape | §8.7 earnings blackout |
| `F-F_Momentum_Factor_daily.csv` | Ken French's library | Optional §8 factor regression |

### 3.6 Calendar alignment fix (blocker)

CRSP extract ends 2025-09-30; iid_ms extends to 2025-12-31. Pick one end-date and enforce it everywhere.

**Decision:** re-pull CRSP through 2025-12-31 (preferred, gets a full 10-year window and the 2025 year-end regime) OR trim iid_ms and TAQ to 2025-09-30. The re-pull is cheap; do that. If operationally difficult, trim both sides to 2025-09-30 and add one sentence to the ICM limitations.

---

## 4. Universe construction (complete)

Point-in-time DJ30 membership is built from S&P DJI announcement dates and an explicit event log. Covered fully in [`REFERENCE_DATA.md`](REFERENCE_DATA.md) §2.1–2.4; this section exists only to spell out the single integration step downstream horizons must do.

**The universe filter.** Every horizon's panel must be filtered to point-in-time members at signal time:

```python
import pandas as pd

membership = pd.read_csv("data/reference/dj30_membership_long.csv", parse_dates=["date"])

# For any panel with (date, ticker) columns:
panel_pit = panel.merge(membership, on=["date", "ticker"], how="inner")
assert (panel_pit.groupby("date")["ticker"].nunique() == 30).all()
```

The assertion is non-negotiable. Every horizon's panel-construction script must end with it.

**PERMNO continuity.** For the DD→DWDP→DOW chain and UTX→RTX transition, CRSP's PERMNO is stable across the name change, but the ticker is not. When an analysis needs PERMNO-level identity (e.g., per-name variance ratio in §8.1), use the CRSP `stocknames` join rather than splicing tickers manually.

---

## 5. Unified methodology

This section specifies the methodology once. It is applied identically at every horizon; §6 only adds horizon-specific adjustments.

### 5.1 Signal construction

For each stock $i \in U_t$ (the DJ30 members at time $t$) and each horizon $h$:

$$
s_{i,t}^{(h)} = \frac{P_{i,t}}{P_{i,t-h}} - 1
$$

using **total returns** (dividend-reinvested, i.e., compounding CRSP `DlyRet`) for H3–H6 and **price-only** returns for H1–H2 (intraday dividends are negligible). Plan §4.2 eq. (1).

Reference: The sign of $s$ interacting with next-period return is exactly $\rho_1(h)$ — the first-order autocorrelation at horizon $h$. Negative $\rho_1 \Rightarrow$ reversal, positive $\rho_1 \Rightarrow$ momentum. See [Lo & MacKinlay (1988)](#14-methods-references) for the interpretation.

### 5.2 Portfolio construction

At the end of each horizon period $t$, sort members by $s_{i,t}^{(h)}$. Define ranks $\text{rk}_{i,t} \in \{1, \dots, 30\}$ with method `first`. Tercile weights for the MOM portfolio:

$$
w_{i,t+h}^{\text{MOM}} = \frac{1}{10}\big[\mathbb{1}(\text{rk}_{i,t} > 20) - \mathbb{1}(\text{rk}_{i,t} \le 10)\big]
$$

and $w^{\text{REV}} = -w^{\text{MOM}}$. Plan §4.3 eq. (2).

Properties:

- Equal-weighted within each leg (10 names each)
- Dollar-neutral across legs ($\sum_i w_i = 0$)
- Gross leverage = 1 ($\sum_i |w_i| = 1$)
- MOM and REV are exact mirrors: one dataframe, two sign conventions

### 5.3 Forward returns and P&L

Forward return at horizon $h$:

$$
r_{i,t+h}^{\text{fwd}} = \prod_{k=1}^{h}(1 + r_{i,t+k}) - 1
$$

for daily-compounded horizons. For intraday horizons the forward is the single-period price change.

Portfolio P&L:

$$
\Pi_{t+h}^{\text{gross}} = \sum_i w_{i,t+h} \cdot r_{i,t+h}^{\text{fwd}}
$$

### 5.4 Transaction costs

Turnover at rebalance:

$$
\tau_{t+h} = \sum_i |w_{i,t+h} - w_{i,t}|
$$

Net return:

$$
\Pi_{t+h}^{\text{net}} = \Pi_{t+h}^{\text{gross}} - c_h \cdot \tau_{t+h}
$$

where $c_h$ is the per-side cost in bps (divide by $10^4$ when applying). Plan §4.5 eq. (3), Table 2:

| Horizon | $c_h$ (bps) |
|---|---:|
| H1 | 3.0 |
| H2 | 1.5 |
| H3 | 1.5 |
| H4 | 1.5 |
| H5 | 1.5 |
| H6 | 1.5 |

H1 pays more because intraday execution crosses spreads at higher participation. H2–H6 assume one rebalance per day or less, executed at VWAP/TWAP so trading is at or near the mid.

### 5.5 Performance metrics

For every strategy × horizon, report:

1. **Annualized return**: $\bar{r} \cdot a_h$ where $a_h$ is the annualization factor (see §6 per horizon)
2. **Annualized volatility**: $\hat{\sigma} \cdot \sqrt{a_h}$
3. **Annualized Sharpe ratio**: $\text{SR} = \bar{r} / \hat{\sigma} \cdot \sqrt{a_h}$
4. **Max drawdown**: $\text{MDD} = \max_{t} \big( \max_{s \le t} C_s - C_t \big) / \max_{s \le t} C_s$ where $C_t$ is cumulative wealth
5. **t-statistic of mean net return vs. zero**: $t = \bar{r} / \hat{\sigma} \cdot \sqrt{N}$
6. **Turnover** per rebalance and annualized

The SR and t-stat are the two metrics used in the headline comparison. SR is scale-free across horizons; t has the same null $\mathcal{H}_0: \mu = 0$ regardless of horizon.

### 5.6 Bonferroni joint significance

Twelve tests are run (6 horizons × 2 directions). Controlling family-wise error rate at 5%:

$$
\alpha_{\text{per test}} = \frac{0.05}{12} = 0.00417
$$

Two-sided critical value:

$$
t^* = \Phi^{-1}\!\left(1 - \frac{0.00417}{2}\right) \approx 2.87
$$

A strategy's t-stat must exceed $\pm 2.87$ to be called "significant." Plan §4.7.

---

## 6. Horizon-by-horizon specification

Each subsection has the same structure: Task block (concrete implementation), Reference block (mechanism + citation), Verification block (checks).

### 6.1 H1 — TAQ 30-minute bars (5–30 min)

#### Task

**Inputs:** TAQ consolidated-trades files (`ctm_YYYYMMDD`) on Engaging, 2016-01-04 → 2025-12-31. DJ30 point-in-time membership matrix (copied to cluster). NYSE early-close day list.

**Step 1 — Aggregation (Engaging-side).** Write `src/taq/aggregate_bars.py`. Per ticker per day:

1. Filter raw trades: `TR_CORR = 0`; `TIME_M BETWEEN '09:30:00' AND '16:00:00'` (or '13:00:00' on early-close days); `PRICE > 0`; `SIZE > 0`; `TR_SCOND` whitelist (exclude opening `O`, closing `6`, late `L/Z/T`, derivative-priced `W`, odd-lot `I`)
2. Assign each trade to bar index $k \in \{1, \dots, 13\}$ by $k = \lfloor (\text{TIME\_M} - 09\!:\!30\!:\!00) / 30\text{ min} \rfloor + 1$
3. Drop bars $k=1$ and $k=13$ (skip first and last 30 min of each session) — Plan §6.1 "skip the first and last 15 minutes of each session" implemented conservatively as dropping the full opening and closing bars. This leaves bars 2–12, i.e., 11 bars per regular session (5 on early-close days)
4. Compute per bar: `open` (first trade), `high`, `low`, `close` (last trade), `vwap`, `volume_shares`, `dollar_volume`, `n_trades`
5. Write one Parquet per ticker-year: `bars/year=YYYY/ticker=XXX.parquet`

**Step 2 — Signal panel construction (Engaging-side).** Write `src/taq/build_h1_panel.py`:

1. Load all bar Parquets
2. Compute bar return: $r_{i,t,k} = \ln(\text{close}_{i,t,k} / \text{close}_{i,t,k-1})$ (log-return for intraday)
3. Signal at bar $k$: previous-bar return $s_{i,t,k} = r_{i,t,k-1}$
4. Forward return: $r^{\text{fwd}}_{i,t,k} = r_{i,t,k+1}$
5. Drop rows where signal or forward is NaN (first and last bars of each session)
6. Point-in-time filter against membership matrix using the trading date
7. Write `h1_panel.parquet` with columns `[datetime, ticker, signal, ret_fwd]`

**Step 3 — Rsync summary panel back.** The full panel is ~1.3M rows (~50 MB); small enough to bring local. Place at `data/interim/taq_summaries/h1_panel.parquet`.

**Step 4 — Run backtest.** Apply `run_horizon(h1_panel, h='30min', cost_bps=3.0, target='ret_fwd')`. Annualization factor $a_{H1} = 252 \times 11 = 2,772$ periods per year.

#### Reference

[Roll (1984)](#14-methods-references) on microstructure reversal: bid-ask bounce generates negative first-order autocorrelation in trade prices at very short horizons. [Gao, Han, Li & Zhou (2018)](#14-methods-references) document *positive* autocorrelation at the 30-min horizon for S&P futures, driven by institutional rebalancing.

**Mechanism.** At 5–30 minute horizons, returns are a mixture of bid-ask bounce (reversal) and information-driven continuation (momentum). On liquid DJ30 names, these effects roughly cancel — Plan §6.1 predicts H1 is the hardest horizon to profit at. A null result is itself a finding; document it.

#### Verification

- [ ] On regular sessions: exactly 13 raw bars aggregated, 11 after dropping first and last
- [ ] On the 21 early-close days: exactly 7 raw bars, 5 after dropping first and last
- [ ] Daily-summed dollar volume agrees with CRSP `DlyPrcVol` within 5% on 5 random sample days
- [ ] Bar returns are near-zero-mean, non-trivial variance ($\sigma \approx 0.002$–$0.005$)
- [ ] Pooled first-order autocorrelation $|\rho_1| < 0.05$

### 6.2 H2 — iid_ms first-half-hour → rest-of-day

#### Task

**Inputs:** `data/raw/dow_intraday.csv.gz`, point-in-time membership, early-close day list.

**Step 1 — Load and type.** Write `src/data/load_iid.py`:

1. Parse CSV, type `DATE` as datetime, tickers as string
2. Assert `(DATE, SYM_ROOT)` is unique; 110,754 rows expected
3. Write `data/interim/intraday.parquet`

**Step 2 — Signal construction.** Write `src/signals/h2_iid.py`:

1. Signal: $s_{i,t}^{(H2)} = \text{mid\_after\_open}_{i,t} / \text{OPrc}_{i,t} - 1$ — the "first-30-minutes" proxy
2. Forward return: $r_{i,t}^{\text{fwd}} = \text{CPrc}_{i,t} / \text{mid\_after\_open}_{i,t} - 1$ — the "rest-of-day" return
3. On early-close days, the "rest-of-day" is compressed to 12:30 → 13:00; either keep (noting shorter window) or drop. **Decision: drop** — 21 days × 1 observation = 21 rows out of ~75,000, negligible, and eliminates the compressed-session ambiguity
4. Point-in-time filter
5. Write `h2_panel.parquet` with columns `[date, ticker, signal, ret_fwd]`

**Step 3 — Run backtest.** `run_horizon(h2_panel, h='1day_intraday', cost_bps=1.5, target='ret_fwd')`. Annualization factor $a_{H2} = 252$.

**Step 4 — Replicate the Gao regression.** As a robustness anchor, fit per-ticker OLS:

$$
r_{i,t}^{\text{rest}} = \alpha_i + \beta_i \cdot r_{i,t}^{\text{first-30}} + \varepsilon_{i,t}
$$

Report: per-ticker $(\beta_i, t_i)$, cross-sectional mean $\beta$, pooled t-stat on mean $\beta$, fraction of tickers with $|t_i| > 2$. This is the H2 row's economic anchor in the ICM.

#### Reference

[Gao, Han, Li & Zhou (2018, *Journal of Financial Economics*)](#14-methods-references). They find significant positive $\beta$ on S&P 500 futures (first-30-min return predicts rest-of-day return, indicating intraday momentum persistence). Their interpretation: first-30 absorbs overnight information flow; the rest of the day rides institutional rebalancing flows in the same direction.

**Caveat for our setup.** Using `mid_after_open` (a ~5-min VWAP mid) as the first-30 proxy introduces measurement error. The proper test is H1 (or H2 with TAQ-derived 9:30–10:00 return), which is why Step 3 gets TAQ where possible.

#### Verification

- [ ] No NaN in `signal` or `ret_fwd` on any regular-session member-day post-filter
- [ ] Pooled mean $\beta$ in the Gao regression is reported in the ICM with sign and magnitude
- [ ] Compare pooled $\beta$ with the narrow-window version already run in prior EDA (mean $\beta = -0.029$) — the sign might differ, that's a finding

### 6.3 H3 — CRSP 1-day close-to-close

#### Task

**Inputs:** `data/raw/dow_daily.csv.gz`, point-in-time membership, FF 5-factor file.

**Step 1 — Load and type CRSP.** Write `src/data/load_crsp.py`:

1. Parse with `DlyCalDt` as datetime, `PERMNO` as int
2. Apply `abs(DlyClose)` and similar for negative-midquote convention
3. Verify 40 ever-members appear
4. Write `data/interim/daily.parquet`

**Step 2 — Signal construction.** Write `src/signals/h3_daily.py`:

1. Sort by `(ticker, date)`, groupby `ticker`:
   - Signal: $s_{i,t}^{(H3)} = r_{i,t}$ (today's total return)
   - Forward: $r_{i,t+1}^{\text{fwd}} = r_{i,t+1}$ (tomorrow's total return)
2. Point-in-time filter against membership *using the signal date* (the rebalance uses information known at close of day $t$)
3. Write `h3_panel.parquet`

**Step 3 — Run backtest.** `run_horizon(h3_panel, h='1day', cost_bps=1.5, target='ret_fwd')`. Annualization factor $a_{H3} = 252$.

#### Reference

[Lehmann (1990, *Quarterly Journal of Economics*)](#14-methods-references). One-day reversal is compensation for liquidity provision: a name that moves sharply today was absorbed by liquidity suppliers who are paid back by the next-day bounce.

**Caveat for DJ30.** Lehmann's universe is the full CRSP cross-section. Large caps have weaker reversal because they are already well-supplied with liquidity. Expect modest t-statistics (our prior EDA confirmed daily-level pooled $\rho_1 < 0$ but small in magnitude).

#### Verification

- [ ] Panel has exactly 30 names on every trading day
- [ ] REV strategy gross Sharpe is positive (non-trivial reversal signal)
- [ ] Turnover is very high (~2.0 per day — every rebalance flips most positions)

### 6.4 H4 — CRSP 5-day weekly

#### Task

**Inputs:** CRSP daily panel (from §6.3 loader), membership.

**Step 1 — Signal construction.** Write `src/signals/h4_weekly.py`:

1. For each ticker, compute cumulative 5-day return: $s_{i,t}^{(H4)} = \prod_{k=t-4}^{t}(1+r_{i,k}) - 1$
2. Forward: $r_{i,t+5}^{\text{fwd}} = \prod_{k=t+1}^{t+5}(1+r_{i,k}) - 1$
3. Rebalance on a weekly (e.g., every Friday close) non-overlapping schedule: keep rows where `date.dayofweek == 4` (Friday) or the last trading day of that week if Friday is a holiday
4. Write `h4_panel.parquet`

**Step 2 — Run backtest.** `run_horizon(h4_panel, h='1week', cost_bps=1.5, target='ret_fwd')`. Annualization factor $a_{H4} = 52$.

#### Reference

[Lo & MacKinlay (1990, *Review of Financial Studies*)](#14-methods-references). Decompose weekly contrarian profits into own-autocovariance, cross-autocovariance (lead-lag), and common-factor terms. Lead-lag dominates in broad CRSP panels.

**Caveat for DJ30.** Without small-cap components, the lead-lag channel is weaker (small caps lag large caps; nothing lags on DJ30). Expect H4 REV to be smaller in magnitude than Lo-MacKinlay's cross-sectional numbers.

#### Verification

- [ ] Panel has exactly 30 names at every Friday close
- [ ] ~500 rebalance dates (10 years × 52 weeks)
- [ ] Turnover around 1.0–1.5 per rebalance

### 6.5 H5 — CRSP 21-day monthly

#### Task

**Inputs:** CRSP daily panel, membership.

**Step 1 — Signal construction.** Write `src/signals/h5_monthly.py`:

1. Cumulative 21-day return: $s_{i,t}^{(H5)} = \prod_{k=t-20}^{t}(1+r_{i,k}) - 1$
2. Forward: $r_{i,t+21}^{\text{fwd}} = \prod_{k=t+1}^{t+21}(1+r_{i,k}) - 1$
3. Rebalance on month-end trading days: keep last trading day of each calendar month
4. Write `h5_panel.parquet`

**Step 2 — Run backtest.** `run_horizon(h5_panel, h='1month', cost_bps=1.5, target='ret_fwd')`. Annualization factor $a_{H5} = 12$.

#### Reference

[Jegadeesh (1990, *Journal of Finance*)](#14-methods-references). Highly significant one-month reversal on CRSP 1934–1987 ($t \approx 11$).

**Caveat for DJ30.** Jegadeesh's sample is ~30 years and ~3,000 stocks; his t-stat is not our target. Plan §6.5: "on DJ30 over 2016–2026 we expect $t \in [1.5, 3]$ at best."

#### Verification

- [ ] Exactly 120 rebalance dates (10 years × 12 months)
- [ ] 30 names per rebalance date
- [ ] H5 REV gross Sharpe $> 0$ at reasonable magnitude

### 6.6 H6 — CRSP 126-day (6-month)

#### Task

**Inputs:** CRSP daily panel, membership.

**Step 1 — Signal construction.** Write `src/signals/h6_semiannual.py`:

1. Jegadeesh-Titman skip: compute signal as 6-month return **skipping the most recent month** to avoid H5 contamination:

$$
s_{i,t}^{(H6)} = \prod_{k=t-125}^{t-21}(1+r_{i,k}) - 1
$$

2. Forward 6-month return: $r_{i,t+126}^{\text{fwd}} = \prod_{k=t+1}^{t+126}(1+r_{i,k}) - 1$
3. Rebalance **monthly with overlapping holdings**: keep last trading day of each month. This gives 120 observations (not 20 non-overlapping) for statistical power, at the cost of overlap in $r^{\text{fwd}}$
4. Write `h6_panel.parquet`

**Step 2 — Run backtest with Newey-West.** Because the forward returns at successive monthly rebalances overlap by 5 months, residuals are autocorrelated up to lag 5. Use `run_horizon` to compute P&L, then compute the t-statistic with Newey-West HAC standard errors at lag $q = 6$:

```python
from statsmodels.stats.sandwich_covariance import cov_hac
# After running P&L, on the time series of portfolio returns r_p:
# Fit r_p = mu + eps; take NW SE on the intercept with q=6 lags
```

Annualization factor $a_{H6} = 12$ (monthly rebalance frequency). Report both the naive t (biased upward due to overlap) and the NW-corrected t; the NW version is the one used for Bonferroni.

#### Reference

[Jegadeesh & Titman (1993, *Journal of Finance*)](#14-methods-references). Classical 3–12 month cross-sectional momentum. [Moskowitz & Grinblatt (1999, *Journal of Finance*)](#14-methods-references) show most of momentum is industry-level; on 30-name large-cap DJ30 with all industries represented, the effect is attenuated.

**Caveat.** 10 years gives ~120 monthly rebalance observations. Even with strong effect sizes, power is modest. Report confidence intervals, not just point estimates.

#### Verification

- [ ] Signal uses skip-1m convention (decomposes into past_126d / past_21d, not contaminated by H5)
- [ ] Newey-West q=6 t-stat is reported alongside naive t
- [ ] H6 MOM gross Sharpe $> 0$ (expected momentum direction)

---

## 7. Core engine

The six horizon panels have a uniform schema: `[date (or datetime), ticker, signal, ret_fwd]`. The same backtest engine consumes all six.

### 7.1 Module responsibilities

| Module | Function | Purpose |
|---|---|---|
| `backtest/portfolio.py` | `terciles_longshort(df, signal_col)` | Compute dollar-neutral tercile weights |
| `backtest/engine.py` | `run_horizon(panel, cost_bps, target)` | Run MOM and REV, apply costs, return P&L |
| `backtest/costs.py` | `apply_costs(weights, cost_bps)` | Turnover × cost calculation |
| `backtest/metrics.py` | `summarize(pnl, a_h)`, `bonferroni_threshold(n, alpha)` | SR, t, MDD, Bonferroni |

### 7.2 Data contracts

**Input panel contract** (required for every horizon):

```
Column     | Type          | Notes
-----------|---------------|----------------------------------------
date       | datetime64[ns] | Rebalance date (end of period t)
ticker     | str           | Must be point-in-time member at `date`
signal     | float64       | s_{i,t}^{(h)}, no NaN, finite
ret_fwd    | float64       | r_{i,t+h}^{fwd}, no NaN, finite
```

Optional columns (passed through, used by robustness): `permno`, `sector`, `vix_quintile`.

**Output P&L contract:**

```
Column       | Type          | Notes
-------------|---------------|----------------------------------------
date         | datetime64[ns] | End of forward-return period
mom_gross    | float64       | Gross MOM P&L this period
mom_net      | float64       | Net MOM P&L after costs
rev_gross    | float64       | Gross REV P&L
rev_net      | float64       | Net REV P&L
turnover     | float64       | Turnover this rebalance
```

### 7.3 Canonical call sequence

```python
# Per horizon:
panel = pd.read_parquet(f"data/interim/h{k}_panel.parquet")
p = terciles_longshort(panel, signal_col="signal")
pnl = run_horizon(panel=p, cost_bps=COST[k], target="ret_fwd")
stats = summarize(pnl, periods_per_year=A[k])
stats.to_csv(f"data/processed/h{k}_stats.csv")
```

See Appendix A for full code skeletons.

### 7.4 Reproducibility

Every backtest run writes a `run_meta.json` alongside its output:

```json
{
  "git_sha": "a1b2c3...",
  "start_time_utc": "2026-04-20T10:15:00Z",
  "end_time_utc":   "2026-04-20T10:16:42Z",
  "horizon": "H3",
  "cost_bps": 1.5,
  "n_obs": 2513,
  "panel_hash": "sha256:..."
}
```

The `Makefile` target `make all` runs everything from `data/interim/` to `data/processed/` and writes the `run_meta.json` automatically.

---

## 8. Robustness suite

The headline is Table 3; these are appendix exhibits. Each is a separate script in `src/robustness/`.

### 8.1 Variance ratio across horizons

**Task.** For each of the 40 ever-members with sufficient history, compute the Lo-MacKinlay (1988) variance ratio:

$$
\text{VR}(q) = \frac{\text{Var}(r_{t,q})/q}{\text{Var}(r_{t,1})} = 1 + 2 \sum_{k=1}^{q-1} \left(1 - \frac{k}{q}\right) \rho_k
$$

for $q \in \{2, 5, 21, 126, 252\}$ days using CRSP daily returns. Use the heteroskedasticity-robust M2 statistic from Lo & MacKinlay. Pool across names for power.

**Expected pattern.**
- $q=2$: near 1, slightly above or below
- $q=5$ through $q=21$: below 1 on DJ30 (reversal signature), consistent with prior EDA showing strong daily-monthly reversal
- $q=126, 252$: near 1 or above (momentum territory)

**Deliverable.** A plot (`_info/plots/vr_term_structure.png`): x-axis is $q$ on log scale, y-axis is VR, one grey line per ticker, solid red curve for cross-sectional median, shaded band for interquartile range, horizontal dashed line at 1 (random-walk null). Goes in §8 of the ICM as the continuous-horizon version of Table 3.

**Reference.** [Lo & MacKinlay (1988, *Review of Financial Studies*)](#14-methods-references).

### 8.2 One ML benchmark (single horizon)

**Task.** At the winning **mean-reversion** horizon (as determined by Table 3), re-run the strategy with LightGBM-regressed signals on a modest feature set:

- Past return at several lags ($h$, $2h$, $3h$)
- Trailing volatility ($20d$ and $60d$)
- Amihud illiquidity from iid_ms (`PercentPriceImpact_LR_Ave` — use the iid_ms spread if not at a CRSP-only horizon, else the daily estimate from `(high - low)/close`)

Training: purged walk-forward with 6 folds, 5-day embargo. Features are TS and XS z-scored within each training fold (fit on training, applied to test — never refit on test).

Test whether the ML-enhanced Sharpe exceeds the naive-rank Sharpe by more than 1 standard error, using either:

- Diebold-Mariano test on the time series of P&L differences, or
- Politis-Romano stationary bootstrap (block length $\ell = 20$)

**Decision rule.** If the ML uplift is not significant at 10%, conclude that naive ranking captures the available predictability and no ML uplift is warranted — report this honestly in the ICM §8.

**Reference.** [Politis & Romano (1994)](#14-methods-references); Diebold-Mariano (1995).

### 8.3 Regime split

**Task.** For the two selected strategies (see §10), report net Sharpe within each of four VIX quintiles:

1. Pool the daily (or rebalance-date) VIX series
2. Split into quintiles Q1 (lowest) through Q5 (highest), with Q1 & Q2 = "calm" and Q5 = "crisis"
3. For each strategy × regime combination, report annualized net return, vol, Sharpe, and fraction of positive-PnL periods

This is **reported**, not traded. No in-sample optimization on regime.

**Output.** A 2×4 table in the ICM §8 regime analysis. If Sharpe is dramatically different across regimes (e.g., REV-H3 is negative in Q5), that's a Risk & Implementation caveat in §9 of the ICM, not a trading rule.

**Data.** VIX daily close from CBOE public CSV (§3.5). Match on trading date.

### 8.4 Cost sensitivity

**Task.** For each of the 12 strategies, compute the *break-even cost*: the per-side cost $c_h^*$ at which the annualized net Sharpe equals zero.

$$
c_h^* = \frac{\bar{r}_{\text{gross}}}{\bar{\tau}}
$$

where $\bar{\tau}$ is average per-rebalance turnover.

**Decision thresholds.**
- $c_h^* < 1$ bp: strategy is not tradeable even with extremely tight costs
- $1 \le c_h^* < 5$ bp: strategy is borderline; realistic execution costs eat most of the edge
- $c_h^* \ge 5$ bp: strategy is robust to cost assumptions

Report break-even costs in a column of Table 3 (or as a supplementary table).

### 8.5 Survivorship check

**Task.** Re-run all 12 backtests using only **always-present** DJ30 members (23 names per `dj30_tenure.csv` with full 2,514-day tenure). Compare net Sharpes against the point-in-time baseline.

**Expected direction.** Survivorship bias typically *inflates* momentum gross Sharpe (winners were added to the index because they kept winning). It should attenuate under point-in-time. If the reverse happens, investigate — likely a data-handling bug.

### 8.6 Look-ahead audit

**Task.** For each of the 12 strategies:

1. Take the signal column of the horizon panel
2. Shift it by one additional period forward (i.e., use $s_{t-h-1}$ instead of $s_{t-h}$)
3. Rerun the backtest
4. Compare Sharpe

The Sharpe should drop only modestly (10–30%). A catastrophic drop ($> 70\%$) indicates look-ahead bias somewhere in the signal pipeline.

For H2 specifically, check the iid_ms lag convention: iid_ms is end-of-day — its indicators for day $t$ are only knowable at $t+1$ open. The signal for H2 is **within-day $t$** (first-30 predicts rest-of-day-$t$), which works, but any iid_ms feature used as a cross-sectional conditioning variable must be lagged by one day.

### 8.7 Corporate actions and earnings

**Task.** Two checks for signal integrity across events:

1. **Dividend handling.** Recompute all signals using `DlyRetx` (price-only) instead of `DlyRet` (total return). Material differences in backtest P&L ($> 5$ bp annualized) flag a dividend-handling bug
2. **Earnings blackout.** Using the earnings calendar (§3.5), re-run all 12 backtests excluding positions where any of $[t-1, t+1]$ around the forward-return window contains an earnings announcement. Report the attenuation in net Sharpe in the ICM. If the effect is dominated by earnings days, document as a model-risk caveat

**Reference.** [Nagel (2012)](#14-methods-references) — "Evaporating Liquidity" — for the mechanism by which earnings news contaminates short-horizon reversal strategies.

---

## 9. The headline comparison

The table below is the project. It must appear on roughly page 3 of the ICM (Plan §7.1).

| | Momentum (MOM-h) | | | | Mean-Reversion (REV-h) | | | | |
|---|---|---|---|---|---|---|---|---|---|
| **h** | $N_{\text{obs}}$ | SR net | t-stat | MDD | SR net | t-stat | MDD | **Winner** |
| H1 (30min) | | | | | | | | |
| H2 (IID) | | | | | | | | |
| H3 (1d) | | | | | | | | |
| H4 (5d) | | | | | | | | |
| H5 (21d) | | | | | | | | |
| H6 (126d) | | | | | | | | |

**Winner column** is whichever of MOM-h and REV-h has the higher net Sharpe, provided its t-stat clears $t^* \approx 2.87$ (Bonferroni). If neither passes, note "N.S."

**Accompanying figure.** Plan §7.2: line plot with horizon on x-axis (log scale or ordinal), net Sharpe on y-axis, two lines (MOM and REV) with error bars. The story is the sign-flipping pattern across horizons — which horizons reward contrarian bets and which reward trend-following. Go-to visualization format: matplotlib `plt.errorbar` with standard errors from the bootstrap in §8.4 applied via block-length 20.

---

## 10. Strategy selection for the ICM

**Rule.** Let

$$
h^*_{\text{MOM}} = \arg\max_h \text{SR}^{\text{MOM}}_h \quad \text{subject to} \quad t^{\text{MOM}}_h > t^*
$$

$$
h^*_{\text{REV}} = \arg\max_h \text{SR}^{\text{REV}}_h \quad \text{subject to} \quad t^{\text{REV}}_h > t^*
$$

Put the two resulting strategies in the ICM sections 5 and 6.

**Fallback if only one family passes.** Present both strategies (best REV and best MOM) but explicitly note in §8 that the non-significant one fails the family-wise test. Do not paper over this.

**Fallback if neither passes.** Present the best of each family, note both fail the Bonferroni threshold, and make the ICM §1 recommendation "no trade" — this is a defensible outcome, not a failed project.

---

## 11. ICM structure

One document, 20–25 pages. Order and page budget from Plan §9.1:

| Section | Pages | Content |
|---|---:|---|
| 1. Executive summary | 1 | Two strategies, headline Sharpe + risk, recommendation |
| 2. Research frame | 1 | Horizon-comparison thesis, Figure 1 (expected sign pattern) |
| 3. Methodology | 2 | Universe, signal, portfolio construction, cost model |
| 4. The horizon comparison | 3 | Table 3, Figure 3, per-horizon interpretation |
| 5. Best mean-reversion strategy | 3–4 | Spec, equity curve, drawdown, regime tables, P&L conditions |
| 6. Best momentum strategy | 3–4 | Same format |
| 7. Statistical properties | 2 | Return distribution, autocorrelation, VaR/ES |
| 8. Robustness | 2 | VR curve, ML benchmark, regime split, cost sensitivity |
| 9. Implementation & risk | 1 | Capacity, kill switches |
| 10. Limitations | 1 | Small cross-section, DJ30 large-caps attenuate effects, 10yr sample thin for H6 |
| 11. Appendix | as needed | Code scaffolding, feature list, LLM log index, references |

**Tone requirement.** Sell-side memo style per Plan §9.2. Short sentences, numbers in tables. Replace "the strategy performs well" with "gross SR 0.87, net SR 0.52, MDD 11%."

---

## 12. Week-by-week plan

Current date: **2026-04-17**. Assuming project submission roughly six weeks out.

| Week | Dates | Deliverable | Verification |
|---|---|---|---|
| 1 | 04-17 → 04-23 | Cross-cutting prereqs: VIX pulled, earnings calendar, calendar alignment (CRSP re-pull or trim). CRSP + iid_ms loaded and written to `data/interim/`. | `daily.parquet` and `intraday.parquet` exist; `vix_daily.csv` in `reference/` |
| 2 | 04-24 → 04-30 | H3, H4, H5, H6 signals computed on CRSP; `run_horizon` engine written; four backtests produced. First draft of Table 3 with CRSP rows filled. | `h3_panel.parquet` through `h6_panel.parquet`; `h3_stats.csv` through `h6_stats.csv` |
| 3 | 05-01 → 05-07 | H2 signal from iid_ms built; backtest run; Gao regression reproduced per-ticker and pooled. Table 3 row for H2 filled. | `h2_panel.parquet`; Gao regression results in `data/processed/gao_regression.csv` |
| 4 | 05-08 → 05-14 | TAQ aggregation finalized on Engaging; H1 panel rsync'd back; backtest run; Table 3 row for H1 filled. Headline figure drafted. | `h1_panel.parquet`; `horizon_plot.png` drafted |
| 5 | 05-15 → 05-21 | Robustness suite: VR curve, ML benchmark at winning REV horizon, regime split on the two selected strategies, cost sensitivity for all 12, survivorship check, look-ahead audit, earnings blackout. | All scripts in `src/robustness/` executed; output CSVs in `data/processed/robustness/` |
| 6 | 05-22 → 05-28 | ICM draft sections 1–8 written. Peer review within team. Revise. | Full ICM draft committed |
| 7 | 05-29 → 06-04 | ICM polish, reproducibility check (`make all` runs clean from git clone), LLM attribution log finalized, submission. | Final PDF + attribution appendix |

If anything slips, the compression order is: drop §8.5 earnings blackout, then §8.2 ML benchmark, then §8.1 VR curve. Never drop: Table 3, cost sensitivity, survivorship, look-ahead.

---

## 13. Pitfalls catalog

From Plan §11, expanded with implementation notes.

### 13.1 Survivorship

**Pitfall.** Using today's DJ30 (as of 2026) to backtest 2016 = NVDA, AMZN, SHW, HON, CRM, AMGN are in the panel from day one despite not being index members.

**Mitigation (done).** Point-in-time membership matrix, §4. Every horizon panel must be filtered before backtesting; the assertion `(count == 30).all()` is non-negotiable.

### 13.2 Look-ahead

**Pitfall.** Using information not knowable at signal time. The most common forms:

- Using iid_ms indicators for day $t$ at signal time $t$ (they're end-of-day summaries; usable at $t+1$ open at earliest)
- Normalizing features using cross-sectional stats that include the future (e.g., z-scoring against the full-sample mean rather than training-fold mean)
- Rebalance-date selection that depends on future prices

**Mitigation.** For iid_ms features, shift by one trading day in the loader. For ML benchmark, fit z-scores on training folds only. For rebalance calendar, use only ex-ante rules (end-of-week = Friday close; end-of-month = last trading day before next calendar month starts).

**Audit.** §8.6 look-ahead test.

### 13.3 Corporate actions

**Pitfall.** The DD → DWDP → DOW sequence (2017-09-01, 2019-04-02) and UTX → RTX (2020-04-06) involve ticker changes that break naive ticker-level time series. For DD specifically, there are three distinct tickers sharing a PERMNO chain.

**Mitigation.** Use CRSP `ret` (total return), not `retx` (price-only) — handles dividends and certain corporate actions cleanly. For the DD chain, join via CRSP `stocknames` on PERMNO if PERMNO-level continuity is needed; otherwise trust that the ticker-level signal panel is correct *within each ticker's tenure*.

### 13.4 Overlapping forecasts at H6

**Pitfall.** 126-day holding periods overlap when rebalanced monthly; naive t-stats overstate significance by as much as $\sqrt{6}$.

**Mitigation.** Newey-West HAC standard errors with $q = 6$ lags. §6.6 Step 2.

**Reference.** [Newey & West (1987)](#14-methods-references).

### 13.5 In-sample scaling at the ML benchmark

**Pitfall.** Z-scoring features on the full sample leaks future statistics into training folds.

**Mitigation.** In §8.2, fit z-score mean and std on training folds only, apply (not refit) to test folds. Use `sklearn`'s `TransformerMixin` pattern inside a `Pipeline` with `cross_val_predict` for walk-forward.

### 13.6 Turnover drift at H1

**Pitfall.** 30-min rebalancing with tercile flips generates extreme turnover — often 1.5–2.0 per rebalance, meaning most positions turn over every half hour.

**Mitigation.** Cost sensitivity (§8.4) is critical at H1. Report break-even cost prominently; if below realistic execution costs (~3 bps) the strategy is a null result.

### 13.7 Earnings days

**Pitfall.** Individual stocks have idiosyncratic jumps on earnings dates; these can drive REV (apparent mean reversion: stock jumps up, then settles) or MOM (announcement drift). Either way, results on earnings days are not stable predictions.

**Mitigation.** §8.7 earnings blackout robustness check. Document whether the selected strategy's Sharpe survives excluding earnings days.

### 13.8 Early-close days

**Pitfall.** On the 21 short sessions (see `nyse_early_closes.csv`), the regular 13-bar 30-min grid reduces to 7 bars. If H1 aggregation silently uses the full-day bar template, bars 8–13 are missing on these days — 21 × 6 = 126 missing bar-rows out of ~130,000.

**Mitigation.** §6.1 Step 1.3 handles this at aggregation. Verify with the bar-count audit (`bar_counts.csv` must show exactly 7 on these 21 dates, 13 otherwise).

---

## 14. Methods references

Each entry: citation, what it's used for in this project, and a pointer to the section that relies on it.

- **[Roll, R. (1984). "A Simple Implicit Measure of the Effective Bid-Ask Spread in an Efficient Market." *Journal of Finance*, 39(4), 1127–1139.]** — Microstructure reversal mechanism underlying H1. §6.1 reference block.

- **[Lo, A. W., & MacKinlay, A. C. (1988). "Stock Market Prices Do Not Follow Random Walks: Evidence from a Simple Specification Test." *Review of Financial Studies*, 1(1), 41–66.]** — Variance ratio test used in §8.1. Also the foundational framing for autocorrelation-driven strategies (§5.1).

- **[DeBondt, W. F., & Thaler, R. (1985). "Does the Stock Market Overreact?" *Journal of Finance*, 40(3), 793–805.]** — Long-horizon (3–5 year) reversal context; not tested in our 10-year window but cited in §1 of the ICM for framing.

- **[Fama, E. F., & French, K. R. (1988). "Permanent and Temporary Components of Stock Prices." *Journal of Political Economy*, 96(2), 246–273.]** — Long-horizon serial correlation decomposition; contextual reference.

- **[Newey, W. K., & West, K. D. (1987). "A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix." *Econometrica*, 55(3), 703–708.]** — HAC standard errors for H6 overlapping forecasts. §6.6 and §13.4.

- **[Lehmann, B. N. (1990). "Fads, Martingales, and Market Efficiency." *Quarterly Journal of Economics*, 105(1), 1–28.]** — H3 daily reversal mechanism. §6.3 reference block.

- **[Lo, A. W., & MacKinlay, A. C. (1990). "When Are Contrarian Profits Due to Stock Market Overreaction?" *Review of Financial Studies*, 3(2), 175–205.]** — H4 weekly decomposition. §6.4 reference block.

- **[Jegadeesh, N. (1990). "Evidence of Predictable Behavior of Security Returns." *Journal of Finance*, 45(3), 881–898.]** — H5 monthly reversal. §6.5 reference block.

- **[Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency." *Journal of Finance*, 48(1), 65–91.]** — H6 momentum and the J/K skip-1 convention. §6.6 reference block.

- **[Politis, D. N., & Romano, J. P. (1994). "The Stationary Bootstrap." *Journal of the American Statistical Association*, 89(428), 1303–1313.]** — Block bootstrap for time-series inference in §8.2 and error bars in §9.

- **[Diebold, F. X., & Mariano, R. S. (1995). "Comparing Predictive Accuracy." *Journal of Business & Economic Statistics*, 13(3), 253–263.]** — ML uplift significance test in §8.2.

- **[Moskowitz, T. J., & Grinblatt, M. (1999). "Do Industries Explain Momentum?" *Journal of Finance*, 54(4), 1249–1290.]** — H6 caveat: most momentum is industry-level, attenuated on DJ30. §6.6.

- **[Lo, A. W. (2004). "The Adaptive Markets Hypothesis." *Journal of Portfolio Management*, 30(5), 15–29.]** — Framing for why autocorrelation signs can flip over time (regime-dependent market efficiency).

- **[Nagel, S. (2012). "Evaporating Liquidity." *Review of Financial Studies*, 25(7), 2005–2039.]** — STR decay story, liquidity provision mechanism; relevant to earnings-blackout robustness (§13.7).

- **[Gao, L., Han, Y., Li, S. Z., & Zhou, G. (2018). "Market Intraday Momentum." *Journal of Financial Economics*, 129(2), 394–414.]** — H2 intraday momentum mechanism. §6.2 reference block.

---

## 15. LLM attribution protocol

**Principle.** Attribution is the easiest 25 points on the rubric. Under-reporting is penalized; over-reporting is not. Log everything non-trivial.

### 15.1 What to log

Log any LLM interaction that:

- Produces code that ends up in the repo
- Produces text that ends up in the ICM
- Resolves a technical decision (e.g., "should H6 use overlapping monthly or non-overlapping semi-annual rebalance?")
- Derives a non-obvious formula or threshold (e.g., Bonferroni $t^* \approx 2.87$)

Do *not* bother logging:

- Simple reformatting or grammar checks on existing prose
- Routine "explain this error message" debugging that doesn't change the code
- Questions that led to dead ends and weren't used

### 15.2 Format

One file per logged interaction under `llm_logs/`. Filename convention: `NNN_slug.md` where `NNN` is a three-digit sequence number and `slug` is a short topic descriptor.

Template (one per file):

```markdown
# LLM Log 012 — Bonferroni threshold for 12 tests

**Model:** Claude Opus 4.7
**Date:** 2026-04-20 10:15 EDT
**Session URL:** (if available)

## Prompt

Derive the closed-form Bonferroni threshold for 12 tests at family-wise alpha = 5%; 
explain the intuition.

## Output

(full output text verbatim, or pointer to saved transcript at llm_logs/012_full.txt)

## Used for

Section 5.6 of Work1.md; confirmed threshold t* ~ 2.87. Applied in Table 3 
significance column.
```

### 15.3 Index in the ICM appendix

The ICM's appendix lists every log entry by number with a one-line purpose:

```
LLM Log 001 — Setup help for pandas_market_calendars XNYS calendar
LLM Log 002 — Derivation of Lo-MacKinlay M2 variance-ratio formula
LLM Log 003 — Debug: H5 panel had 119 rebalances instead of 120
LLM Log 012 — Bonferroni threshold for 12 tests
...
```

### 15.4 Models to attribute

Any LLM that materially contributed to the work, including (but not limited to): Claude (any version), GPT-4, Gemini, Cursor/Copilot autocompletions when non-trivial.

---

## Appendix A. Code skeletons

Expanded from Plan §13. Fill in the gaps as you implement.

### A.1 `backtest/portfolio.py`

```python
import numpy as np
import pandas as pd

def terciles_longshort(df: pd.DataFrame, signal_col: str = "signal") -> pd.DataFrame:
    """Dollar-neutral, equal-weighted tercile long-short weights.
    
    Input: df with columns [date, ticker, signal, ret_fwd]
    Output: same df with added columns [w_mom, w_rev]
    """
    out = df.copy()
    out["rk"] = out.groupby("date")[signal_col].rank(method="first")
    out["n"]  = out.groupby("date")["rk"].transform("size")
    out["q"]  = pd.cut(
        out["rk"] / out["n"],
        bins=[0, 1/3, 2/3, 1],
        labels=["lo", "mi", "hi"],
    )
    # Equal-weight within each tercile leg
    leg_size = out.groupby(["date", "q"])["rk"].transform("size")
    w = np.where(out["q"] == "hi",  1.0,
        np.where(out["q"] == "lo", -1.0, 0.0))
    w = w / leg_size
    out["w_mom"] = w
    out["w_rev"] = -w
    return out
```

### A.2 `backtest/engine.py`

```python
import numpy as np
import pandas as pd
from .portfolio import terciles_longshort

def run_horizon(
    panel: pd.DataFrame,
    cost_bps: float = 1.5,
    target: str = "ret_fwd",
) -> pd.DataFrame:
    """Run MOM and REV on a horizon panel. Returns per-rebalance P&L.
    
    Input panel columns: [date, ticker, signal, ret_fwd]
    Output columns: [date, mom_gross, mom_net, rev_gross, rev_net, turnover]
    """
    p = terciles_longshort(panel, signal_col="signal")

    # Gross P&L per rebalance date
    pnl_mom_gross = (p["w_mom"] * p[target]).groupby(p["date"]).sum()
    pnl_rev_gross = (p["w_rev"] * p[target]).groupby(p["date"]).sum()

    # Turnover: compare weights across adjacent rebalance dates
    # For terciles_longshort we know |w_mom| sums to 1 each date; turnover
    # is bounded above by 2. Proper implementation: lag w_mom per ticker
    # and sum |delta|.
    w = p.pivot(index="date", columns="ticker", values="w_mom").fillna(0)
    turnover = (w - w.shift(1)).abs().sum(axis=1).fillna(w.iloc[0].abs().sum())

    cost = turnover * (cost_bps / 1e4)
    return pd.DataFrame({
        "mom_gross": pnl_mom_gross,
        "mom_net":   pnl_mom_gross - cost,
        "rev_gross": pnl_rev_gross,
        "rev_net":   pnl_rev_gross - cost,
        "turnover":  turnover,
    })
```

### A.3 `backtest/metrics.py`

```python
import numpy as np
import pandas as pd
from scipy.stats import norm

def summarize(pnl: pd.DataFrame, periods_per_year: int) -> pd.DataFrame:
    """Compute summary stats for each column of pnl (excluding turnover)."""
    def stats(x: pd.Series) -> pd.Series:
        x = x.dropna()
        mu, sd = x.mean(), x.std()
        n = len(x)
        sr = np.sqrt(periods_per_year) * mu / sd if sd > 0 else np.nan
        t  = np.sqrt(n) * mu / sd if sd > 0 else np.nan
        mdd = max_drawdown((1 + x).cumprod())
        return pd.Series({
            "mean": mu,
            "std": sd,
            "sharpe": sr,
            "t_stat": t,
            "n_obs": n,
            "max_dd": mdd,
        })
    # Summarize only P&L columns, not turnover
    cols = [c for c in pnl.columns if c not in ("turnover",)]
    return pnl[cols].apply(stats).T

def max_drawdown(cum_wealth: pd.Series) -> float:
    running_max = cum_wealth.cummax()
    drawdown = (cum_wealth - running_max) / running_max
    return drawdown.min()

def bonferroni_threshold(n_tests: int = 12, alpha: float = 0.05) -> float:
    """Two-sided z-critical for family-wise error rate `alpha` across `n_tests`."""
    return norm.ppf(1 - (alpha / n_tests) / 2)
```

### A.4 `signals/h3_daily.py` (example; other horizons follow the same pattern)

```python
import pandas as pd

def build_h3_panel(daily: pd.DataFrame, membership: pd.DataFrame) -> pd.DataFrame:
    """H3 = 1-day close-to-close reversal. Signal = today's return; forward = tomorrow's."""
    d = daily.sort_values(["ticker", "date"]).copy()
    d["signal"]  = d.groupby("ticker")["DlyRet"].shift(0)
    d["ret_fwd"] = d.groupby("ticker")["DlyRet"].shift(-1)
    d = d.dropna(subset=["signal", "ret_fwd"])
    # Point-in-time filter
    d = d.merge(membership, on=["date", "ticker"], how="inner")
    assert (d.groupby("date")["ticker"].nunique() == 30).all(), "PiT membership broken"
    return d[["date", "ticker", "signal", "ret_fwd"]]
```

### A.5 `cli/run_all.py`

```python
"""Reproducibility entry point. `python -m src.cli.run_all` runs everything."""
from pathlib import Path
import pandas as pd

from src.signals import h1_taq, h2_iid, h3_daily, h4_weekly, h5_monthly, h6_semiannual
from src.backtest.engine import run_horizon
from src.backtest.metrics import summarize

HORIZON_CONFIG = {
    "H1": {"cost_bps": 3.0, "periods_per_year": 2772},
    "H2": {"cost_bps": 1.5, "periods_per_year": 252},
    "H3": {"cost_bps": 1.5, "periods_per_year": 252},
    "H4": {"cost_bps": 1.5, "periods_per_year": 52},
    "H5": {"cost_bps": 1.5, "periods_per_year": 12},
    "H6": {"cost_bps": 1.5, "periods_per_year": 12},
}

def main():
    out = {}
    for h in ["H1", "H2", "H3", "H4", "H5", "H6"]:
        panel = pd.read_parquet(f"data/interim/{h.lower()}_panel.parquet")
        cfg = HORIZON_CONFIG[h]
        pnl = run_horizon(panel, cost_bps=cfg["cost_bps"])
        stats = summarize(pnl, periods_per_year=cfg["periods_per_year"])
        pnl.to_parquet(f"data/processed/{h.lower()}_pnl.parquet")
        stats.to_csv(f"data/processed/{h.lower()}_stats.csv")
        out[h] = stats
    # Assemble Table 3
    assemble_headline_table(out).to_csv("data/processed/headline_table.csv")

if __name__ == "__main__":
    main()
```

---

## Appendix B. Expected output files

Enumerated so the agent knows when the project is complete:

### B.1 Interim panels

```
data/interim/daily.parquet
data/interim/intraday.parquet
data/interim/h1_panel.parquet          # rsync'd from Engaging
data/interim/h2_panel.parquet
data/interim/h3_panel.parquet
data/interim/h4_panel.parquet
data/interim/h5_panel.parquet
data/interim/h6_panel.parquet
data/interim/taq_summaries/bar_counts.csv
data/interim/taq_summaries/vwap_sanity.csv
```

### B.2 Backtest outputs (one set per horizon)

```
data/processed/h{1..6}_pnl.parquet      # per-rebalance P&L
data/processed/h{1..6}_stats.csv        # SR, t, MDD, turnover
data/processed/h{1..6}_equity.csv       # cumulative wealth
data/processed/h{1..6}_run_meta.json    # reproducibility metadata
```

### B.3 Robustness outputs

```
data/processed/robustness/vr_term_structure.csv
data/processed/robustness/vr_term_structure.png
data/processed/robustness/ml_benchmark_stats.csv
data/processed/robustness/regime_split_table.csv
data/processed/robustness/cost_sensitivity.csv
data/processed/robustness/survivorship_check.csv
data/processed/robustness/look_ahead_audit.csv
data/processed/robustness/earnings_blackout.csv
data/processed/gao_regression.csv
```

### B.4 Headline deliverables

```
data/processed/headline_table.csv       # Table 3 rendered
data/processed/horizon_plot.png         # Figure 3
data/processed/Figure_1_expected.png    # expected-sign prior (plan §3.2)
```

### B.5 ICM

```
icm/ICM.tex   (or .md → rendered .pdf via pandoc)
icm/figures/  (copied from data/processed/*.png)
icm/tables/   (LaTeX-rendered from data/processed/*.csv)
icm/ICM.pdf   (final)
```

---

## Appendix C. Agent interaction protocol for cluster work

H1 (TAQ aggregation) runs on MIT Engaging. The agent (human or LLM) cannot execute code on Engaging directly.

### C.1 Workflow

1. Code for TAQ aggregation lives locally in `src/taq/` under git
2. User `rsync`s to Engaging: `rsync -av src/taq/ engaging:~/project1/src/taq/`
3. User submits the SLURM job (or runs interactively) on Engaging
4. Outputs land in `~/project1/out/` on Engaging: `h1_panel.parquet`, `bar_counts.csv`, `vwap_sanity.csv`, `run_meta.json`
5. User `rsync`s outputs back: `rsync -av engaging:~/project1/out/ data/interim/taq_summaries/`
6. User shares output files with the agent (paste contents or upload)
7. Agent interprets against §6.1 verification checklist and Plan §8.5 expectations

### C.2 What to share back with the agent

Small summary files only. Specifically:

- `bar_counts.csv` (≤2,514 rows): per-date bar counts
- `vwap_sanity.csv` (~5 rows): sample-day VWAP comparison to CRSP
- `run_meta.json`: SLURM job ID, git SHA, timing
- Optionally: the summary statistics of `h1_panel.parquet` (`.describe()`) rather than the full panel

Do not share: raw TAQ, 30-min bar Parquets, any file >10 MB. They don't add interpretive value over the summaries.

### C.3 What the agent should do with the summaries

Check against:

- Bar count expected = 11 on regular sessions, 5 on the 21 early-close days, 0 on holidays
- VWAP agreement within 5% on 5 random ticker-days
- `h1_panel.parquet` row count ≈ 40 tickers × ~2,500 days × 11 bars × (tenure fraction) ≈ 900,000 (accounting for partial tenure)
- H1 pooled first-order autocorrelation $|\rho_1| < 0.05$ (near-zero consistent with Roll/Gao tug-of-war)

If any check fails, flag to the user and propose a diagnostic.

---

*End of Work1. Next touch: create `src/data/load_crsp.py` and `src/data/load_iid.py` to complete Week 1. Horizon implementation (§6) starts at the beginning of Week 2.*
