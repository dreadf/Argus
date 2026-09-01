"""
Loaders for the volatility research track's real market data (see
pipeline/vol/vrp.py's docstring and .claude/plans/we-need-a-major-buzzing-
catmull.md for context). No synthetic data anywhere -- every series here is
observed market prices from a real source, spliced together where sourcing
that history required more than one provider.

VIX3M cross-check, run once (2026-09-01), result summarized here so it isn't
re-derived silently: a peer session's CBOE cache (output/data/vix3m.csv,
starts 2009-09-18) and this session's yfinance ^VIX3M mirror (starts
2007-01-03) agree almost exactly on their 4,262 overlapping days (mean abs
diff $0.0005, one $1.05 outlier day, negligible). yfinance additionally
carries 2007-01-03 to 2009-09-17 that the CBOE cache doesn't have at all.
CBOE's own confirmed VIX3M launch is 2007-11, with published data from
2007-12-04 (https://www.macroption.com/vix3m/) -- the Jan-Nov 2007 yfinance
data predates that and could not be cross-verified against a second source,
so it is dropped. Dec 2007 to Sep 2009 (most of the 2008 crisis) is used from
yfinance alone, flagged below as single-sourced for that window specifically.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

VIX3M_CONFIRMED_LAUNCH = "2007-12-04"  # earliest date treated as real, see module docstring
VIX3M_SPLICE_DATE = "2009-09-18"       # peer session's CBOE cache begins here


def load_vix_series(path: str = "output/data/vix.csv") -> pd.Series:
    """VIX, from a peer session's CBOE cache (full history from 1990)."""
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date")["close"].sort_index()


def load_vix3m_series(
    yfinance_path: str = "output/data/vol_vix_family.csv",
    cboe_path: str = "output/data/vix3m.csv",
) -> pd.Series:
    """VIX3M, spliced: yfinance for 2007-12-04 to 2009-09-17 (single-sourced,
    see module docstring), CBOE cache from 2009-09-18 onward (cross-verified
    against yfinance on the overlap, agrees to within $0.0005 on average)."""
    yf_df = pd.read_csv(yfinance_path, parse_dates=["date"]).set_index("date")["VIX3M"]
    cboe_df = pd.read_csv(cboe_path, parse_dates=["date"]).set_index("date")["close"]

    yf_early = yf_df.loc[VIX3M_CONFIRMED_LAUNCH:VIX3M_SPLICE_DATE].iloc[:-1]  # exclude splice date itself, cboe owns it
    spliced = pd.concat([yf_early, cboe_df]).sort_index()
    assert not spliced.index.duplicated().any(), "VIX3M splice produced duplicate dates"
    return spliced


def load_vix9d_series(path: str = "output/data/vix9d.csv") -> pd.Series:
    """VIX9D, from a peer session's CBOE cache (from 2011; CBOE's own launch
    was Oct 2013, so 2011-2013 in this file is presumably back-computed by
    CBOE, consistent with how VIX3M/VXV history was also back-filled at
    launch -- not independently re-verified here, used only as the plan's
    stated short-horizon supplement, never as the primary crisis-era test)."""
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date")["close"].sort_index()


def load_spy_daily_returns(path: str = "output/data/vol_spy_history.csv") -> pd.Series:
    """Daily log returns from SPY's real close prices, 1993 onward
    (pipeline/vol_extract.py's long-history fetch, separate from
    output/data/raw_SPY.csv which only starts 2020 and belongs to the
    equity-direction track / options bot)."""
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")["close"].sort_index()
    log_returns = np.log(df / df.shift(1))
    return log_returns.dropna()
