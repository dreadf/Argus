"""
Realized variance estimators for the volatility forecasting track
(Experiments 14+, H2/H3 in .claude/plans/we-need-a-major-buzzing-catmull.md).

fetch_intraday_daily_rv(): the primary estimator. Real 1-minute SPY bars from
Alpaca, confirmed available from roughly mid-2016 onward (empty before that
on this account's feed -- checked directly: 2015-06-01 empty, 2016-06-01 has
726 bars). Daily realized variance = sum of squared 1-minute log returns
within regular trading hours (13:30-20:00 UTC), the standard RV construction
(Andersen-Bollerslev). This is real, observed intraday price data -- no
synthetic bars anywhere.

yang_zhang_daily(): fallback range-based estimator from daily OHLC only, for
anything needing history before 2016 or if the intraday fetch is
unavailable. Roughly 5x more efficient than close-to-close variance
(Yang & Zhang, 2000) because it uses the open/high/low/close range, not just
the close-to-close return.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
RTH_START_UTC = "13:30"
RTH_END_UTC = "20:00"


def _fetch_minute_bars_chunked(symbol: str, start: date, end: date, chunk_days: int = 90) -> pd.DataFrame:
    """Alpaca's SIP feed rejects very wide date ranges for minute data on
    some accounts (a concurrent session hit this independently on daily
    bars: 'does not permit querying recent SIP data', resolved the same way
    -- chunk into smaller windows). Chunks into `chunk_days`-day windows and
    concatenates."""
    import os

    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from dotenv import load_dotenv

    load_dotenv()
    client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))

    frames = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + pd.Timedelta(days=chunk_days), end)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=datetime.combine(cursor, datetime.min.time()),
            end=datetime.combine(chunk_end, datetime.min.time()),
        )
        for attempt in range(3):
            try:
                df = client.get_stock_bars(req).df
                break
            except Exception as e:
                wait = 5 * (attempt + 1)
                print(f"  minute bars {cursor}-{chunk_end} failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
        else:
            raise RuntimeError(f"minute bars fetch failed 3 times for {cursor} to {chunk_end}")
        if not df.empty:
            frames.append(df)
        cursor = chunk_end
        time.sleep(0.2)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames)


def _minute_log_returns(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Shared fetch: real 1-minute bars -> per-minute log returns within
    RTH, with the day boundary correctly broken (no overnight-gap return
    counted as if it were intraday). Both fetch_intraday_daily_rv and
    fetch_intraday_semivariance build on this so the expensive minute-bar
    fetch happens once, not once per estimator."""
    raw = _fetch_minute_bars_chunked(symbol, start, end)
    if raw.empty:
        raise RuntimeError(f"no minute bars returned for {symbol} {start} to {end}")

    df = raw.xs(symbol, level="symbol") if symbol in raw.index.get_level_values("symbol") else raw
    df = df.reset_index()
    ts = df["timestamp"]
    rth_mask = (ts.dt.strftime("%H:%M") >= RTH_START_UTC) & (ts.dt.strftime("%H:%M") < RTH_END_UTC)
    df = df[rth_mask].copy()
    df["date"] = ts.dt.tz_localize(None).dt.normalize()
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df.loc[df["date"] != df["date"].shift(1), "log_ret"] = np.nan
    return df.dropna(subset=["log_ret"])


def fetch_intraday_full(
    symbol: str = "SPY",
    start: date = date(2016, 7, 1),
    end: date | None = None,
) -> pd.DataFrame:
    """One fetch, every estimator this track needs from it:
    - rv: total realized variance (sum of squared 1-min log returns)
    - rv_pos / rv_neg: Patton-Sheppard realized SEMIvariance -- rv split by
      the sign of each minute's return (Patton & Sheppard 2015: rv_neg is
      the stronger predictor of future vol; H2's core test).
    - bpv: bipower variation (Barndorff-Nielsen & Shephard 2004), a jump-
      robust variance estimate; rv - bpv is the estimated jump contribution
      (Andersen-Bollerslev-Diebold), used for the HAR-RV-J specification.
    All annualized to percentage-point volatility units (sqrt(x*252)*100)
    for direct comparability with VIX and the plain RV series."""
    if end is None:
        end = date.today()
    minute_returns = _minute_log_returns(symbol, start, end)

    def _day_stats(r: pd.Series) -> pd.Series:
        r = r.to_numpy()
        rv = np.sum(r ** 2)
        rv_pos = np.sum(r[r > 0] ** 2)
        rv_neg = np.sum(r[r < 0] ** 2)
        # Bipower variation: mu1^-2 * sum(|r_i| * |r_{i-1}|), mu1 = sqrt(2/pi).
        mu1_inv2 = np.pi / 2
        abs_r = np.abs(r)
        bpv = mu1_inv2 * np.sum(abs_r[1:] * abs_r[:-1]) if len(r) > 1 else np.nan
        return pd.Series({"rv": rv, "rv_pos": rv_pos, "rv_neg": rv_neg, "bpv": bpv, "n_minutes": len(r)})

    daily = minute_returns.groupby("date")["log_ret"].apply(_day_stats).unstack()
    daily["jump"] = (daily["rv"] - daily["bpv"]).clip(lower=0)

    ann = np.sqrt(TRADING_DAYS_PER_YEAR) * 100
    out = pd.DataFrame({
        "realized_vol_annualized_pct": np.sqrt(daily["rv"]) * ann,
        "rv_pos_annualized_pct": np.sqrt(daily["rv_pos"]) * ann,
        "rv_neg_annualized_pct": np.sqrt(daily["rv_neg"]) * ann,
        "bpv_annualized_pct": np.sqrt(daily["bpv"].clip(lower=0)) * ann,
        "jump_annualized_pct": np.sqrt(daily["jump"]) * ann,
        "n_minutes": daily["n_minutes"],
    })
    return out


def fetch_intraday_daily_rv(
    symbol: str = "SPY",
    start: date = date(2016, 7, 1),
    end: date | None = None,
) -> pd.Series:
    """Daily realized variance from real 1-minute bars: sum of squared
    log returns within RTH each day, annualized. Index is trading date.
    Kept as a thin wrapper over fetch_intraday_full for backward
    compatibility with Experiment 14's driver."""
    full = fetch_intraday_full(symbol, start, end)
    return full["realized_vol_annualized_pct"].rename("realized_vol_annualized_pct")


def yang_zhang_daily(ohlc: pd.DataFrame, window: int = 1) -> pd.Series:
    """Yang-Zhang range-based daily volatility estimator from OHLC only
    (Yang & Zhang, 2000) -- the fallback when intraday data isn't available.
    `ohlc` must have columns open, high, low, close, indexed by date, with
    each row's `open` interpreted as that session's open relative to the
    PRIOR session's close (overnight jump component)."""
    o, h, l, c = ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"]
    prev_c = c.shift(1)

    log_ho = np.log(h / o)
    log_lo = np.log(l / o)
    log_co = np.log(c / o)
    log_oc = np.log(o / prev_c)
    log_cc = np.log(c / prev_c)

    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)

    k = 0.34 / (1.34 + (window + 1) / (window - 1)) if window > 1 else 0.34 / 1.34
    close_var = log_cc.var()
    open_var = log_oc.var()
    rs_mean = rs.mean()
    yz_var = open_var + k * close_var + (1 - k) * rs_mean
    daily_vol = np.sqrt(max(yz_var, 0.0))
    return pd.Series(np.sqrt(rs.clip(lower=0)) * np.sqrt(TRADING_DAYS_PER_YEAR) * 100, index=ohlc.index, name="yang_zhang_vol_annualized_pct")


if __name__ == "__main__":
    from pipeline.io_utils import atomic_to_csv

    print("Fetching real 1-minute SPY bars 2016-07-01 to present, computing RV/RS+/RS-/BPV/jump...")
    full = fetch_intraday_full()
    print(f"{len(full)} trading days, {full.index.min().date()} to {full.index.max().date()}")
    print(full.describe())

    # Self-check: bipower variation is jump-robust, so it should be <= RV on
    # average (RV = BPV + jump contribution, jump clipped at 0 by construction)
    # -- confirms the estimator isn't producing nonsense before trusting it.
    mean_rv = (full["realized_vol_annualized_pct"] ** 2).mean()
    mean_bpv = (full["bpv_annualized_pct"] ** 2).mean()
    print(f"\nSelf-check: mean RV ({mean_rv:.2f}) should be >= mean BPV ({mean_bpv:.2f}): "
          f"{'PASS' if mean_rv >= mean_bpv else 'FAIL'}")
    print(f"Self-check: RS+ + RS- should ~= RV (both computed from the same minute returns): "
          f"mean RS+={((full['rv_pos_annualized_pct']**2).mean()):.2f}, "
          f"mean RS-={((full['rv_neg_annualized_pct']**2).mean()):.2f}, "
          f"sum={((full['rv_pos_annualized_pct']**2).mean() + (full['rv_neg_annualized_pct']**2).mean()):.2f} "
          f"vs RV={mean_rv:.2f}")

    out = full.reset_index()
    atomic_to_csv(out, "output/data/vol_spy_intraday_full.csv", index=False)
    print("\nSaved to output/data/vol_spy_intraday_full.csv")
