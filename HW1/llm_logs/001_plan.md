# LLM Log 001 — Initial planning session + Week-1 scaffolding

**Model:** Claude Opus 4.7 (1M context)
**Date:** 2026-04-13
**Session:** Claude Code CLI, interactive

## Prompts

> I'm thinking ahead about possible landmines and data idiosyncrasies, so before we even start coding, please read both `_info/main_plan.tex` and `_info/Work1.md` exhaustively — you need to internalize not just the workflow, but the intended statistical guarantees, evaluation protocols, and calendar conventions.
>
> I've attached a snippet from our CRSP raw loader, please step through and verify: does it strictly select the full DJ30 membership each day? Are any tickers missing or misaligned, especially on corporate action dates? How is universe completeness enforced?
>
> Here is a list of EDA outputs and data directories we have from prior work. Please check: do these outputs fully match the schema and feature layout specified in the plan? Are there any missing variables or dtype mismatches across parquet and CSV? Be granular — check joins, key fields, and row counts.
>
> When you build the Week-1 scaffolding, call out any technical or data-quality issues before writing code. For each component:
> - What assumptions are hard-coded in the current pipeline?
> - Are there any latent issues you see (ambiguous tickers, nulls, partial days)?
> - Document every case where the choice of reference field (e.g., IBES OFTIC versus legacy ticker) could break downstream merges.
>
> Please ask me every question whose answer could shift architectural decisions. Don't just gently prompt — if in doubt, give me a specific code chunk and the ambiguity you see, so we can work through it collaboratively. Propose parameterizations or fail-fast checks if you suspect sources of silent error.
>
> As you architect the build, break down day-by-day, but anticipate cross-week dependencies. Explicitly flag any step that could be blocked or entail rework later.
>
> I've thought a lot about the design, but I want you to push back: where are the gaps or unstable inferences? For example, is the Bonferroni calculation correct in light of the actual number of hypothesis tests? Does our current threshold align with best practices in Section 5.6 of Work1.md?
>
> When reviewing outputs, please show me anything you want confirmed: post your inferred table shapes, row counts, and any columns with unexpected null rates/high cardinality. Don't move forward if you're unsure.

## What the model was asked to produce

1. Read both governing docs end-to-end.
2. Inventory the existing codebase / data / EDA outputs.
3. Produce an executable plan covering the full build.
4. Ask only the questions whose answers change architecture.
5. Begin executing Week 1.

## Output (high level; full plan persisted at `.claude/plans/hazy-napping-moore.md`)

Three decisions surfaced via AskUserQuestion and answered by the user:

1. Calendar alignment — trim iid to 2025-09-30 (not re-pull CRSP).
2. H1 TAQ — full aggregation on MIT Engaging, not "stretch skip."
3. Earnings blackout — user added `data/IBES.csv.gz` so §8.7 is unblocked.

Week-1 scaffolding produced:

- [src/data/load_crsp.py](../src/data/load_crsp.py) — wrote `data/interim/daily.parquet` (90,231 rows, 39 tickers, 2016-01-04 → 2025-09-30).
- [src/data/load_iid.py](../src/data/load_iid.py) — wrote `data/interim/intraday.parquet` (90,678 rows; dedupe keeps max-dollar-volume security per `(date, ticker)`).
- [src/data/load_ibes.py](../src/data/load_ibes.py) — wrote `data/reference/earnings_dates.csv` (1,436 announcements; 962 BMO / 471 AMC / 3 intraday; uses OFTIC not legacy IBES TICKER).
- [src/data/validate.py](../src/data/validate.py) — cross-dataset audit; all six checks green.
- [src/backtest/{portfolio,engine,costs,metrics}.py](../src/backtest/) — tercile long-short, horizon-agnostic engine, turnover cost model, summary+NW+Bonferroni metrics. Self-tests pass.

## Non-trivial technical decisions made in this session

1. **Dedup in iid_ms loader.** iid uses `SYM_ROOT` only, so preferreds/class-B/warrants collapse onto the same `(date, ticker)` key. JPM has 9 such rows on 2016-01-04; DD has 3. Resolved by sorting descending on `total_dollar_m` and keeping the first — common stock dominates by 1-3 orders of magnitude so the pick is unambiguous.
2. **IBES `OFTIC` instead of `TICKER`.** IBES's `TICKER` field is legacy (NIKE, VISA, UNIH, CHV, WAG, XON, …); `OFTIC` is the stable original ticker that joins to CRSP.
3. **Bonferroni formula.** 12 tests × α=5% two-sided → t* = Φ⁻¹(1 − 0.00417/2) = 2.8653. Matches the ≈2.87 quoted in Work1.md §5.6.
4. **Data-quality gap: GS absent from CRSP + iid.** Documented in `data/interim/LOAD_NOTES.md`. Pipeline runs on 29-name universes in the interim; PIT assertions relaxed to `nunique in {28, 29, 30}`. The one 28-name day (2020-04-03) is the UTX→RTX merger-day where CRSP assigned the row to RTX while S&P DJI kept UTX as a member through that date.

## How the output was used

- Plan file → approval & execution roadmap.
- Week-1 code → committed to `src/` subdirs.
- `LOAD_NOTES.md` → ongoing data-quality log.
- This log itself → Work1.md §15 attribution; first entry.
