"""
Replay put credit spreads over real expired SPY option prices.

For each non-overlapping week (Friday entry -> the following Friday's
expiry), across every distance x width combination in the sweep:

  1. Compute the short/long strikes from that Friday's real SPY close,
     rounding away from spot to the nearest $1 (Picker rule #4).
  2. Fetch the real historical closing price of both legs on the entry date
     (Alpaca's expired-contract history goes back to Feb 2024).
  3. Settle at intrinsic value against the real SPY close on the expiry
     Friday -- this is an assumption, not a fact (Part 2's honesty
     correction): no slippage, no early assignment, bar-close entry price.

Non-overlapping by construction: each entry Friday's spread expires before
the next entry Friday opens one, so weeks never share an outcome date.
"""

from __future__ import annotations

import math
import os
import time
from datetime import date, timedelta

import pandas as pd
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionBarsRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv

from pipeline.options.config import DISTANCE_TARGETS, UNDERLYING, WIDTH_TARGETS
from pipeline.options.contracts import build_occ_symbol

load_dotenv()
_option_data_client = OptionHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))

DATA_START = date(2024, 2, 1)  # Alpaca's expired-contract history starts here
MAX_RETRIES = 3


def _load_spy_closes(csv_path: str = "output/data/raw_SPY.csv") -> pd.Series:
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    df["date"] = df["timestamp"].dt.date
    return df.set_index("date")["close"]


def _fridays_between(start: date, end: date) -> list[date]:
    d = start
    while d.weekday() != 4:
        d += timedelta(days=1)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out


def _nearest_trading_day_on_or_before(closes: pd.Series, target: date) -> date | None:
    valid = [d for d in closes.index if d <= target]
    return max(valid) if valid else None


def _round_away_from_spot(spot: float, distance: float) -> int:
    """Nearest $1 strike at or beyond the target distance below spot,
    rounding down (further from spot -> more OTM -> never more risk than the
    evidence gate approved). Picker rule #4."""
    target = spot * (1 - distance)
    return math.floor(target)


def _fetch_bar_closes(symbols: list[str], on_date: date) -> dict[str, float]:
    if not symbols:
        return {}
    request = OptionBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=pd.Timestamp(on_date),
        end=pd.Timestamp(on_date) + pd.Timedelta(days=1),
    )
    for attempt in range(MAX_RETRIES):
        try:
            df = _option_data_client.get_option_bars(request).df
            break
        except Exception as e:
            if "empty" in str(e).lower() or "404" in str(e):
                return {}
            wait = 5 * (attempt + 1)
            print(f"  get_option_bars({on_date}) failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
    else:
        return {}
    if df.empty:
        return {}
    return {sym: float(df.loc[sym].iloc[0]["close"]) for sym in df.index.get_level_values("symbol").unique()}


def run_backtest(
    start: date = DATA_START,
    end: date | None = None,
    distances: tuple[float, ...] = DISTANCE_TARGETS,
    widths: tuple[int, ...] = WIDTH_TARGETS,
) -> pd.DataFrame:
    closes = _load_spy_closes()
    if end is None:
        end = closes.index.max()

    entry_fridays = [f for f in _fridays_between(start, end) if f in closes.index]
    rows = []
    skipped_weeks = 0

    for entry in entry_fridays:
        expiry_target = entry + timedelta(days=7)
        expiry = _nearest_trading_day_on_or_before(closes, expiry_target)
        if expiry is None or expiry <= entry:
            skipped_weeks += 1
            continue

        spot_entry = closes.loc[entry]
        spy_expiry = closes.loc[expiry]

        strikes_needed = {}  # symbol -> (distance, width, leg)
        cells = []
        for distance in distances:
            short_strike = _round_away_from_spot(spot_entry, distance)
            short_sym = build_occ_symbol(UNDERLYING, expiry, "P", short_strike)
            strikes_needed[short_sym] = True
            for width in widths:
                long_strike = short_strike - width
                if long_strike <= 0:
                    continue
                long_sym = build_occ_symbol(UNDERLYING, expiry, "P", long_strike)
                strikes_needed[long_sym] = True
                cells.append((distance, width, short_strike, long_strike, short_sym, long_sym))

        bar_closes = _fetch_bar_closes(list(strikes_needed.keys()), entry)
        time.sleep(0.3)

        for distance, width, short_strike, long_strike, short_sym, long_sym in cells:
            short_close = bar_closes.get(short_sym)
            long_close = bar_closes.get(long_sym)
            if short_close is None or long_close is None:
                rows.append(
                    {
                        "entry": entry, "expiry": expiry, "distance": distance, "width": width,
                        "spot_entry": spot_entry, "spy_expiry": spy_expiry,
                        "short_strike": short_strike, "long_strike": long_strike,
                        "credit": None, "net_pnl": None, "win": None, "missing_data": True,
                    }
                )
                continue

            credit = short_close - long_close
            intrinsic_short = max(0.0, short_strike - spy_expiry)
            intrinsic_long = max(0.0, long_strike - spy_expiry)
            payout_owed = intrinsic_short - intrinsic_long
            net_pnl = credit - payout_owed
            rows.append(
                {
                    "entry": entry, "expiry": expiry, "distance": distance, "width": width,
                    "spot_entry": spot_entry, "spy_expiry": spy_expiry,
                    "short_strike": short_strike, "long_strike": long_strike,
                    "credit": credit, "payout_owed": payout_owed, "net_pnl": net_pnl,
                    "win": payout_owed <= 1e-9, "missing_data": False,
                }
            )

    result = pd.DataFrame(rows)
    print(f"{len(entry_fridays)} candidate entry Fridays, {skipped_weeks} skipped (no valid expiry date)")
    return result


if __name__ == "__main__":
    df = run_backtest()
    valid = df[~df["missing_data"]]
    missing = df[df["missing_data"]]
    print(f"{len(valid)} valid (distance, width) cells, {len(missing)} missing data")

    # Self-check 1: prices rise with strike -- for puts, credit (short - long)
    # must be >= 0 since the short strike is always above the long strike, and
    # a put closer to the money is worth more.
    bad_credit = valid[valid["credit"] < -0.01]
    print(f"Self-check: {len(bad_credit)} cells with negative credit (should be ~0, small noise tolerated)")

    # Self-check 2: real session dates only -- every entry/expiry date used
    # came from raw_SPY.csv's own index, so this is true by construction
    # rather than something to check after the fact.

    # Self-check 3: n_eff per distance should be close to the number of
    # unique entry Fridays (non-overlapping weeks), not overlapping windows.
    n_weeks = valid["entry"].nunique()
    print(f"{n_weeks} unique non-overlapping entry weeks with at least one valid cell")

    df.to_csv("output/data/spread_backtest_results.csv", index=False)
    print("Saved to output/data/spread_backtest_results.csv")

    # Reproduce the flagship 3% cell as a spot check.
    for width in WIDTH_TARGETS:
        cell = valid[(valid["distance"] == 0.03) & (valid["width"] == width)]
        if len(cell) == 0:
            continue
        win_rate = cell["win"].mean()
        avg_credit = cell["credit"].mean()
        print(f"3% distance, ${width} width: n={len(cell)}, win_rate={win_rate:.3f}, avg_credit={avg_credit:.3f}, mean_net_pnl={cell['net_pnl'].mean():.3f}")
