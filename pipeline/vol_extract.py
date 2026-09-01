"""
Fetches the long-history real market data the volatility research track needs
that isn't already on disk (see .claude/plans/we-need-a-major-buzzing-catmull.md):

- VIX, VIX3M, VIX9D: CBOE's published implied-volatility indices, via
  yfinance. VIX3M begins 2007-12-04, VIX9D begins 2013-10-01 -- both
  confirmed against CBOE/vendor documentation before use (see the plan's
  verification log). Used for Test 13a's long-history mechanism check and
  as a candidate feature for Experiment 14's HAR-X specification.
- SPY daily history back to 1993: output/data/raw_SPY.csv only starts
  2020-01-02 (built for the equity-direction track's date range), too
  short for a ~980-week mechanism test. Fetched to a SEPARATELY NAMED file
  (vol_spy_history.csv) so this never collides with the bot's or the
  equity track's use of raw_SPY.csv, per the plan's file-boundary rules.

All data is real, observed market prices -- no synthetic/simulated series
anywhere in this module.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from pipeline.io_utils import atomic_to_csv

OUT_DIR = "output/data"

TICKERS = {
    "VIX": "^VIX",
    "VIX3M": "^VIX3M",
    "VIX9D": "^VIX9D",
}

# Earliest date any of the above tickers has real data, per CBOE/vendor docs
# (checked before use, see the plan's verification log items 2 and 11):
# VIX3M from 2007-12-04, VIX9D from 2013-10-01. Fetching from 2007-01-01
# covers both with a small buffer; yfinance simply returns less for VIX9D.
FETCH_START = "2007-01-01"


def fetch_vix_family(start: str = FETCH_START, out_path: str = f"{OUT_DIR}/vol_vix_family.csv") -> pd.DataFrame:
    """One CSV with columns date, VIX, VIX3M, VIX9D (VIX9D NaN before its
    2013-10-01 start). Real, observed CBOE index closes -- yfinance is a
    convenience mirror, no derived/computed values."""
    frames = {}
    for name, ticker in TICKERS.items():
        df = yf.Ticker(ticker).history(start=start, auto_adjust=False)
        if df.empty:
            raise RuntimeError(f"yfinance returned no data for {ticker} -- check ticker validity or connectivity")
        s = df["Close"]
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        frames[name] = s

    combined = pd.DataFrame(frames)
    combined.index.name = "date"
    combined = combined.sort_index()
    atomic_to_csv(combined.reset_index(), out_path, index=False)
    return combined


def fetch_spy_long_history(start: str = "1993-01-01", out_path: str = f"{OUT_DIR}/vol_spy_history.csv") -> pd.DataFrame:
    """SPY daily OHLC back to its 1993 inception -- a SEPARATE file from
    output/data/raw_SPY.csv (which starts 2020-01-02 and is used by both
    the equity-direction track and the options backtest). Never overwrite
    that file from here."""
    df = yf.Ticker("SPY").history(start=start, auto_adjust=False)
    if df.empty:
        raise RuntimeError("yfinance returned no data for SPY -- check connectivity")
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    df = df[["Open", "High", "Low", "Close", "Volume"]].sort_index()
    df.columns = [c.lower() for c in df.columns]
    atomic_to_csv(df.reset_index(), out_path, index=False)
    return df


if __name__ == "__main__":
    vix = fetch_vix_family()
    print(f"VIX family: {len(vix)} rows, {vix.index.min().date()} to {vix.index.max().date()}")
    print(f"  VIX3M non-null from: {vix['VIX3M'].first_valid_index().date()}")
    print(f"  VIX9D non-null from: {vix['VIX9D'].first_valid_index().date()}")

    spy = fetch_spy_long_history()
    print(f"\nSPY long history: {len(spy)} rows, {spy.index.min().date()} to {spy.index.max().date()}")
