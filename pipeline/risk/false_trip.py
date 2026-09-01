"""
False-trip test (Part 6): replay a guard against real historical outcomes and
count how often it would have blocked a WINNER. >30% is mis-set.

Three guards are testable against Experiment 11's backtest data as it
stands: check_credit_width_ratio (every row already has real credit and
width), check_volatility_regime (SPY's own daily history gives real
yesterday's-move), and check_term_structure (real VIX9D/VIX3M history is
cached and covers the same 126 real weeks, W4/Experiment 12d). The rest of
the guards need data the expired-contract history doesn't carry -- live
open interest, bid-ask spreads, account state, greeks -- and Part 6 already
says so; this file does not pretend otherwise.
"""

from __future__ import annotations

import pandas as pd

from pipeline.data.vix import contango_ratio, load_cached_vix
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
    """W4/Experiment 12d: this guard's RV(10d) leg was retired and
    replaced by check_term_structure (tested separately below) -- only
    the yesterday's-move gap-risk leg remains live, so only that leg is
    replayed here. realized_vol_series stays imported for
    false_trip_rate_term_structure's own use below, not for this."""
    # .shift(1): the live guard computes spy_yesterday_move_pct from
    # closes fetched BEFORE today's decision -- i.e. using the prior
    # trading day's close, never today's own close, which isn't available
    # yet at decision time. Evaluating this replay at the entry date's
    # own close (no shift) was a one-day lookahead.
    daily_move = spy_closes.pct_change().shift(1)

    cell = results_df[(results_df["distance"] == distance) & (results_df["width"] == width) & (~results_df["missing_data"])].copy()
    cell["entry"] = pd.to_datetime(cell["entry"]).dt.date
    winners = cell[cell["win"]]
    if len(winners) == 0:
        return {"distance": distance, "width": width, "n_winners": 0, "blocked": 0, "blocked_pct": 0.0}

    blocked = 0
    for entry_date in winners["entry"]:
        move = daily_move.get(pd.Timestamp(entry_date))
        if move is not None and pd.notna(move) and abs(move) > cfg.SPY_DAILY_MOVE_THRESHOLD:
            blocked += 1
    return {
        "distance": distance, "width": width, "n_winners": len(winners),
        "blocked": blocked, "blocked_pct": blocked / len(winners),
    }


def false_trip_rate_term_structure(results_df: pd.DataFrame, distance: float, width: float, percentile: float = 0.33, min_history: int = 60) -> dict:
    """W4/Experiment 12d: replays check_term_structure against real
    winning weeks, using the SAME walk-forward threshold discipline the
    live guard uses (33rd percentile of contango strictly BEFORE each
    entry date, never a full-sample constant).

    Also returns a per-volatility-regime breakdown (VIX9D quartile at
    entry) WITH bucket counts -- this is the fix for the actual failure
    mode found earlier in this project: a false-trip test that only
    reports one aggregate blocked_pct can pass cleanly while resting on
    almost no observations in the regime that matters (the original
    RV-threshold false-trip test scored 5.7% blocked and looked fine,
    but only 4 of 126 real weeks were ever above its own trigger level --
    the test could not have failed even if the guard were wrong).
    Printing n per bucket here makes that kind of underpowered pass
    visible instead of hidden inside an average.
    """
    v9 = load_cached_vix("VIX9D") / 100.0
    v3m = load_cached_vix("VIX3M") / 100.0
    ratio = contango_ratio(v9, v3m)

    cell = results_df[(results_df["distance"] == distance) & (results_df["width"] == width) & (~results_df["missing_data"])].copy()
    cell["entry"] = pd.to_datetime(cell["entry"])
    cell = cell.merge(v9.rename("vix9d"), left_on="entry", right_index=True, how="left")
    winners = cell[cell["win"]].dropna(subset=["vix9d"]).copy()
    if len(winners) == 0:
        return {"distance": distance, "width": width, "n_winners": 0, "blocked": 0, "blocked_pct": 0.0, "by_regime": pd.DataFrame()}

    def _blocked(entry_date) -> bool | None:
        prior = ratio[ratio.index < entry_date]
        if len(prior) < min_history:
            return None  # not enough history to have a threshold yet -- excluded, not counted as blocked or clear
        today_ratio = ratio.get(entry_date)
        if today_ratio is None or pd.isna(today_ratio):
            return None
        threshold = prior.quantile(percentile)
        return today_ratio < threshold

    winners["blocked"] = winners["entry"].apply(_blocked)
    testable = winners.dropna(subset=["blocked"])
    winners_all = winners  # kept for the total count reported even if some are untestable (insufficient trailing history)

    n_winners = len(testable)
    n_blocked = int(testable["blocked"].sum())

    testable = testable.copy()
    testable["regime"] = pd.qcut(testable["vix9d"], 4, labels=["calmest", "calm", "active", "most volatile"], duplicates="drop")
    by_regime = testable.groupby("regime", observed=True).agg(n=("blocked", "size"), blocked=("blocked", "sum"))
    by_regime["blocked_pct"] = by_regime["blocked"] / by_regime["n"]

    return {
        "distance": distance, "width": width,
        "n_winners": n_winners, "n_winners_total_incl_untestable": len(winners_all),
        "blocked": n_blocked, "blocked_pct": n_blocked / n_winners if n_winners else 0.0,
        "by_regime": by_regime,
    }


if __name__ == "__main__":
    from pipeline.backtest.spread_backtest import _load_spy_closes
    from pipeline.io_utils import coerce_win_column

    results = coerce_win_column(pd.read_csv("output/data/spread_backtest_results.csv"))
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

    print("\nGuard #12 (volatility regime, RV leg RETIRED W4 -- yesterday's-move leg only) false-trip rate:")
    max_blocked_pct = 0.0
    for distance, width in survivors:
        r = false_trip_rate_vol_regime(results, spy_closes, distance, width)
        max_blocked_pct = max(max_blocked_pct, r["blocked_pct"])
        print(f"  {distance:.0%} / ${width:.0f}: {r['blocked']}/{r['n_winners']} winners blocked ({r['blocked_pct']:.1%})")
    status = "PASS" if max_blocked_pct <= cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT else "FAIL (mis-set, needs loosening)"
    print(f"  -> {status} (bar: <={cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT:.0%})")

    print("\ncheck_term_structure (W4, new guard) false-trip rate, walk-forward threshold, "
          "SPLIT BY VOLATILITY REGIME with bucket counts printed:")
    print("(this split is the actual point -- the guard it replaces passed its false-trip test at an aggregate\n"
          " 5.7% blocked while resting on only 4 of 126 weeks ever crossing its trigger; printing n per bucket\n"
          " here means that specific failure mode can't hide inside an average again)")
    max_blocked_pct = 0.0
    for distance, width in survivors:
        r = false_trip_rate_term_structure(results, distance, width)
        max_blocked_pct = max(max_blocked_pct, r["blocked_pct"])
        untestable = r["n_winners_total_incl_untestable"] - r["n_winners"]
        print(f"\n  {distance:.0%} / ${width:.0f}: {r['blocked']}/{r['n_winners']} winners blocked "
              f"({r['blocked_pct']:.1%})" + (f", {untestable} excluded (insufficient trailing history)" if untestable else ""))
        if not r["by_regime"].empty:
            print(f"    {r['by_regime'].round(3).to_string()}")
    status = "PASS" if max_blocked_pct <= cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT else "FAIL (mis-set, needs loosening)"
    print(f"\n  -> {status} (bar: <={cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT:.0%})")

    print(
        "\nNOT testable against this backtest (no historical OI/spread/greeks/account-state data): "
        "market-open, data-sanity, liquidity, net-delta, per-trade cap, crash-day budget, one-leg emergency, "
        "drawdown soft/hard (needs a simulated running account, not built). Kept on structural grounds per Part 9B."
    )
