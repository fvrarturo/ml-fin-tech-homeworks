# Reference Data — README

*Files added to the project during the Week-1 data scaffolding pass. Sits alongside [Work1.md](Work1.md).*

The files documented here belong in `data/reference/`. They are small, version-controlled, and human-inspectable. They do **not** include the bulk CRSP / iid_ms / TAQ pulls — those live in `data/raw/` and `data/interim/`.

---

## Note on TAQ Intraday Files

**NYSE TAQ (Trade and Quote) files** for this project are available on the MIT Engaging cluster, in directory `favara:~Fin_Tech/HW1/data/`. Files are named `TAQYYYY.csv.gz`, one per year from 2016 to 2025 inclusive. These files contain the full intraday tick-by-tick trade records for NYSE stocks, and are integral for any higher-frequency or microstructure analyses.

**TAQ Variable List:**

| Field | Description |
|-------|-------------|
| `DATE`      | Trade date (YYYYMMDD integer) |
| `TIME_M`    | Trade time in milliseconds from midnight (e.g., 34223015 = 09:30:23.015) |
| `SYM_ROOT`  | Security symbol root (ticker) |
| `SYM_SUFFIX`| Additional security identifier, e.g., class shares or preferred stock (can be blank) |
| `EX`        | Exchange code where the trade occurred (e.g., N, A, Q, etc.) |
| `TR_SCOND`  | Trade sale condition flags (provides context for trade type, reporting type, and eligibility for certain analyses) |
| `SIZE`      | Number of shares traded in this tick |
| `PRICE`     | Trade price (dollars, usually as float) |
| `TR_CORR`   | Trade correction indicator (flags cancelled/corrected trades; use to filter out reversals or errors) |

For concrete use: each row in these files represents a single reported trade on the NYSE during regular or extended session. The fields allow for precise reconstruction of quote evolution, trade sizes, price formation, and filtering by trade conditions or corrections. `TIME_M` permits sub-second analysis and alignment with other (e.g., quote or indicator) feeds.

**Note:** These TAQ files are much larger and are stored outside Git for practical reasons. In typical workflow, read these files directly from the Engaging directory using relevant pandas or dask code for your time window and symbol subset.

---

## 1. Inventory

| File | Rows | Purpose | Source |
|---|---:|---|---|
| `dj30_membership_long.csv` | 75,420 | Point-in-time DJ30 index membership, one row per `(date, ticker)` member-day. **Primary merge key for all backtests.** | Built from S&P DJI press releases |
| `dj30_membership_wide.csv` | 2,514 | Same data, wide matrix: `date` index × 40 ever-member tickers, 0/1 flags. Handier for cross-sectional ops. | Pivoted from long file |
| `dj30_events.csv` | 10 | Canonical event log: effective date, outgoing ticker, incoming ticker, note. Feeds the membership builder. | S&P DJI announcements, cross-checked against Wikipedia and news |
| `dj30_tenure.csv` | 40 | Per-ticker first/last membership day and total days. Useful for CRSP-merge sanity checks. | Derived from long file |
| `nyse_early_closes.csv` | 21 | NYSE short-session days (13:00 ET close) with reason classification. | `pandas_market_calendars` (XNYS) |
| `ff_fivefactors.csv` | 15,771 | Fama-French 5-factor daily returns + RF. Used in the ICM factor regression. | [Ken French's data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) |

Builder scripts live in `src/data/`:

- `build_dj30_membership.py` — regenerates the four DJ30 files from the event log
- `build_early_closes.py` — regenerates the early-close file

Both are idempotent and take <1 second to run.

---

## 2. File-by-file notes

### 2.1 `dj30_membership_long.csv` — point-in-time universe

**Schema.** Two columns: `date` (ISO, YYYY-MM-DD) and `ticker` (string).

**Coverage.** 2016-01-04 through 2025-12-31, 2,514 NYSE trading days, exactly 30 tickers per day.

**Loading.**
```python
import pandas as pd
membership = pd.read_csv("data/reference/dj30_membership_long.csv",
                         parse_dates=["date"])
# Filter a CRSP panel to point-in-time members:
panel_pit = panel.merge(membership, on=["date", "ticker"], how="inner")
```

**Ever-members (40 total).** 23 with full tenure + 17 with partial tenure due to 10 index events. See `dj30_tenure.csv` for first/last dates per ticker.

**Effective-date convention.** An event's effective date is the **first** trading day the *incoming* ticker is in the index. The *outgoing* ticker is a member through the prior trading day inclusive. Matches S&P DJI's "prior to the open of trading on [date]" language in every press release.

**Why this matters.** Without a point-in-time filter, backtesting 2016 using 2025's DJ30 would "see" NVDA and AMZN — classic survivorship bias. The work plan (L1893–1906) lists this as the #1 pitfall.

### 2.2 `dj30_membership_wide.csv` — membership matrix

Same content as the long file, pivoted. Shape: (2514 dates) × (40 tickers). Values are `int8` 0/1 flags. Row sums are exactly 30 on every date.

Useful when you want a boolean mask per date without a merge — e.g., cross-sectional z-scoring restricted to current members.

### 2.3 `dj30_events.csv` — index event log

Schema: `effective_date`, `out`, `in`, `note`. Ten rows covering the 2016–2025 window. This is the canonical source — the long and wide files are derived from it.

Append a row and rerun `build_dj30_membership.py` when S&P DJI announces a new change.

**Known churn timeline:**

| Date | Event |
|---|---|
| 2017-09-01 | DD → DWDP (DuPont + Dow Chemical merger) |
| 2018-06-26 | GE → WBA (GE out after 110+ yrs) |
| 2019-04-02 | DWDP → DOW (DowDuPont spinoff) |
| 2020-04-06 | UTX → RTX (UTC + Raytheon merger) |
| 2020-08-31 | XOM → CRM, PFE → AMGN, RTX → HON (Apple 4:1 split rebalance) |
| 2024-02-26 | WBA → AMZN (Walmart 3:1 split rebalance) |
| 2024-11-08 | INTC → NVDA, DOW → SHW |

**The RTX trap.** RTX is in the index for only 102 trading days (2020-04-06 → 2020-08-28). Any feature engineering that treats membership days as roughly comparable will badly over-weight noise on this ticker. Flag it.

**The DD → DWDP → DOW → SHW chain.** Four distinct tickers, different CUSIPs, but partially overlapping CRSP PERMNO history (DD and DWDP share a PERMNO through the name change; DOW is a fresh PERMNO; SHW was never related). The membership file is keyed on ticker — join through CRSP's `stocknames` table if you need PERMNO continuity.

### 2.4 `dj30_tenure.csv` — per-ticker sanity

Schema: `ticker`, `first_day`, `last_day`, `n_days`. Sorted by first day.

Useful for cross-referencing against your WRDS pull's actual tenure per ticker (work plan flagged 6 truncated tickers in its EDA; this file enumerates all 17 partial-tenure names).

### 2.5 `nyse_early_closes.csv` — short-session days

**Schema.** `date`, `close_time_et`, `reason`, `is_black_friday`, `is_christmas_eve`, `is_july_3`, `is_adhoc`.

**Coverage.** 21 days across 2016–2025, all at 13:00 ET (3 hours shorter than regular 16:00 close).

**Breakdown.** 10 Black Fridays (every year) + 5 Christmas Eves (2018, 2019, 2020, 2024, 2025) + 6 July 3 (2017, 2018, 2019, 2023, 2024, 2025). No ad-hoc disruptions in this window. 2018-12-05 (Bush funeral) and 2025-01-09 (Carter funeral) were *full* closures, not early closes — they live in the holidays list instead.

**Why it matters for H2.** The canonical Gao et al. (2018) regression uses a 13-bar grid (9:30→10:00, ..., 15:30→16:00). On early-close days, bars 8–13 don't exist. If you silently skip the check, your regression is wrong on 21/2514 = 0.83% of the sample with no error message. Three handling options, ordered from lazy to pedantic:

1. **Drop these days** from the H2 regression (easiest; <1% data loss)
2. **Shrink the grid to 7 bars** (9:30→10:00 through 12:30→13:00) and redefine Gao's "last 30 min" = 12:30→13:00 on short sessions
3. **Add an early-close dummy feature** and keep the full grid on regular days — most defensible, also a minor ICM exhibit

**iid_ms audit note.** Verify that on these 21 dates, `mid_before_close` is timestamped in the 12:50–13:00 window (not 15:50–16:00). If WRDS didn't adjust, the AM/PM split features are subtly wrong on short sessions.

### 2.6 `ff_fivefators.csv` — Fama-French factors

**Schema.** `date` (YYYYMMDD integer), `Mkt-RF`, `SMB`, `HML`, `RMW`, `CMA`, `RF`. Values are **percentages**, not decimals.

**Coverage.** 1963-07-01 through 2026-02-27 (15,771 daily rows). More than enough for our 2016–2025 window.

**Loading.**
```python
import pandas as pd
ff = pd.read_csv("data/reference/F-F_Research_Data_5_Factors_2x3_daily.csv",
                 skiprows=3, skipfooter=2, engine="python")
ff.rename(columns={ff.columns[0]: "date"}, inplace=True)
ff["date"] = pd.to_datetime(ff["date"], format="%Y%m%d")
for c in ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]:
    ff[c] = ff[c].astype(float) / 100.0   # percent -> decimal
```

**Factor coverage vs. ICM need.** The work plan Section 25.5 specifies a 5-factor + LIQ regression: MKT, SMB, HML, **MOM**, LIQ. This file gives us Mkt-RF, SMB, HML plus bonus RMW and CMA, but **does not include momentum**. MOM is a separate file on Ken French's library (`ff_mom.csv`) and is **required** for the ICM — STR is supposed to load negative on MOM, MHM positive. Download it before writing Section 25.5. LIQ (Pástor-Stambaugh) is a separate, lower-priority source.

---

## 3. Quick integration snippet

Wiring all four reference files into a typical backtest loop:

```python
import pandas as pd

# Load reference data
membership  = pd.read_csv("data/reference/dj30_membership_long.csv",
                          parse_dates=["date"])
early_close = pd.read_csv("data/reference/nyse_early_closes.csv",
                          parse_dates=["date"])
ff          = pd.read_csv("data/reference/F-F_Research_Data_5_Factors_2x3_daily.csv",
                          skiprows=3, skipfooter=2, engine="python")
ff.rename(columns={ff.columns[0]: "date"}, inplace=True)
ff["date"] = pd.to_datetime(ff["date"], format="%Y%m%d")
for c in ff.columns[1:]:
    ff[c] = ff[c].astype(float) / 100.0

# Build the panel
panel = (crsp
         .merge(membership,  on=["date", "ticker"], how="inner")     # PiT filter
         .assign(is_early_close=lambda d: d["date"].isin(early_close["date"]))
         .merge(ff,          on="date",             how="left"))     # factors

# Now `panel` is point-in-time, marked for short sessions, and factor-augmented.
```

---

## 4. Still missing / flagged (as of Week 1)

From the Work1.md "still missing" list plus what we've identified since:

1. **Pástor-Stambaugh LIQ factor** — lower priority; from Lubos Pástor's Chicago Booth page or WRDS.
2. **VIX daily series** — required for regime combiner. Free CSV from CBOE.
3. **FOMC / CPI / NFP event-date dummies** — for the STR gating rule and regime features.
4. **Earnings calendar for the 40 ever-members** — IBES on WRDS or scrape from Zacks/EarningsWhispers.
5. **Treasury 2s10s slope** — FRED DGS2, DGS10. Regime feature.
6. **DJIA / DIA benchmark series** — natural benchmark for a DJ30 strategy; CRSP has S&P and VW but not DJIA itself.
7. **PERMNO ↔ ticker crosswalk** across DD/DWDP/DOW/UTX/RTX CUSIP changes.
8. **JPM spread outlier** — the 13.7 bps median quoted spread flagged in Work1.md §4.3 still needs a root cause before publishing spread-sorted results.
9. **Calendar alignment** — Work1.md §4.7 flagged CRSP ending 2025-09-30 vs. iid_ms ending 2025-12-31. Re-pull CRSP through year-end or trim iid_ms. *Not addressed yet.*
10. **Tick Size Pilot (Oct 2016 – Oct 2018) check** — verify none of the 40 ever-members were Tick Size Pilot constituents. DJ30 is mostly spared but worth a one-line audit.