"""Unit tests for src/taq/aggregate_bars.py.

All tests run on tiny synthetic in-memory TAQ frames — no real data required.
Run locally from the project root:

    source venv/bin/activate
    python -m pytest tests/test_taq_aggregation.py -v
"""
from __future__ import annotations

from io import BytesIO
import gzip

import numpy as np
import pandas as pd
import pytest

from src.taq.aggregate_bars import (
    BAD_SCOND,
    EARLY_CLOSE,
    REG_CLOSE,
    REG_OPEN,
    aggregate_from_trades,
    aggregate_year,
    bar_index,
    filter_trades,
    iter_chunks,
    parse_time_to_sec,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def make_trades(rows: list[dict]) -> pd.DataFrame:
    """Materialize a tiny TAQ-shaped frame with the right dtypes."""
    df = pd.DataFrame(rows)
    # Column-level defaults first (for cases where the column is absent entirely),
    # then per-cell fill for rows in a mixed column.
    defaults = {"EX": "N", "SYM_SUFFIX": "", "TR_SCOND": "@", "TR_CORR": "00"}
    for col, val in defaults.items():
        if col not in df:
            df[col] = val
        else:
            df[col] = df[col].fillna(val)
    df["SYM_SUFFIX"] = df["SYM_SUFFIX"].replace("", pd.NA).astype("string")
    df["TR_SCOND"] = df["TR_SCOND"].astype("string")
    df["TR_CORR"] = df["TR_CORR"].astype(str)
    df["SIZE"] = df["SIZE"].astype("int64")
    df["PRICE"] = df["PRICE"].astype("float64")
    return df[["DATE", "TIME_M", "EX", "SYM_ROOT", "SYM_SUFFIX",
               "TR_SCOND", "SIZE", "PRICE", "TR_CORR"]]


# --------------------------------------------------------------------------- #
# parse_time_to_sec                                                           #
# --------------------------------------------------------------------------- #

def test_parse_time_to_sec_basic():
    s = pd.Series(["09:30:00.000000000", "09:30:23.015000000",
                   "16:00:00.000000000", "04:00:00.000000000"])
    got = parse_time_to_sec(s)
    assert got.tolist() == [34200, 34223, 57600, 14400]


def test_parse_time_to_sec_noon():
    assert parse_time_to_sec(pd.Series(["12:00:00.000"])).iloc[0] == 12 * 3600


def test_parse_time_to_sec_single_digit_hour():
    """TAQ emits hour without zero-padding: '4:00:00.017392614' for 04:00:00.
    Regression test — the original fixed-width slice broke on production data."""
    s = pd.Series(["4:00:00.017392614", "9:30:23.015000000",
                   "10:00:00.000000000", "9:0:0.0"])
    got = parse_time_to_sec(s)
    assert got.tolist() == [4 * 3600, 9 * 3600 + 30 * 60 + 23,
                            10 * 3600, 9 * 3600]


# --------------------------------------------------------------------------- #
# bar_index                                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("hhmmss,expected_bar", [
    ("09:30:00", 1),   # first bar starts
    ("09:59:59", 1),   # still first bar
    ("10:00:00", 2),
    ("10:29:59", 2),
    ("15:30:00", 13),  # last regular bar starts
    ("15:59:59", 13),
    ("09:29:59", 0),   # pre-session
    ("16:00:00", 0),   # after close (boundary exclusive)
    ("17:00:00", 0),   # post-session
])
def test_bar_index_regular(hhmmss, expected_bar):
    sec = parse_time_to_sec(pd.Series([hhmmss + ".0"]))
    got = bar_index(sec, is_early_close=False)
    assert got.iloc[0] == expected_bar


@pytest.mark.parametrize("hhmmss,expected_bar", [
    ("09:30:00", 1),
    ("12:30:00", 7),
    ("12:59:59", 7),
    ("13:00:00", 0),   # early-close boundary
    ("15:30:00", 0),   # after early close
])
def test_bar_index_early_close(hhmmss, expected_bar):
    sec = parse_time_to_sec(pd.Series([hhmmss + ".0"]))
    got = bar_index(sec, is_early_close=True)
    assert got.iloc[0] == expected_bar


def test_bar_index_vectorized_mixed():
    """Mixed early-close / regular days in one call."""
    sec = parse_time_to_sec(pd.Series([
        "10:00:00.0",  # bar 2 regular
        "12:30:00.0",  # bar 7 on early-close, bar 7 on regular
        "15:30:00.0",  # bar 13 regular, 0 on early-close
    ]))
    is_early = pd.Series([False, True, True])
    got = bar_index(sec, is_early_close=is_early)
    assert got.tolist() == [2, 7, 0]


# --------------------------------------------------------------------------- #
# TR_SCOND filter (BAD_SCOND regex)                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("scond,blocked", [
    ("@", False),       # primary regular sale — keep
    ("@ TI", True),     # pre-market T flag
    ("F", False),       # intermarket sweep — keep
    ("@ Z", True),
    ("@ L", True),
    ("@ 6", True),
    ("@ O", True),
    ("@ U", True),
    ("@ I", True),
    ("@ W", True),
    ("", False),        # empty — not blocked
    ("FTIP", True),     # T somewhere inside
])
def test_bad_scond_regex(scond, blocked):
    assert bool(BAD_SCOND.search(scond)) == blocked


# --------------------------------------------------------------------------- #
# filter_trades                                                               #
# --------------------------------------------------------------------------- #

def test_filter_trades_keeps_only_dj30_regular_session():
    trades = make_trades([
        # Keep: regular DJ30 trade
        {"DATE": "2017-01-03", "TIME_M": "10:00:00.0", "SYM_ROOT": "AAPL",
         "SIZE": 100, "PRICE": 120.0},
        # Drop: pre-market
        {"DATE": "2017-01-03", "TIME_M": "04:00:00.0", "SYM_ROOT": "AAPL",
         "SIZE": 1,   "PRICE": 116.0, "TR_SCOND": "@ TI"},
        # Drop: not a DJ30 ticker
        {"DATE": "2017-01-03", "TIME_M": "10:00:00.0", "SYM_ROOT": "FB",
         "SIZE": 100, "PRICE": 133.0},
        # Drop: SYM_SUFFIX non-empty (preferred share)
        {"DATE": "2017-01-03", "TIME_M": "10:00:00.0", "SYM_ROOT": "JPM",
         "SYM_SUFFIX": "PRA",
         "SIZE": 100, "PRICE": 25.0},
        # Drop: TR_CORR != 00
        {"DATE": "2017-01-03", "TIME_M": "10:00:00.0", "SYM_ROOT": "AAPL",
         "TR_CORR": "01", "SIZE": 100, "PRICE": 120.0},
        # Drop: PRICE <= 0
        {"DATE": "2017-01-03", "TIME_M": "10:00:00.0", "SYM_ROOT": "AAPL",
         "SIZE": 100, "PRICE": 0.0},
        # Drop: odd-lot (SCOND I)
        {"DATE": "2017-01-03", "TIME_M": "10:00:00.0", "SYM_ROOT": "AAPL",
         "TR_SCOND": "@ I", "SIZE": 50, "PRICE": 120.0},
        # Drop: after close
        {"DATE": "2017-01-03", "TIME_M": "16:05:00.0", "SYM_ROOT": "AAPL",
         "SIZE": 100, "PRICE": 120.0},
    ])

    filt = filter_trades(trades, keep_tickers={"AAPL", "JPM"},
                         early_close_dates=set())
    assert len(filt) == 1
    assert filt.iloc[0]["SYM_ROOT"] == "AAPL"
    assert filt.iloc[0]["PRICE"] == 120.0


def test_filter_trades_respects_early_close():
    """On an early-close day, trades at 15:00 should drop even though they'd
    be valid on a regular day."""
    trades = make_trades([
        {"DATE": "2017-07-03", "TIME_M": "10:00:00.0", "SYM_ROOT": "AAPL",
         "SIZE": 100, "PRICE": 120.0},
        {"DATE": "2017-07-03", "TIME_M": "15:00:00.0", "SYM_ROOT": "AAPL",
         "SIZE": 100, "PRICE": 121.0},  # after 13:00 close on July 3
    ])
    early = {pd.Timestamp("2017-07-03")}
    filt = filter_trades(trades, keep_tickers={"AAPL"}, early_close_dates=early)
    assert len(filt) == 1
    assert filt.iloc[0]["TIME_M"] == "10:00:00.0"


# --------------------------------------------------------------------------- #
# aggregate_from_trades                                                       #
# --------------------------------------------------------------------------- #

def test_aggregate_drops_first_and_last_bars_regular():
    """Build a one-day AAPL frame with one trade in every bar. After aggregation
    we should have bars 2..12 → 11 bars, re-numbered 1..11."""
    rows = []
    for hh in range(9, 16):
        for mm in (30 if hh == 9 else 0, 0 if hh == 9 else 30):
            t = f"{hh:02d}:{mm:02d}:01.0"
            rows.append({"DATE": "2017-01-03", "TIME_M": t,
                         "SYM_ROOT": "AAPL", "SIZE": 100, "PRICE": 120 + hh})
    # Dedup the weird ordering
    trades = make_trades(rows)
    filt = filter_trades(trades, keep_tickers={"AAPL"}, early_close_dates=set())
    agg = aggregate_from_trades(filt)

    assert len(agg) == 11, f"expected 11 kept bars, got {len(agg)}: {agg['bar_raw'].tolist()}"
    assert agg["bar_raw"].min() == 2 and agg["bar_raw"].max() == 12
    assert agg["bar"].tolist() == list(range(1, 12))


def test_aggregate_vwap_dollar_volume_consistency():
    """VWAP = dollar_volume / volume, and n_trades matches row count."""
    trades = make_trades([
        {"DATE": "2017-01-03", "TIME_M": "10:00:01.0", "SYM_ROOT": "AAPL",
         "SIZE": 100, "PRICE": 120.0},
        {"DATE": "2017-01-03", "TIME_M": "10:05:00.0", "SYM_ROOT": "AAPL",
         "SIZE": 300, "PRICE": 121.0},
        {"DATE": "2017-01-03", "TIME_M": "10:29:59.0", "SYM_ROOT": "AAPL",
         "SIZE": 200, "PRICE": 122.0},
    ])
    filt = filter_trades(trades, keep_tickers={"AAPL"}, early_close_dates=set())
    agg = aggregate_from_trades(filt)
    assert len(agg) == 1
    row = agg.iloc[0]
    assert row["n_trades"] == 3
    assert row["volume"] == 600
    # dollar_volume = 100*120 + 300*121 + 200*122 = 12_000 + 36_300 + 24_400 = 72_700
    assert row["dollar_volume"] == pytest.approx(72_700.0)
    assert row["vwap"] == pytest.approx(72_700.0 / 600)
    assert row["open"] == 120.0
    assert row["high"] == 122.0
    assert row["low"] == 120.0
    assert row["close"] == 122.0


def test_aggregate_early_close_day_keeps_5_bars():
    """On 2017-07-03 (early close), bars 2..6 are kept → 5 bars, re-numbered 1..5.

    Early close session is 09:30-13:00 with 7 raw half-hour slots; drop first
    and last → 5 bars survive.
    """
    rows = []
    # one trade at the start of each 30-min slot: 09:30, 10:00, 10:30, ..., 12:30
    for slot_min in range(0, 7 * 30, 30):
        hh = 9 + (30 + slot_min) // 60
        mm = (30 + slot_min) % 60
        t = f"{hh:02d}:{mm:02d}:01.0"
        rows.append({"DATE": "2017-07-03", "TIME_M": t,
                     "SYM_ROOT": "AAPL", "SIZE": 100, "PRICE": 120 + slot_min / 30})
    trades = make_trades(rows)
    early = {pd.Timestamp("2017-07-03")}
    filt = filter_trades(trades, keep_tickers={"AAPL"}, early_close_dates=early)
    agg = aggregate_from_trades(filt)

    # kept bars: 2..6
    assert agg["bar_raw"].min() == 2 and agg["bar_raw"].max() == 6
    assert len(agg) == 5
    assert agg["bar"].tolist() == [1, 2, 3, 4, 5]


# --------------------------------------------------------------------------- #
# aggregate_year  (full pipeline, tiny synthetic gzip)                        #
# --------------------------------------------------------------------------- #

def _write_mini_taq(tmp_path, rows) -> "pathlib.Path":
    import io
    df = make_trades(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    path = tmp_path / "TAQ2017.csv.gz"
    with gzip.open(path, "wb") as f:
        f.write(buf.getvalue())
    return path


def test_aggregate_year_end_to_end(tmp_path):
    rows = []
    for day in ("2017-01-03", "2017-01-04"):
        for hh in range(10, 15):      # bars 2..11
            rows.append({"DATE": day, "TIME_M": f"{hh:02d}:00:01.0",
                         "SYM_ROOT": "AAPL", "SIZE": 100, "PRICE": 120.0 + hh})
            rows.append({"DATE": day, "TIME_M": f"{hh:02d}:15:01.0",
                         "SYM_ROOT": "MSFT", "SIZE": 50, "PRICE": 60.0 + hh})
        # one pre-market trade that MUST be filtered out
        rows.append({"DATE": day, "TIME_M": "04:00:00.0",
                     "SYM_ROOT": "AAPL", "SIZE": 1, "PRICE": 115.0,
                     "TR_SCOND": "@ TI"})

    taq = _write_mini_taq(tmp_path, rows)
    out = tmp_path / "out"

    meta = aggregate_year(
        input_path=taq, output_dir=out, year=2017,
        keep_tickers={"AAPL", "MSFT"}, early_close_dates=set(),
        chunksize=1000,
    )

    assert meta["tickers"] == 2
    assert meta["rows_kept"] == 20   # 2 days × 5 bars × 2 tickers
    # Check on-disk layout
    aapl = pd.read_parquet(out / "year=2017" / "ticker=AAPL.parquet")
    msft = pd.read_parquet(out / "year=2017" / "ticker=MSFT.parquet")
    assert len(aapl) == 10  # 5 bars × 2 days
    assert len(msft) == 10
    assert set(aapl["bar"]) <= set(range(1, 12))
    # VWAP consistency spot check
    assert (aapl["vwap"] - aapl["dollar_volume"] / aapl["volume"]).abs().max() < 1e-9
