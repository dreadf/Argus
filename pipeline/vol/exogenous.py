"""
Exogenous features for Experiment 17 (H5): information HAR structurally
lacks, since HAR only ever sees its own past values. Reuses data already on
disk from the equity-direction track rather than re-fetching.

- market_dispersion: cross-sectional std of daily returns across the 40
  tracked stocks each day -- a known leading indicator of index volatility
  (when stocks start moving very differently from each other, or all
  together, index vol tends to follow).
- news_count: total daily news article volume across all 40 symbols, from
  the same raw_news.csv Experiment 9 (equity track) used, deduplicated the
  same way (an article mentioning multiple symbols was fetched once per
  symbol) -- but aggregated market-wide here, not per-symbol, since the
  target is SPY volatility, not any single stock's direction.
"""

from __future__ import annotations

import ast

import numpy as np
import pandas as pd

from pipeline.config import SYMBOLS


def build_market_dispersion(symbols: list[str] = SYMBOLS) -> pd.Series:
    """Cross-sectional std of daily_return across all symbols, per date."""
    frames = []
    for s in symbols:
        df = pd.read_csv(f"output/data/engineered_{s}.csv", usecols=["timestamp", "daily_return"], parse_dates=["timestamp"])
        df["timestamp"] = df["timestamp"].dt.tz_localize(None).dt.normalize()
        df["symbol"] = s
        frames.append(df)
    panel = pd.concat(frames)
    dispersion = panel.groupby("timestamp")["daily_return"].std()
    dispersion.name = "market_dispersion"
    return dispersion


def build_news_count(path: str = "output/data/raw_news.csv") -> pd.Series:
    """Total daily news volume across all tracked symbols, deduplicated the
    same way as panel.py's add_news_features (an article mentioning
    multiple symbols was fetched once per symbol by news_extract.py)."""
    news = pd.read_csv(path)
    news = news.drop_duplicates(subset=["created_at", "headline"])
    news["timestamp"] = (
        pd.to_datetime(news["created_at"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
        .dt.normalize()
    )
    daily_count = news.groupby("timestamp").size()
    daily_count.name = "news_count"
    return daily_count
