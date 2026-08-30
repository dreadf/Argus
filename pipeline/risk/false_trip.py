"""
False-trip test (Part 6): replay a guard against real historical outcomes and
count how often it would have blocked a WINNER. >30% is mis-set.

Only two guards are actually testable against Experiment 11's backtest data
as it stands: check_credit_width_ratio (every row already has real credit
and width) and check_volatility_regime (SPY's own daily history gives real
RV(10d) and yesterday's move on every entry date). The rest of the 14 guards
need data the expired-contract history doesn't carry -- live open interest,
bid-ask spreads, account state, greeks -- and Part 6 already says so; this
file does not pretend otherwise.
"""

from __future__ import annotations

import pandas as pd

from pipeline.options.vol import realized_vol_series
from pipeline.risk import options_config as cfg


def false_trip_rate_credit_width(results_df: pd.DataFrame, distance: float, width: float) -> dict:
    cell = results_df[(results_df["distance"] == distance) & (results_df["width"] == width) & (~results_df["missing_data"])]
    winners = cell[cell["win"]]
    if len(winners) == 0:
        return {"distance": distance, "width": width, "n_winners": 0, "blocked": 0, "blocked_pct": 0.0}
    ratio = winners["credit"] / winners["width"]
    blocked = ((ratio < cfg.CREDIT_WIDTH_MIN) | (ratio > cfg.CREDIT_WIDTH_MAX)).sum()
    return {
        "distance": distance, "width": width, "n_winners": len(winners),
        "blocked": int(blocked), "blocked_pct": blocked / len(winners),
    }


def false_trip_rate_vol_regime(results_df: pd.DataFrame, spy_closes: pd.Series, distance: float, width: float) -> dict:
    rv_series = realized_vol_series(spy_closes, window=10)
    daily_move = spy_closes.pct_change()

    cell = results_df[(results_df["distance"] == distance) & (results_df["width"] == width) & (~results_df["missing_data"])].copy()
    cell["entry"] = pd.to_datetime(cell["entry"]).dt.date
    winners = cell[cell["win"]]
    if len(winners) == 0:
        return {"distance": distance, "width": width, "n_winners": 0, "blocked": 0, "blocked_pct": 0.0}

    blocked = 0
    for entry_date in winners["entry"]:
        rv = rv_series.get(pd.Timestamp(entry_date))
        move = daily_move.get(pd.Timestamp(entry_date))
        if (rv is not None and pd.notna(rv) and rv > cfg.VOL_REGIME_RV_THRESHOLD) or (
            move is not None and pd.notna(move) and abs(move) > cfg.SPY_DAILY_MOVE_THRESHOLD
        ):
            blocked += 1
    return {
        "distance": distance, "width": width, "n_winners": len(winners),
        "blocked": blocked, "blocked_pct": blocked / len(winners),
    }


if __name__ == "__main__":
    from pipeline.backtest.spread_backtest import _load_spy_closes

    results = pd.read_csv("output/data/spread_backtest_results.csv")
    results["win"] = results["win"].map({"True": True, "False": False, True: True, False: False})
    spy_closes = _load_spy_closes()
    spy_closes.index = pd.to_datetime(list(spy_closes.index))

    survivors = [(0.03, 1.0), (0.03, 2.0), (0.03, 5.0)]

    print("Guard #8 (credit/width band) false-trip rate on evidence-gate survivors:")
    max_blocked_pct = 0.0
    for distance, width in survivors:
        r = false_trip_rate_credit_width(results, distance, width)
        max_blocked_pct = max(max_blocked_pct, r["blocked_pct"])
        print(f"  {distance:.0%} / ${width:.0f}: {r['blocked']}/{r['n_winners']} winners blocked ({r['blocked_pct']:.1%})")
    status = "PASS" if max_blocked_pct <= cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT else "FAIL (mis-set, needs loosening)"
    print(f"  -> {status} (bar: <={cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT:.0%})")

    print("\nGuard #12 (volatility regime) false-trip rate on evidence-gate survivors:")
    max_blocked_pct = 0.0
    for distance, width in survivors:
        r = false_trip_rate_vol_regime(results, spy_closes, distance, width)
        max_blocked_pct = max(max_blocked_pct, r["blocked_pct"])
        print(f"  {distance:.0%} / ${width:.0f}: {r['blocked']}/{r['n_winners']} winners blocked ({r['blocked_pct']:.1%})")
    status = "PASS" if max_blocked_pct <= cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT else "FAIL (mis-set, needs loosening)"
    print(f"  -> {status} (bar: <={cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT:.0%})")

    print(
        "\nNOT testable against this backtest (no historical OI/spread/greeks/account-state data): "
        "market-open, data-sanity, liquidity, net-delta, per-trade cap, crash-day budget, one-leg emergency, "
        "drawdown soft/hard (needs a simulated running account, not built). Kept on structural grounds per Part 9B."
    )
