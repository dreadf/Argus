"""
W5: fetch QQQ and IWM daily closes back to 2016, mirroring
fetch_spy_history.py's method exactly (same chunking, same SIP-with-IEX-
fallback, same self-checks) but as a separate, standalone script rather
than a generalized/parameterized version of that file -- SPY's long-
history fetch is a dependency of the entire Experiment 29 reconstruction
and every number derived from it, so this deliberately shares no code
path with it rather than risk a shared-function bug touching both.

Unlike fetch_spy_history.py's SPY (which never splits), this uses
adjustment=Adjustment.ALL per the W1 fix: neither QQQ nor IWM has split in
this window, checked below as a self-check rather than assumed, but ALL
also handles dividend adjustment, which SPY's own raw_SPY_long.csv
deliberately does NOT apply (see reconstruct.py -- unadjusted is correct
there because it only needs real historical CLOSES, not a return series).
This file is for a DIFFERENT purpose (a rough vol/breach-risk read for
symbol viability, not strike pricing), where dividend-adjusted closes are
the more honest input for a realized-volatility estimate.

Only pipeline/backtest/qqq_iwm_viability.py reads these files. Nothing
else does, and nothing else should -- same file-boundary discipline
fetch_spy_history.py's own docstring states for raw_SPY_long.csv.
"""

from __future__ import annotations

import os

import pandas as pd
from alpaca.data.enums import Adjustment
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

LONG_HISTORY_START = pd.Timestamp("2016-01-01")
OUTPUT_PATHS = {"QQQ": "output/data/raw_QQQ_long.csv", "IWM": "output/data/raw_IWM_long.csv"}


def _chunk_ranges(start: pd.Timestamp, end: pd.Timestamp, months: int = 24) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    ranges = []
    cur = start
    while cur < end:
        nxt = min(cur + pd.DateOffset(months=months), end)
        ranges.append((cur, nxt))
        cur = nxt
    return ranges


def fetch_long_history(symbol: str, start: pd.Timestamp = LONG_HISTORY_START,
                        end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Fetches `symbol`'s daily bars from `start` to `end` (default:
    today), in ~2-year chunks with an IEX fallback per chunk -- same
    method fetch_spy_history.py uses and for the same reason (a
    full-span single request fails on SIP with "subscription does not
    permit querying recent SIP data")."""
    load_dotenv()
    client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
    if end is None:
        end = pd.Timestamp.now()

    def _request(chunk_start, chunk_end, feed: str):
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=chunk_start,
                                end=chunk_end, feed=feed, adjustment=Adjustment.ALL)
        return client.get_stock_bars(req).df

    frames = []
    for chunk_start, chunk_end in _chunk_ranges(start, end):
        try:
            bars = _request(chunk_start, chunk_end, "sip")
        except Exception as e:
            if "sip" not in str(e).lower() and "permit" not in str(e).lower():
                raise
            print(f"  SIP rejected for {chunk_start.date()}-{chunk_end.date()} ({e}), falling back to IEX...")
            bars = _request(chunk_start, chunk_end, "iex")
        frames.append(bars)

    combined = pd.concat(frames)
    df = combined.reset_index()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.tz_convert(None).dt.normalize()
    return df.set_index("date")[["close"]].sort_index()


if __name__ == "__main__":
    from pipeline.extract import assert_no_split_artifacts
    from pipeline.io_utils import atomic_to_csv

    for symbol, output_path in OUTPUT_PATHS.items():
        print(f"Fetching {symbol} from {LONG_HISTORY_START.date()} to today (writing to {output_path})...")
        df = fetch_long_history(symbol)
        print(f"  fetched {len(df)} days, {df.index.min().date()} to {df.index.max().date()}")

        # Self-check: no unadjusted-split artifact slipped through despite
        # adjustment=Adjustment.ALL (same guard pipeline/extract.py uses).
        assert_no_split_artifacts(df["close"], symbol=symbol)
        print(f"  self-check: no split artifacts -- PASS")

        gaps = df.index.to_series().diff().dt.days.dropna()
        max_gap = gaps.max()
        assert max_gap <= 5, f"{symbol}: a {max_gap:.0f}-day gap suggests missing data, not just a long weekend"
        print(f"  self-check: largest gap between trading days = {max_gap:.0f} days -- PASS")

        atomic_to_csv(df.reset_index(), output_path, index=False)
        print(f"  saved to {output_path}\n")
