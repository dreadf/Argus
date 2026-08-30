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
    highest cushion (not the highest P&L). Multiple cells can clear the bar
    at once (Experiment 11: three did, at 3% distance), and Part 9B is
    explicit that picking whichever looks best in hindsight would repeat the
    exact mistake the evidence gate exists to prevent. Cushion is the
    statistic the gate itself is built on, so it is the only tie-break
    decided in advance rather than after seeing which one paid the most.
    """
    survivors = tradable_distances(gate_df)
    if survivors.empty:
        return None
    best = survivors.loc[survivors["cushion_se"].idxmax()]
    return {"distance": float(best["distance"]), "width": float(best["width"]), "cushion_se": float(best["cushion_se"])}


def _nearest_listed_strike_at_or_beyond(strikes: pd.Series, target: float) -> float | None:
    """Rule #4: nearest listed strike at or beyond the target distance below
    spot -- i.e. the largest listed strike that does not exceed target.
    Rounding away from spot means MORE OTM than the raw target, never less."""
    candidates = strikes[strikes <= target]
    if candidates.empty:
        return None
    return float(candidates.max())


def choose_strikes(chain_df: pd.DataFrame, spot: float, distance: float, width: float) -> dict | None:
    listed = chain_df["strike"].unique()
    listed = pd.Series(listed)
    target_short = spot * (1 - distance)
    short_strike = _nearest_listed_strike_at_or_beyond(listed, target_short)
    if short_strike is None:
        return None
    target_long = short_strike - width
    long_strike = _nearest_listed_strike_at_or_beyond(listed, target_long)
    if long_strike is None or long_strike >= short_strike:
        return None
    return {"short_strike": short_strike, "long_strike": long_strike}


def choose_expiry(today: date, chain_df: pd.DataFrame) -> date | None:
    """Rule #6: from the expiries that actually exist in the fetched chain
    (not just the theoretical Mon/Wed/Fri calendar), prefer the one closest
    to 7 DTE -- the shortest end of the window, matching the entry/expiry
    cadence the backtest actually tested."""
    listed_expiries = sorted(chain_df["expiry"].unique())
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
    else:
        print("\nNo trade selected today (empty gate, no listed strikes, or budget too small).")
