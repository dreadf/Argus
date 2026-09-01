"""
Experiment 24 data build: daily-entry (overlapping) replay of the exact same
put-credit-spread structure as pipeline/backtest/spread_backtest.py --
read-only, never modified; this imports its strike-construction and
option-fetch logic directly rather than duplicating it -- but entering
EVERY trading day instead of only Fridays.

Why: every H4 test so far (Experiments 15/19/20/21/23) used the 125
non-overlapping weekly entries spread_backtest.py deliberately builds,
which keeps every row statistically independent but caps the sample at
~125. This raises the observation count to ~640 over the SAME real
Feb-2024-onward option history (Alpaca's expired-contract history start),
at the honest cost of overlap: a Tuesday entry and a Wednesday entry share
~6 of 7 days of real market exposure, so they are not independent draws.
Every downstream test on this data MUST use Newey-West HAC correction
(pipeline/vol/forecast_eval.py's diebold_mariano, already built and
calibrated) instead of a plain t-test -- this does not increase the amount
of independent market history behind the result, only the observation
count and therefore statistical power, and only up to whatever the true
autocorrelation structure allows.

Scope: only the (distance, width) cells H4 actually trades -- the four
ELIGIBLE_DISTANCES at BASELINE_WIDTH, per pipeline/vol/overlay.py -- not
the full 6x4 sweep, to keep API load proportional to this specific
follow-up question.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd

from pipeline.backtest.spread_backtest import (
    DATA_START,
    UNDERLYING,
    _fetch_bar_closes,
    _load_spy_closes,
    _nearest_trading_day_on_or_before,
    _round_away_from_spot,
)
from pipeline.io_utils import atomic_to_csv
from pipeline.options.contracts import build_occ_symbol
from pipeline.vol.overlay import BASELINE_WIDTH, ELIGIBLE_DISTANCES

OUTPUT_PATH = "output/data/vol_daily_entry_backtest.csv"


def run_daily_backtest(start: date = DATA_START, end: date | None = None) -> pd.DataFrame:
    closes = _load_spy_closes()
    if end is None:
        end = closes.index.max()

    entry_days = [d for d in closes.index if start <= d <= end]
    rows = []
    skipped = 0

    for i, entry in enumerate(entry_days):
        expiry_target = entry + timedelta(days=7)
        expiry = _nearest_trading_day_on_or_before(closes, expiry_target)
        if expiry is None or expiry <= entry:
            skipped += 1
            continue

        spot_entry = closes.loc[entry]
        spy_expiry = closes.loc[expiry]

        strikes_needed: dict[str, bool] = {}
        cells = []
        for distance in ELIGIBLE_DISTANCES:
            short_strike = _round_away_from_spot(spot_entry, distance)
            short_sym = build_occ_symbol(UNDERLYING, expiry, "P", short_strike)
            strikes_needed[short_sym] = True
            long_strike = short_strike - BASELINE_WIDTH
            if long_strike <= 0:
                continue
            long_sym = build_occ_symbol(UNDERLYING, expiry, "P", long_strike)
            strikes_needed[long_sym] = True
            cells.append((distance, short_strike, long_strike, short_sym, long_sym))

        bar_closes = _fetch_bar_closes(list(strikes_needed.keys()), entry)
        time.sleep(0.3)

        for distance, short_strike, long_strike, short_sym, long_sym in cells:
            short_close = bar_closes.get(short_sym)
            long_close = bar_closes.get(long_sym)
            if short_close is None or long_close is None:
                rows.append({
                    "entry": entry, "expiry": expiry, "distance": distance, "width": BASELINE_WIDTH,
                    "spot_entry": spot_entry, "spy_expiry": spy_expiry,
                    "short_strike": short_strike, "long_strike": long_strike,
                    "credit": None, "payout_owed": None, "missing_data": True,
                })
                continue
            credit = short_close - long_close
            intrinsic_short = max(0.0, short_strike - spy_expiry)
            intrinsic_long = max(0.0, long_strike - spy_expiry)
            payout_owed = intrinsic_short - intrinsic_long
            rows.append({
                "entry": entry, "expiry": expiry, "distance": distance, "width": BASELINE_WIDTH,
                "spot_entry": spot_entry, "spy_expiry": spy_expiry,
                "short_strike": short_strike, "long_strike": long_strike,
                "credit": credit, "payout_owed": payout_owed, "missing_data": False,
            })

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(entry_days)} entry days fetched...", flush=True)

    result = pd.DataFrame(rows)
    print(f"{len(entry_days)} candidate entry days, {skipped} skipped (no valid expiry)")
    print(f"{result['entry'].nunique()} entry days with at least one cell attempted")
    return result


if __name__ == "__main__":
    df = run_daily_backtest()
    valid = df[~df["missing_data"]]
    print(f"{len(valid)} valid cells, {int(df['missing_data'].sum())} missing across {len(df)} total rows")

    # Same self-check spread_backtest.py runs: credit (short - long) must be >= 0.
    bad_credit = valid[valid["credit"] < -0.01]
    print(f"Self-check: {len(bad_credit)} cells with negative credit (should be ~0)")

    atomic_to_csv(df, OUTPUT_PATH, index=False)
    print(f"Saved to {OUTPUT_PATH}")
