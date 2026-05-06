# data/interim/ — Load-time data quality notes

Running log of gaps discovered during typed parquet construction.

## 2026-04-17 — CRSP + iid GS gap: RESOLVED

**Status.** Resolved 2026-04-17 by supplementary WRDS pulls:
`data/raw/dow_daily_gs.csv.gz` (2,450 rows, PERMNO 86868) and
`data/raw/dow_intraday_gs.csv.gz` (~16k rows, multi-security). Both loaders now
concatenate the supplements automatically. Cross-dataset validator R3 shows
30 names on every one of 2,450 trading days. If a future full CRSP re-pull
includes GS, just delete the `_gs` files — the loaders pick them up only if
they exist.

## 2026-04-17 — Single CRSP duplicate row at RTX 2020-04-03

**Fact.** The raw pull has two identical rows for RTX on 2020-04-03 (at the UTX→RTX ticker transition). `load_crsp.py` drops the duplicate.

**Impact.** None after dedup.

## 2026-04-17 — iid_ms has multi-security (date, ticker) rows

**Fact.** The WRDS iid_ms pull includes preferred shares, class-B shares, and warrants sharing a `SYM_ROOT` with the common stock. ~21k duplicate rows, concentrated in JPM (18 series: JPMPRA … JPMPRM, JPMWS), DD (3 series), BA, and others. GS also has ~5 preferreds in the supplementary pull.

**Impact.** None after dedup. `load_iid.py` keeps the single most-traded security per `(date, ticker)` by `total_dollar_m` — the common stock dominates by 1-3 orders of magnitude so the pick is unambiguous.

## 2026-04-17 — UTX→RTX ticker relabel on 2020-04-03

**Fact.** The UTC+Raytheon merger closed on Fri 2020-04-03. CRSP and iid both
relabel PERMNO 17830 as RTX starting that day, but S&P DJI kept UTX in the
index through 2020-04-03 and added RTX on Mon 2020-04-06 (see
`data/reference/dj30_events.csv`). That single-day legal-entity vs. index-rules
mismatch would otherwise leave the 2020-04-03 PIT panel at 29 names.

**Mitigation.** Both loaders apply a one-cell ticker patch: on 2020-04-03, the
RTX row (PERMNO 17830) is relabeled back to UTX so it matches the membership
file. The underlying security is the same merged entity; only the label
differs.

**Impact.** PIT merge produces 30 names on every trading day.

## 2026-04-17 — IBES missing GS earnings

**Fact.** `data/raw/IBES.csv.gz` has 39 `OFTIC` codes; GS is absent.

**Impact.** Minor. The §8.7 earnings-blackout robustness check will treat GS as
having no earnings announcements and therefore never blacked out. Sharpes
attributable to GS positions are not adjusted for earnings drift.

**Remediation if relevant later.** Add GS (IBES TICKER likely "GS" or legacy
"GOLD") to the IBES WRDS pull and concat with `src/data/load_ibes.py`.
