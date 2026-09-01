"""
W2: fetch SPY daily closes back to 2016 for the long-history reconstruction
(pipeline/backtest/reconstruct.py) and breach-rate work -- separate from,
and deliberately never touching, output/data/raw_SPY.csv.

That file is pipeline.config.MARKET_SYMBOL's data, consumed by
pooled_xgb_model.py via add_market_features and refetched by extract.py
for the 2020-2026 window every 41-symbol pipeline run. Fetching a longer
SPY range through the shared extract.py/fetch_and_save path would silently
rewrite that file out from under the ML track (Collision 1/2 in the
options-track plan). This module writes its own separately named file
instead, so the two tracks can never step on each other regardless of
which one runs first or how often.

Only spread_backtest.py's reconstruction path (W3) reads
raw_SPY_long.csv. Nothing else does, and nothing else should.
"""

from __future__ import annotations

import os

import pandas as pd
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

LONG_HISTORY_START = pd.Timestamp("2016-01-01")
OUTPUT_PATH = "output/data/raw_SPY_long.csv"


def _chunk_ranges(start: pd.Timestamp, end: pd.Timestamp, months: int = 24) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    ranges = []
    cur = start
    while cur < end:
        nxt = min(cur + pd.DateOffset(months=months), end)
        ranges.append((cur, nxt))
        cur = nxt
    return ranges


def fetch_spy_long_history(start: pd.Timestamp = LONG_HISTORY_START, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Fetches SPY daily bars from `start` to `end` (default: today), in
    ~2-year chunks rather than one request spanning the whole range.

    A single request for the full 2016-2026 span on the SIP feed
    consistently failed with "subscription does not permit querying
    recent SIP data" (confirmed reproducible, not transient: 3 retries,
    same error). Bisecting the exact same overall range into yearly
    windows and requesting each separately succeeded on SIP every time,
    recovering the full history -- whatever internal limit is being hit
    (span, row count, or something else undocumented) is per-request, not
    a hard boundary on how old the data can be. IEX is kept as a
    per-chunk fallback, but is known to only carry data back to
    2018-11-01 (confirmed empirically: four different start dates from
    2015-2018 all returned the identical earliest bar), so a chunk that
    needs IEX will silently lose whatever portion of itself predates that
    floor -- the post-fetch self-checks below exist specifically to catch
    that rather than let it pass silently."""
    load_dotenv()
    client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
    if end is None:
        end = pd.Timestamp.now()

    def _request(chunk_start, chunk_end, feed: str):
        req = StockBarsRequest(symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=chunk_start, end=chunk_end, feed=feed)
        return client.get_stock_bars(req).df

    frames = []
    for chunk_start, chunk_end in _chunk_ranges(start, end):
        try:
            bars = _request(chunk_start, chunk_end, "sip")
        except Exception as e:
            if "sip" not in str(e).lower() and "permit" not in str(e).lower():
                raise
            print(f"  SIP rejected for {chunk_start.date()}-{chunk_end.date()} ({e}), falling back to IEX for this chunk...")
            bars = _request(chunk_start, chunk_end, "iex")
        frames.append(bars)

    combined = pd.concat(frames)
    df = combined.reset_index()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.tz_convert(None).dt.normalize()
    return df.set_index("date")[["close"]].sort_index()


if __name__ == "__main__":
    from pipeline.io_utils import atomic_to_csv

    print(f"Fetching SPY from {LONG_HISTORY_START.date()} to today (writing to {OUTPUT_PATH}, NOT raw_SPY.csv)...")
    df = fetch_spy_long_history()
    print(f"Fetched {len(df)} days, {df.index.min().date()} to {df.index.max().date()}")

    # Self-check 1: the four stress events this history exists to capture
    # are actually present in the fetched range.
    stress_events = {
        "Feb 2018 volmageddon": "2018-02-05",
        "Q4 2018 selloff": "2018-12-24",
        "COVID crash": "2020-03-23",
        "2022 bear market start": "2022-01-03",
    }
    for label, d in stress_events.items():
        present = pd.Timestamp(d) in df.index or any(abs((df.index - pd.Timestamp(d)).days) <= 3)
        print(f"  {label} ({d}): {'covered' if present else 'MISSING from fetched range'}")
        assert present, f"expected {label} ({d}) to be inside the fetched history"

    # Self-check 2: no gaps of more than a long holiday weekend (a genuine
    # data hole would show up as a multi-week gap between trading days).
    gaps = df.index.to_series().diff().dt.days.dropna()
    max_gap = gaps.max()
    print(f"Self-check: largest gap between consecutive trading days = {max_gap:.0f} days")
    assert max_gap <= 5, f"a {max_gap:.0f}-day gap suggests missing data, not just a long weekend"

    # Self-check 3: raw_SPY.csv (the ML track's file) is untouched by this run.
    other_path = "output/data/raw_SPY.csv"
    before = os.path.getmtime(other_path) if os.path.exists(other_path) else None
    atomic_to_csv(df.reset_index(), OUTPUT_PATH, index=False)
    after = os.path.getmtime(other_path) if os.path.exists(other_path) else None
    assert before == after, "raw_SPY.csv's mtime changed -- this must never touch that file"
    print(f"Self-check: {other_path} untouched (mtime unchanged) -- PASS")

    print(f"\nSaved to {OUTPUT_PATH}")
