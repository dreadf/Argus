"""
The Picker: the 9 fixed rules from OPTIONS_SYSTEM_PLAN.md Part 6 that choose
which spread to sell. No AI, nothing here reads an LLM output. Every number
comes from the evidence gate or account state, never a guess made here.

Emits a proposal dict shaped exactly for pipeline.risk.guards.run_all_guards,
so the next step after selection is always: run every guard before this ever
reaches a broker.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from pipeline.backtest.evidence_gate import tradable_distances
from pipeline.options import config as opt_cfg
from pipeline.options.contracts import build_occ_symbol, expiries_in_window
from pipeline.risk import options_config as risk_cfg


def choose_distance_width(gate_df: pd.DataFrame) -> dict | None:
    """Rule #3/#5: among cells clearing the 2-SE bar, pick the one with the
    highest cost-adjusted mean P&L (T2 correction; was cushion_se).

    The original reasoning for tie-breaking on cushion_se was sound in
    spirit -- decide the rule in advance rather than pick whichever cell
    looks best after seeing the results -- but cushion_se turned out to be
    anti-correlated with cost robustness: it is highest exactly where
    credit is thinnest (3%/$1's cushion of 3.28 SE was the best in the
    table, but its mean P&L falls from $0.052/share to -$0.048/share at a
    pre-committed 2c/leg slippage assumption, and its short strike was
    blocked live on real open interest of 22 against the 500 minimum).
    mean_net_pnl already has the same "decided in advance" property --
    evidence_gate.py bakes in DEFAULT_SLIPPAGE_PER_SHARE before this
    function ever sees the table, so this is not picking whichever paid
    the most in hindsight, it is picking the cell whose cushion survives
    a cost assumption fixed before the comparison.
    """
    survivors = tradable_distances(gate_df)
    if survivors.empty:
        return None
    best = survivors.loc[survivors["mean_net_pnl"].idxmax()]
    return {
        "distance": float(best["distance"]),
        "width": float(best["width"]),
        "cushion_se": float(best["cushion_se"]),
        "mean_net_pnl": float(best["mean_net_pnl"]),
    }


def _nearest_listed_strike_at_or_beyond(strikes: pd.Series, target: float) -> float | None:
    """Rule #4: nearest listed strike at or beyond the target distance below
    spot -- i.e. the largest listed strike that does not exceed target.
    Rounding away from spot means MORE OTM than the raw target, never less."""
    candidates = strikes[strikes <= target]
    if candidates.empty:
        return None
    return float(candidates.max())


def _nearest_listed_strike_at_or_above(strikes: pd.Series, target: float) -> float | None:
    """For the long (protective) leg only: the smallest listed strike that
    does not go below target, i.e. never further from the short strike than
    the configured width. Reusing _nearest_listed_strike_at_or_beyond here
    (as an earlier version did) rounds the WRONG way for this leg -- it
    picks the largest strike <= target, which on a grid that doesn't line
    up exactly only ever widens the realized spread beyond what the
    evidence gate measured, silently breaking the "only trade what was
    measured" guarantee this system is otherwise built on."""
    candidates = strikes[strikes >= target]
    if candidates.empty:
        return None
    return float(candidates.min())


def choose_strikes(chain_df: pd.DataFrame, spot: float, distance: float, width: float) -> dict | None:
    """Rule #4. The short leg's target is rounded down to the nearest
    LIQUID_STRIKE_INCREMENT before searching the listed chain -- SPY open
    interest concentrates on $5/$10 strikes, and a raw $1-odd target
    (e.g. $746 at 3% below a $769 spot) can pass the round-trip build but
    fail live on real depth (confirmed: OI 22 against the 500 minimum on
    exactly that strike). Rounding down moves the target FURTHER from spot,
    so this can only buy more distance than the evidence gate measured,
    never less."""
    listed = chain_df["strike"].unique()
    listed = pd.Series(listed)
    target_short = spot * (1 - distance)
    target_short = math.floor(target_short / opt_cfg.LIQUID_STRIKE_INCREMENT) * opt_cfg.LIQUID_STRIKE_INCREMENT
    short_strike = _nearest_listed_strike_at_or_beyond(listed, target_short)
    if short_strike is None:
        return None
    target_long = short_strike - width
    long_strike = _nearest_listed_strike_at_or_above(listed, target_long)
    if long_strike is None or long_strike >= short_strike:
        return None
    realized_distance = (spot - short_strike) / spot
    return {"short_strike": short_strike, "long_strike": long_strike, "realized_distance": realized_distance}


def choose_expiry(today: date, chain_df: pd.DataFrame) -> date | None:
    """Rule #6: from the expiries that actually exist in the fetched chain
    (not just the theoretical Mon/Wed/Fri calendar), prefer the one closest
    to 7 DTE -- the shortest end of the window, matching the entry/expiry
    cadence the backtest actually tested.

    "Matching the cadence" means FRIDAY only -- spread_backtest.py's
    _fridays_between generates exclusively Friday entry/expiry dates, so
    every win rate, cushion, and credit statistic in the evidence gate was
    measured on Friday-to-Friday cycles alone. An earlier version of this
    function picked the nearest-DTE listed expiry with no weekday filter,
    which can silently select a Wednesday expiry the backtest never tested
    -- confirmed live (2026-09-01): the untested Wed 2026-09-09 expiry's 3%
    strike quoted OI=386 (blocks the 500 minimum) while the SAME strike on
    the tested Fri 2026-09-11 expiry quoted OI=35,231 (two orders of
    magnitude more, comfortably passes). Restricting to Friday isn't just
    a liquidity fix, it is what "trade what was measured" requires here."""
    listed_expiries = sorted(
        e for e in chain_df["expiry"].unique()
        if (e - today).days >= 0 and e.weekday() == 4  # Friday only -- matches _fridays_between
    )
    if not listed_expiries:
        return None
    return min(listed_expiries, key=lambda e: (e - today).days)


def size_contracts(current_equity: float, open_positions: list[dict], max_loss_per_contract: float) -> int:
    """Rule #7: the budget formula from Part 6 -- always floor, never round,
    and size against what's left in the crash-day budget, not a flat
    per-bet allowance."""
    if max_loss_per_contract <= 0:
        return 0
    per_trade_cap = current_equity * risk_cfg.PER_TRADE_CAP_PCT
    crash_day_budget = current_equity * risk_cfg.CRASH_DAY_BUDGET_PCT
    committed = sum(p.get("max_loss_total", 0.0) for p in open_positions)
    budget_left = crash_day_budget - committed
    allowance = min(per_trade_cap, budget_left)
    if allowance <= 0:
        return 0
    return math.floor(allowance / max_loss_per_contract)


def select_spread(
    chain_df: pd.DataFrame,
    spot: float,
    gate_df: pd.DataFrame,
    account_state: dict,
    today: date | None = None,
) -> dict | None:
    """Runs Picker rules 1-7 end to end. Rules #8 (limit at mid) and #9 (fill
    discipline) are execution-time concerns and belong to orders.py (Build
    Step 9); this function's output includes the mid price the LIMIT order
    should use, but does not place anything.

    Returns None whenever no valid trade exists -- an empty evidence gate, no
    matching listed strikes, no viable expiry, or a budget too small for even
    one contract are all legitimate "don't trade today" outcomes, not errors.
    """
    if today is None:
        today = date.today()

    choice = choose_distance_width(gate_df)
    if choice is None:
        return None  # Guard #3 restates this, but the Picker itself also refuses here.

    expiry = choose_expiry(today, chain_df)
    if expiry is None:
        return None

    chain_at_expiry = chain_df[chain_df["expiry"] == expiry]
    strikes = choose_strikes(chain_at_expiry, spot, choice["distance"], choice["width"])
    if strikes is None:
        return None

    short_row = chain_at_expiry[chain_at_expiry["strike"] == strikes["short_strike"]]
    long_row = chain_at_expiry[chain_at_expiry["strike"] == strikes["long_strike"]]
    if short_row.empty or long_row.empty:
        return None
    short_row, long_row = short_row.iloc[0], long_row.iloc[0]

    if pd.isna(short_row["mid"]) or pd.isna(long_row["mid"]):
        return None  # Guard #2 (data sanity) would also catch this.

    credit_per_share = short_row["mid"] - long_row["mid"]
    credit_per_contract = credit_per_share * 100
    width_dollars = (strikes["short_strike"] - strikes["long_strike"]) * 100
    max_loss_per_contract = width_dollars - credit_per_contract

    contracts = size_contracts(account_state.get("current_equity", 0.0), account_state.get("open_positions", []), max_loss_per_contract)
    if contracts < 1:
        return None

    short_delta = short_row.get("delta")
    long_delta = long_row.get("delta")
    net_delta_per_share = None
    if short_delta is not None and long_delta is not None and not pd.isna(short_delta) and not pd.isna(long_delta):
        # We are short the short leg (delta flips sign) and long the long leg (delta as-is).
        net_delta_per_share = -short_delta + long_delta

    dte = (expiry - today).days
    would_hold_into_expiry = False  # Picker only ever proposes fresh entries; monitor.py owns the day-before-expiry exit.

    def _spread_pct(row) -> float | None:
        if pd.isna(row["bid"]) or pd.isna(row["ask"]) or not row["mid"] or row["mid"] <= 0:
            return None
        return (row["ask"] - row["bid"]) / row["mid"]

    return {
        "underlying": opt_cfg.UNDERLYING,
        "short_symbol": build_occ_symbol(opt_cfg.UNDERLYING, expiry, "P", strikes["short_strike"]),
        "long_symbol": build_occ_symbol(opt_cfg.UNDERLYING, expiry, "P", strikes["long_strike"]),
        "short_strike": strikes["short_strike"],
        "long_strike": strikes["long_strike"],
        "expiry": expiry,
        "dte": dte,
        "distance": choice["distance"],
        "realized_distance": strikes["realized_distance"],  # after Rule #4's $5-increment rounding; may exceed "distance"
        "width_dollars": width_dollars,
        "credit_per_contract": credit_per_contract,
        "limit_price_per_share": credit_per_share,  # Rule #8: LIMIT at mid.
        "contracts": contracts,
        "max_loss_per_contract": max_loss_per_contract,
        "max_loss_total": max_loss_per_contract * contracts,
        "would_hold_into_expiry_day": would_hold_into_expiry,
        "iv_missing": pd.isna(short_row.get("iv")),
        "open_interest_short": int(short_row["open_interest"]),
        "open_interest_long": int(long_row["open_interest"]),
        "spread_pct_short": _spread_pct(short_row),
        "spread_pct_long": _spread_pct(long_row),
        "quoted_short": not pd.isna(short_row["bid"]) and not pd.isna(short_row["ask"]),
        "quoted_long": not pd.isna(long_row["bid"]) and not pd.isna(long_row["ask"]),
        "net_delta_share_equiv": (net_delta_per_share * 100 * contracts) if net_delta_per_share is not None else 0.0,
        "cushion_se": choice["cushion_se"],
    }


if __name__ == "__main__":
    import os

    from pipeline.options.chain import fetch_chain, get_spot

    gate_path = "output/data/evidence_gate_results.csv"
    if not os.path.exists(gate_path):
        raise SystemExit("Run pipeline.backtest.evidence_gate first to produce evidence_gate_results.csv")
    gate_df = pd.read_csv(gate_path)

    choice = choose_distance_width(gate_df)
    print("Chosen (distance, width) by highest cushion:", choice)
    assert choice is not None and choice["distance"] == 0.03, choice

    today = date.today()
    exps = expiries_in_window(today, risk_cfg.MIN_DTE, risk_cfg.MAX_DTE)
    spot = get_spot()
    chain_df = fetch_chain(exps, spot=spot)
    print(f"Fetched {len(chain_df)} contracts across {len(exps)} candidate expiries")

    fake_state = {"current_equity": 100_000.0, "open_positions": []}
    proposal = select_spread(chain_df, spot, gate_df, fake_state, today=today)
    print("\nSelected proposal:")
    for k, v in (proposal or {}).items():
        print(f"  {k}: {v}")

    if proposal is not None:
        from pipeline.risk.guards import run_all_guards

        fake_state_full = {
            "market_open": True,
            "data_stale": False,
            "spot_price": spot,
            "chain_spot_price": spot,
            "evidence_gate_passed": True,
            "current_equity": 100_000.0,
            "peak_equity": 100_000.0,
            "open_positions": [],
            "rv_10d": 0.10,
            "spy_yesterday_move_pct": 0.005,
        }
        result = run_all_guards(fake_state_full, proposal)
        print(f"\nGuards: {'PASS' if result['passed'] else 'BLOCKED'}")
        for f in result["failed"]:
            print(f"  FAILED: {f['guard']}: {f['reason']}")

        # Regression lock: choose_expiry must never propose a non-Friday
        # expiry -- the backtest's _fridays_between tested Friday cycles
        # exclusively, and a Wednesday expiry blocked live on real OI 386
        # vs the identical Friday strike's 35,231 (2026-09-01).
        assert proposal["expiry"].weekday() == 4, f"expiry {proposal['expiry']} is not a Friday"
        print(f"Expiry-weekday regression check: {proposal['expiry']} is a Friday -- PASS")
    else:
        print("\nNo trade selected today (empty gate, no listed strikes, or budget too small).")
