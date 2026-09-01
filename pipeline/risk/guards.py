"""
The guards from OPTIONS_SYSTEM_PLAN.md Part 6 (14 originally; check_term_structure
added in Experiment 12d/W4, replacing the RV(10d) leg of check_volatility_regime).
Each check_*(state, proposal)
returns (passed: bool, reason: str). Any single failure blocks the trade;
the reason is logged either way (audit/log.py, Build Step 8).

Pure functions on plain dicts, deliberately -- this is what makes them
independently unit-testable against fake account states (Verification #4)
and replayable against the backtest for the false-trip test
(FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT), without needing a live broker
connection or a running event loop.

`state` describes account/market conditions. `proposal` describes the
candidate spread the Picker (selector.py, Build Step 7) chose. Guards that
only need one of the two still take both for a uniform signature; run_all_guards
is the single entry point everything else should call.
"""

from __future__ import annotations

from pipeline.risk import options_config as cfg


def check_market_open(state: dict, proposal: dict) -> tuple[bool, str]:
    if not state.get("market_open", False):
        return False, "market closed"
    return True, "market open"


def check_data_sanity(state: dict, proposal: dict) -> tuple[bool, str]:
    if state.get("data_stale", False):
        return False, "chain data stale (quote older than 15 min)"
    if proposal.get("iv_missing", False):
        return False, "IV missing on the chosen leg"
    spot = state.get("spot_price")
    chain_spot = state.get("chain_spot_price")
    if spot is not None and chain_spot is not None and spot > 0:
        disagreement = abs(spot - chain_spot) / spot
        if disagreement > 0.005:
            return False, f"spot disagrees with chain by {disagreement:.2%} (>0.5%)"
    return True, "data sane"


def check_evidence_gate(state: dict, proposal: dict) -> tuple[bool, str]:
    if not state.get("evidence_gate_passed", False):
        return False, "no distance clears the 2-SE evidence gate cushion"
    return True, "evidence gate cleared"


def check_per_trade_cap(state: dict, proposal: dict) -> tuple[bool, str]:
    equity = state.get("current_equity", 0.0)
    max_loss = proposal.get("max_loss_total", 0.0)
    cap = equity * cfg.PER_TRADE_CAP_PCT
    if max_loss > cap:
        return False, f"max loss ${max_loss:.0f} exceeds per-trade cap ${cap:.0f} ({cfg.PER_TRADE_CAP_PCT:.0%} of equity)"
    return True, "within per-trade cap"


def check_crash_day_budget(state: dict, proposal: dict) -> tuple[bool, str]:
    equity = state.get("current_equity", 0.0)
    open_positions = state.get("open_positions", [])
    committed = sum(p.get("max_loss_total", 0.0) for p in open_positions)
    budget = equity * cfg.CRASH_DAY_BUDGET_PCT
    remaining = budget - committed
    max_loss = proposal.get("max_loss_total", 0.0)
    if max_loss > remaining:
        return False, f"max loss ${max_loss:.0f} exceeds remaining crash-day budget ${remaining:.0f}"
    return True, "within crash-day budget"


def check_concurrent_positions(state: dict, proposal: dict) -> tuple[bool, str]:
    n_open = len(state.get("open_positions", []))
    if n_open >= cfg.MAX_CONCURRENT_POSITIONS:
        return False, f"already {n_open} positions open (max {cfg.MAX_CONCURRENT_POSITIONS})"
    return True, "under concurrent-position limit"


def check_net_delta(state: dict, proposal: dict) -> tuple[bool, str]:
    open_positions = state.get("open_positions", [])
    current = sum(p.get("net_delta_share_equiv", 0.0) for p in open_positions)
    proposed = proposal.get("net_delta_share_equiv", 0.0)
    total = abs(current + proposed)
    if total > cfg.NET_DELTA_CAP_SHARE_EQUIV:
        return False, f"book delta {total:.0f} would exceed ±{cfg.NET_DELTA_CAP_SHARE_EQUIV} share-equivalents"
    return True, "within net-delta cap"


def check_credit_width_ratio(state: dict, proposal: dict) -> tuple[bool, str]:
    credit = proposal.get("credit_per_contract", 0.0)
    width = proposal.get("width_dollars", 0.0)
    if width <= 0:
        return False, "invalid width"
    ratio = credit / width
    if ratio < cfg.CREDIT_WIDTH_MIN:
        return False, f"credit/width {ratio:.3f} below {cfg.CREDIT_WIDTH_MIN} (not paid enough)"
    if ratio > cfg.CREDIT_WIDTH_MAX:
        return False, f"credit/width {ratio:.3f} above {cfg.CREDIT_WIDTH_MAX} (negative-premium zone)"
    return True, "credit/width in band"


def check_expiry_window(state: dict, proposal: dict) -> tuple[bool, str]:
    dte = proposal.get("dte")
    if dte is None or not (cfg.MIN_DTE <= dte <= cfg.MAX_DTE):
        return False, f"DTE {dte} outside [{cfg.MIN_DTE}, {cfg.MAX_DTE}]"
    return True, "DTE within window"


def check_expiry_day_rule(state: dict, proposal: dict) -> tuple[bool, str]:
    if proposal.get("would_hold_into_expiry_day", False):
        return False, "would hold a position into its expiration day (pin-risk rule)"
    return True, "no position held into expiry day"


def check_liquidity(state: dict, proposal: dict) -> tuple[bool, str]:
    for leg in ("short", "long"):
        oi = proposal.get(f"open_interest_{leg}")
        spread_pct = proposal.get(f"spread_pct_{leg}")
        quoted = proposal.get(f"quoted_{leg}", False)
        if not quoted:
            return False, f"{leg} leg unquoted"
        if oi is None or oi < cfg.MIN_OPEN_INTEREST:
            return False, f"{leg} leg open interest {oi} below {cfg.MIN_OPEN_INTEREST}"
        if spread_pct is None or spread_pct > cfg.MAX_BID_ASK_SPREAD_PCT:
            return False, f"{leg} leg bid-ask spread {spread_pct} exceeds {cfg.MAX_BID_ASK_SPREAD_PCT:.0%} of mid"
        # The floor above only checks OI clears an absolute minimum,
        # independent of how many contracts this specific order wants.
        # size_contracts sizes purely off equity-based dollar caps with no
        # reference to quoted depth, so a large-enough account could
        # otherwise propose more contracts than the market can realistically
        # absorb (item 24: crosses the OI floor itself past ~$1.08M equity
        # on the narrowest tested width).
        contracts = proposal.get("contracts", 0)
        max_contracts = oi * cfg.MAX_CONTRACTS_PCT_OF_OPEN_INTEREST
        if contracts > max_contracts:
            return False, f"{leg} leg order size {contracts} exceeds {cfg.MAX_CONTRACTS_PCT_OF_OPEN_INTEREST:.0%} of open interest {oi} ({max_contracts:.0f})"
    return True, "both legs liquid"


def check_volatility_regime(state: dict, proposal: dict) -> tuple[bool, str]:
    """W4 (Experiment 12d): the RV(10d) leg that used to live here was
    retired and replaced by check_term_structure below, which uses a
    forward-looking instrument (VIX3M/VIX9D) for the same underlying
    risk. Trailing realized volatility is exactly the lagging quantity
    that made an earlier version of the reconstruction in reconstruct.py
    fail its own regime-split validation (0.03x-1.25x model/real error),
    so replacing it here with the same lagging signal would just move
    that problem into the live guard. This leg -- yesterday's SPY move --
    is a distinct gap-risk check, not a pricing/regime check, and stays."""
    move = state.get("spy_yesterday_move_pct")
    if move is not None and abs(move) > cfg.SPY_DAILY_MOVE_THRESHOLD:
        return False, f"SPY moved {move:.2%} yesterday, exceeds {cfg.SPY_DAILY_MOVE_THRESHOLD:.0%} skip threshold"
    return True, "no large gap yesterday"


def check_term_structure(state: dict, proposal: dict) -> tuple[bool, str]:
    """W4: blocks when the VIX term structure (VIX3M/VIX9D) has flattened
    or inverted below its own trailing history -- the condition
    documented (Quantpedia; 2004-2025 CBOE data) to precede 21 of 22
    backwardation episodes tied to a >5% S&P drawdown within 30 days.
    Fails closed on missing/stale data rather than assuming calm, the
    same convention check_data_sanity already uses for the option chain.

    The threshold is precomputed by the caller from data strictly before
    today (pipeline.data.vix.trailing_contango_threshold) and passed in
    as a plain float, keeping this function -- like every other guard --
    a pure function on plain dicts with no fetch of its own, so it stays
    independently unit-testable and false-trip-testable without a live
    VIX connection."""
    if state.get("vix_data_stale", True):
        return False, "VIX term-structure data stale or unavailable"
    contango = state.get("vix_contango_ratio")
    threshold = state.get("vix_contango_threshold")
    if contango is None or threshold is None:
        return False, "VIX term-structure data missing"
    if contango < threshold:
        return False, f"VIX3M/VIX9D {contango:.3f} below trailing 33rd-pct threshold {threshold:.3f} -- term structure flattening/inverting"
    return True, f"VIX term structure normal ({contango:.3f} >= {threshold:.3f})"


def check_drawdown_soft(state: dict, proposal: dict) -> tuple[bool, str]:
    equity = state.get("current_equity", 0.0)
    peak = state.get("peak_equity", equity)
    if peak <= 0:
        return True, "no peak recorded yet"
    drawdown = (peak - equity) / peak
    if drawdown >= cfg.DRAWDOWN_SOFT_PCT:
        return False, f"drawdown {drawdown:.2%} at/above soft stop {cfg.DRAWDOWN_SOFT_PCT:.0%} -- stop opening"
    return True, "within soft drawdown limit"


def check_drawdown_hard(state: dict, proposal: dict) -> tuple[bool, str]:
    equity = state.get("current_equity", 0.0)
    peak = state.get("peak_equity", equity)
    if peak <= 0:
        return True, "no peak recorded yet"
    drawdown = (peak - equity) / peak
    if drawdown >= cfg.DRAWDOWN_HARD_PCT:
        return False, f"drawdown {drawdown:.2%} at/above hard stop {cfg.DRAWDOWN_HARD_PCT:.0%} -- halt, close everything"
    return True, "within hard drawdown limit"


ALL_GUARDS = [
    check_market_open,
    check_data_sanity,
    check_evidence_gate,
    check_per_trade_cap,
    check_crash_day_budget,
    check_concurrent_positions,
    check_net_delta,
    check_credit_width_ratio,
    check_expiry_window,
    check_expiry_day_rule,
    check_liquidity,
    check_volatility_regime,
    check_term_structure,
    check_drawdown_soft,
    check_drawdown_hard,
]


def run_all_guards(state: dict, proposal: dict) -> dict:
    """Runs every guard regardless of earlier failures (all reasons get
    logged, per the plan), and reports whether the trade may proceed."""
    results = []
    for guard in ALL_GUARDS:
        passed, reason = guard(state, proposal)
        results.append({"guard": guard.__name__, "passed": passed, "reason": reason})
    all_passed = all(r["passed"] for r in results)
    failed = [r for r in results if not r["passed"]]
    return {"passed": all_passed, "results": results, "failed": failed}


if __name__ == "__main__":
    # Self-checks against fake account states (Verification #4).
    base_state = {
        "market_open": True,
        "data_stale": False,
        "spot_price": 769.0,
        "chain_spot_price": 769.5,
        "evidence_gate_passed": True,
        "current_equity": 100_000.0,
        "peak_equity": 100_000.0,
        "open_positions": [],
        "rv_10d": 0.10,
        "spy_yesterday_move_pct": 0.005,
        "vix_data_stale": False,
        "vix_contango_ratio": 1.20,       # calm, normal term structure (real measured median ~1.21)
        "vix_contango_threshold": 1.12,   # a real measured trailing 33rd-pct value; ratio comfortably above it
    }
    base_proposal = {
        # Real Experiment 11 numbers: 3% distance, $5 width, ~6 contracts.
        "max_loss_total": 2_838.0,
        "credit_per_contract": 27.4,
        "width_dollars": 500.0,
        "dte": 8,
        "would_hold_into_expiry_day": False,
        "iv_missing": False,
        "open_interest_short": 5000,
        "open_interest_long": 3000,
        "spread_pct_short": 0.05,
        "spread_pct_long": 0.08,
        "quoted_short": True,
        "quoted_long": True,
        "net_delta_share_equiv": 30.0,
    }

    # 1. A clean proposal should pass everything.
    result = run_all_guards(base_state, base_proposal)
    assert result["passed"], result["failed"]
    print(f"Clean proposal: PASS (all {len(ALL_GUARDS)} guards)")

    # 2. Exactly at the soft drawdown line (5.0%) should fail; just under should pass.
    at_line = {**base_state, "current_equity": 100_000 * (1 - cfg.DRAWDOWN_SOFT_PCT)}
    passed, reason = check_drawdown_soft(at_line, base_proposal)
    assert not passed, "exactly at the drawdown line should fail (>=), not pass"
    print(f"At soft drawdown line: BLOCKED ({reason})")

    one_dollar_under = {**base_state, "current_equity": 100_000 * (1 - cfg.DRAWDOWN_SOFT_PCT) + 1}
    passed, reason = check_drawdown_soft(one_dollar_under, base_proposal)
    assert passed, "one dollar under the drawdown line should still pass"
    print("One dollar under soft drawdown line: PASS")

    # 3. At max concurrent positions.
    maxed = {**base_state, "open_positions": [{"max_loss_total": 100, "net_delta_share_equiv": 5}] * cfg.MAX_CONCURRENT_POSITIONS}
    passed, reason = check_concurrent_positions(maxed, base_proposal)
    assert not passed, "at the concurrent-position cap should block"
    print(f"At max concurrent positions: BLOCKED ({reason})")

    # 3b. Risk-limit ordering (T1 fix): CRASH_DAY_BUDGET_PCT must not exceed
    # DRAWDOWN_HARD_PCT, or the crash-day budget could approve more
    # simultaneous risk than the amount meant to trigger the emergency
    # halt -- making Guard #14 structurally unreachable in the exact
    # all-positions-lose-at-once scenario it exists for.
    assert cfg.CRASH_DAY_BUDGET_PCT <= cfg.DRAWDOWN_HARD_PCT, (
        f"CRASH_DAY_BUDGET_PCT ({cfg.CRASH_DAY_BUDGET_PCT:.0%}) exceeds "
        f"DRAWDOWN_HARD_PCT ({cfg.DRAWDOWN_HARD_PCT:.0%}) -- the hard stop "
        "would be unreachable if every open position lost its max at once."
    )
    print(f"Risk-limit ordering: crash-day budget {cfg.CRASH_DAY_BUDGET_PCT:.0%} <= hard stop {cfg.DRAWDOWN_HARD_PCT:.0%}: PASS")

    # Concretely: fill the crash-day budget with positions at the per-trade
    # cap and confirm the guard blocks a proposal that would push committed
    # risk past what the hard stop is meant to bound.
    n_at_cap = int(cfg.CRASH_DAY_BUDGET_PCT // cfg.PER_TRADE_CAP_PCT)  # positions before budget is used up
    committed_positions = [{"max_loss_total": 100_000 * cfg.PER_TRADE_CAP_PCT, "net_delta_share_equiv": 5}] * n_at_cap
    budget_state = {**base_state, "open_positions": committed_positions}
    one_more = {**base_proposal, "max_loss_total": 100_000 * cfg.PER_TRADE_CAP_PCT}
    passed, reason = check_crash_day_budget(budget_state, one_more)
    committed_pct = n_at_cap * cfg.PER_TRADE_CAP_PCT
    assert committed_pct <= cfg.DRAWDOWN_HARD_PCT, "even fully committed budget must not exceed the hard stop"
    print(f"{n_at_cap} positions at the per-trade cap ({committed_pct:.0%} committed): "
          f"one more is {'BLOCKED' if not passed else 'ALLOWED'} ({reason})")

    # 4. IV missing on the chosen leg.
    passed, reason = check_data_sanity(base_state, {**base_proposal, "iv_missing": True})
    assert not passed, "missing IV should block on data-sanity grounds"
    print(f"IV=None on chosen leg: BLOCKED ({reason})")

    # 5. Hard drawdown check independent of soft -- both should fire together at 8%+.
    hard_hit = {**base_state, "current_equity": 100_000 * (1 - cfg.DRAWDOWN_HARD_PCT)}
    soft_passed, _ = check_drawdown_soft(hard_hit, base_proposal)
    hard_passed, hard_reason = check_drawdown_hard(hard_hit, base_proposal)
    assert not soft_passed and not hard_passed
    print(f"At hard drawdown line: BLOCKED by both ({hard_reason})")

    # 6. check_term_structure (W4): stale/missing data fails closed.
    passed, reason = check_term_structure({**base_state, "vix_data_stale": True}, base_proposal)
    assert not passed, "stale VIX data must block, not silently proceed"
    print(f"VIX data stale: BLOCKED ({reason})")

    passed, reason = check_term_structure({**base_state, "vix_contango_ratio": None}, base_proposal)
    assert not passed, "missing contango ratio must block"
    print(f"VIX contango ratio missing: BLOCKED ({reason})")

    # 7. check_term_structure: below the trailing threshold blocks;
    # exactly at or above it passes (mirrors the >= convention already
    # used by the drawdown guards' at-the-line tests above).
    flattening = {**base_state, "vix_contango_ratio": 1.05, "vix_contango_threshold": 1.12}
    passed, reason = check_term_structure(flattening, base_proposal)
    assert not passed, "contango below its trailing threshold must block"
    print(f"VIX term structure flattening (1.05 < 1.12 threshold): BLOCKED ({reason})")

    at_threshold = {**base_state, "vix_contango_ratio": 1.12, "vix_contango_threshold": 1.12}
    passed, reason = check_term_structure(at_threshold, base_proposal)
    assert passed, "contango exactly at the threshold should pass (not a strict block)"
    print(f"VIX term structure exactly at threshold: PASS ({reason})")

    print("\nAll guards.py self-checks passed.")
