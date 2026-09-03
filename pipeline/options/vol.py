"""
Annualized realized volatility on log returns.

Deliberately not added to transform.py: transform.py:62-63 computes an
un-annualized standard deviation of *simple* returns for the equity ML
features, and those experiments must stay reproducible exactly as they ran.
Options need log returns, annualized by sqrt(252), which is a different
quantity used for a different purpose (comparing to IV, sizing distance).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

from pipeline.options.config import UNDERLYING

TRADING_DAYS_PER_YEAR = 252

_stock_data_client_cache: StockHistoricalDataClient | None = None


def _get_stock_data_client() -> StockHistoricalDataClient:
    """Constructed lazily, on first real use, not at module import time --
    the same class of bug fixed this session in pipeline/extract.py,
    pipeline/run_all.py, pipeline/backtest/spread_backtest.py, and
    pipeline/options/chain.py (a fifth instance, flagged by a peer
    session's own test run rather than found independently). Every dev
    machine has a real .env, which is exactly why this was invisible
    locally; CI has none, by design."""
    global _stock_data_client_cache
    if _stock_data_client_cache is None:
        load_dotenv()
        _stock_data_client_cache = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
    return _stock_data_client_cache


def log_returns(closes: pd.Series) -> pd.Series:
    return np.log(closes / closes.shift(1)).dropna()


def realized_vol(closes: pd.Series, window: int) -> float:
    """Annualized realized volatility over the last `window` daily closes."""
    if len(closes) < window + 1:
        raise ValueError(f"need at least {window + 1} closes, got {len(closes)}")
    rets = log_returns(closes.tail(window + 1))
    return float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


def realized_vol_series(closes: pd.Series, window: int) -> pd.Series:
    """Rolling annualized realized volatility, one value per day once enough
    history exists. Used by the backtest to reconstruct what a volatility
    regime filter would have seen on each historical date."""
    rets = log_returns(closes)
    return rets.rolling(window).std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)


def fetch_recent_closes(symbol: str = UNDERLYING, lookback_days: int = 40) -> pd.Series:
    """Live daily closes for the last `lookback_days` calendar days -- enough
    padding for a 21-day rolling window even across weekends/holidays."""
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=lookback_days)
    # The account's data subscription doesn't permit recent SIP data; IEX
    # (free-tier eligible) is sufficient for daily closes used in a vol
    # estimate -- confirmed empirically (SIP raised "does not permit
    # querying recent SIP data", IEX did not).
    request = StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start, end=end, feed=DataFeed.IEX
    )
    bars = _get_stock_data_client().get_stock_bars(request).df
    closes = bars.loc[symbol]["close"] if isinstance(bars.index, pd.MultiIndex) else bars["close"]
    return closes


if __name__ == "__main__":
    # Self-check 1: a known-shape sanity check -- constant daily returns of
    # zero should give zero vol, and a fixed daily log-return should annualize
    # to that value times sqrt(252) exactly.
    flat = pd.Series([100.0] * 30)
    assert realized_vol(flat, 21) == 0.0

    daily_log_ret = 0.01
    growing = pd.Series([100.0 * np.exp(daily_log_ret * i) for i in range(30)])
    computed = realized_vol(growing, 21)
    # Deterministic geometric growth has zero *variance* in log returns
    # (every day's log return is exactly daily_log_ret), so vol should be ~0,
    # not daily_log_ret * sqrt(252). This checks the function measures
    # variance of returns, not the drift.
    assert abs(computed) < 1e-8, computed

    # Self-check 2: against real history, if raw_SPY.csv is present.
    csv_path = "output/data/raw_SPY.csv"
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=["timestamp"])
        closes = df.set_index("timestamp")["close"]
        v10 = realized_vol(closes, 10)
        v21 = realized_vol(closes, 21)
        print(f"raw_SPY.csv: 10-day annualized RV = {v10:.4f}, 21-day annualized RV = {v21:.4f}")
        assert 0.0 < v10 < 2.0 and 0.0 < v21 < 2.0, "annualized vol out of a sane [0, 200%] range"

    # Self-check 3: live fetch.
    live_closes = fetch_recent_closes()
    print(f"Fetched {len(live_closes)} live daily closes for {UNDERLYING}")
    live_rv10 = realized_vol(live_closes, 10)
    print(f"Live 10-day annualized RV for {UNDERLYING}: {live_rv10:.4f}")
    assert 0.0 < live_rv10 < 2.0

    print("All vol.py self-checks passed.")
