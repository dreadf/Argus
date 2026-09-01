"""
The 15-minute position monitor -- the only thing that ever closes a
position. Alpaca accepts MARKET and LIMIT only on multi-leg option orders
(no broker-side brackets/stops), so every exit rule in the plan is fiction
unless something actively polls and acts (OPTIONS_SYSTEM_PLAN.md Part 8).

run_once() (below) is the entry point a scheduler must invoke on a timer --
this file does not schedule itself. Wire a cron entry (or systemd timer)
during market hours, e.g.:
  */15 9-16 * * 1-5 cd /path/to/repo && python -m pipeline.execution.monitor --run --dry-run
Flip to --live only after Tuesday's 1-contract MANUAL smoke test confirms
the order-submission path end to end.

Four checks, in priority order (Part 6's exit-rule table):
  1. One leg orphaned -> emergency close, at market, immediately. The only
     scenario that can exceed the stated max loss.
  2. Tomorrow is expiry day -> close unconditionally, regardless of P&L
     (pin-risk rule: never hold into expiration day).
  3. Profit target hit (buyback costs <= 50% of credit received) -> close,
     bank the profit.
  4. Hard drawdown (8% from peak) -> close everything, halt.

evaluate_position/evaluate_account are pure functions on plain dicts, same
design as guards.py, for the same reason: unit-testable without a live
broker connection, and replayable against the backtest for a false-trip
check on the profit-target and day-before-expiry rules.

Every cycle records a heartbeat (recovery.record_heartbeat), including a
cycle where nothing happens -- a lightweight timestamp file, not a full
audit-log row (every 15 minutes would otherwise flood the schema-locked
audit log with no-op entries). recovery.check_heartbeat_stale reads it
back; a gap of more than a few cycles with positions still open means this
loop stopped running, which is otherwise silent.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest, OptionLegRequest

from pipeline.risk import options_config as risk_cfg


def evaluate_position(position: dict, today: date, current_short_mid: float | None, current_long_mid: float | None) -> dict:
    """`position` describes one open spread: short_symbol, long_symbol,
    contracts, credit_per_contract (at entry), expiry (date), and how many
    contracts the broker actually reports on each leg (short_qty, long_qty)
    -- read from the broker, never assumed, same discipline as broker.py."""
    short_qty = position.get("short_qty", 0)
    long_qty = position.get("long_qty", 0)

    if short_qty != long_qty:
        # Catches both a fully one-sided fill (one leg 0) and a partial
        # mismatch (e.g. short_qty=6, long_qty=3) -- the more realistic
        # failure mode on a multi-contract MLEG order that only partially
        # fills. Either way the protective leg no longer covers every
        # contract of the exposed leg, so the stated max loss no longer
        # holds and this must close immediately, not just when one side is
        # fully empty.
        orphan_leg = "short" if short_qty > long_qty else "long"
        return {
            "action": "emergency_close_orphan",
            "orphan_leg": orphan_leg,
            "reason": f"leg quantities mismatched (short={short_qty}, long={long_qty}) -- structural loss cap no longer holds, close immediately",
        }

    if short_qty == 0 and long_qty == 0:
        return {"action": "hold", "reason": "no position"}

    days_to_expiry = (position["expiry"] - today).days
    if days_to_expiry <= 1:
        return {
            "action": "close_expiry_day_rule",
            "reason": f"expiry in {days_to_expiry} day(s) -- never hold into expiration day (pin-risk rule)",
        }

    if current_short_mid is None or current_long_mid is None:
        return {"action": "hold", "reason": "no live quote this cycle, cannot evaluate profit target"}

    current_buyback_cost = current_short_mid - current_long_mid
    # position["credit_per_contract"] is dollars-per-contract (the same unit
    # selector.py's credit_per_contract = credit_per_share * 100 produces
    # and run_agent.py logs verbatim) -- /100 recovers the per-share credit
    # so it's comparable to current_short_mid/current_long_mid, which are
    # always per-share. Asserted rather than just commented, since this
    # project has already been bitten twice by an unstated unit assumption
    # silently drifting.
    credit_received = position["credit_per_contract"] / 100
    assert 0 <= credit_received < 100, f"credit_received {credit_received} outside a plausible per-share range -- check credit_per_contract's unit"
    if current_buyback_cost <= risk_cfg.PROFIT_TARGET_PCT * credit_received:
        return {
            "action": "close_profit_target",
            "reason": f"buyback cost ${current_buyback_cost:.2f} <= {risk_cfg.PROFIT_TARGET_PCT:.0%} of credit ${credit_received:.2f}",
        }

    return {"action": "hold", "reason": "no exit condition met"}


def evaluate_account(state: dict) -> dict:
    equity = state.get("current_equity", 0.0)
    peak = state.get("peak_equity", equity)
    if peak <= 0:
        return {"action": "hold", "reason": "no peak recorded yet"}
    drawdown = (peak - equity) / peak
    if drawdown >= risk_cfg.DRAWDOWN_HARD_PCT:
        return {
            "action": "close_everything_halt",
            "reason": f"drawdown {drawdown:.2%} at/above hard stop {risk_cfg.DRAWDOWN_HARD_PCT:.0%}",
        }
    return {"action": "hold", "reason": "within hard drawdown limit"}


def build_close_order(position: dict, net_limit_price: float | None = None):
    """Closing intents are the mirror of orders.py's opening intents: we
    BUY_TO_CLOSE the short leg (we were short it) and SELL_TO_CLOSE the long
    leg (we were long it). Pass net_limit_price for a planned LIMIT close;
    omit it for an urgent MARKET close (emergency orphan, or a day-before-
    expiry close past its retry window -- Part 6: "getting out matters more
    than the price we get out at")."""
    legs = [
        OptionLegRequest(symbol=position["short_symbol"], ratio_qty=1, side=OrderSide.BUY, position_intent=PositionIntent.BUY_TO_CLOSE),
        OptionLegRequest(symbol=position["long_symbol"], ratio_qty=1, side=OrderSide.SELL, position_intent=PositionIntent.SELL_TO_CLOSE),
    ]
    if net_limit_price is None:
        return MarketOrderRequest(qty=position["contracts"], order_class=OrderClass.MLEG, time_in_force=TimeInForce.DAY, legs=legs)
    return LimitOrderRequest(
        qty=position["contracts"], order_class=OrderClass.MLEG, time_in_force=TimeInForce.DAY,
        limit_price=round(net_limit_price, 2), legs=legs,
    )


def build_emergency_single_leg_close(symbol: str, contracts: int, held_side: str):
    """`held_side` is 'short' (we sold it, need to BUY_TO_CLOSE) or 'long'
    (we bought it, need to SELL_TO_CLOSE). Single-leg market order, no
    order_class needed -- this isn't a spread, it's the orphan alone."""
    if held_side == "short":
        side, intent = OrderSide.BUY, PositionIntent.BUY_TO_CLOSE
    elif held_side == "long":
        side, intent = OrderSide.SELL, PositionIntent.SELL_TO_CLOSE
    else:
        raise ValueError(f"held_side must be 'short' or 'long', got {held_side!r}")
    return MarketOrderRequest(symbol=symbol, qty=contracts, side=side, time_in_force=TimeInForce.DAY, position_intent=intent)


def _raw_qty(raw_positions: list, symbol: str, side) -> int:
    """Real bug, found live on the first actual fill (2026-09-01): Alpaca
    reports a SHORT position's qty as a NEGATIVE number (e.g. -6 for 6
    short contracts), by broker convention -- `side` already disambiguates
    short vs long, so `int(float(p.qty))` without abs() made a perfectly
    matched 6-short/6-long spread compare as short_qty=-6 != long_qty=6 in
    evaluate_position, which would have triggered emergency_close_orphan on
    a healthy position on the very next monitor cycle. Caught only because
    the cron runs --dry-run; would have submitted a real erroneous close
    under --live."""
    for p in raw_positions:
        if p.symbol == symbol and p.side == side:
            return abs(int(float(p.qty)))
    return 0


def run_once(dry_run: bool = True, today: date | None = None) -> dict:
    """Item 1's fix: this is the function a scheduler must call every ~15
    minutes during market hours (cron/systemd timer -- see the module
    docstring). Without something invoking this on a timer, every exit rule
    above is unreachable code: the Picker can open a position, but nothing
    ever closes one.

    Reads open spreads from the audit log (pipeline.execution.positions,
    same discipline as run_agent.py's account/position handling -- never
    trust the broker's raw Position objects for this system's synthetic
    risk fields), re-prices each against live quotes, evaluates every exit
    rule, and submits + logs any resulting close. Every cycle is logged,
    including a cycle where nothing happens, so a monitor outage is
    visible in the audit trail rather than silent.
    """
    from alpaca.trading.enums import PositionSide

    from pipeline.audit.log import append_entry
    from pipeline.execution.broker import get_account_state, get_clock, get_trading_client
    from pipeline.execution.positions import open_spread_positions
    from pipeline.execution.recovery import record_heartbeat
    from pipeline.options.chain import fetch_option_mids
    from pipeline.options.contracts import parse_occ_symbol

    if today is None:
        today = datetime.now(timezone.utc).date()

    clock = get_clock()
    if not clock["market_open"]:
        record_heartbeat("SKIPPED_MARKET_CLOSED")
        return {"outcome": "SKIPPED", "reason": "market closed", "closed": []}

    client = get_trading_client()
    positions = open_spread_positions()
    if not positions:
        record_heartbeat("NO_OPEN_POSITIONS")
        return {"outcome": "NO_OPEN_POSITIONS", "closed": []}

    account = get_account_state(open_positions=positions)
    raw_positions = account["raw_positions"]

    closed = []

    account_action = evaluate_account({"current_equity": account["current_equity"], "peak_equity": account["peak_equity"]})
    force_close_all = account_action["action"] == "close_everything_halt"

    for position in positions:
        short_qty = _raw_qty(raw_positions, position["short_symbol"], PositionSide.SHORT)
        long_qty = _raw_qty(raw_positions, position["long_symbol"], PositionSide.LONG)
        # expiry isn't stored in the audit log separately -- it's parsed
        # straight from the OCC symbol (contracts.parse_occ_symbol), the
        # same encoding build_occ_symbol used to construct it at open time.
        expiry = parse_occ_symbol(position["short_symbol"])["expiry"]
        position = {**position, "short_qty": short_qty, "long_qty": long_qty, "expiry": expiry}

        if short_qty == 0 and long_qty == 0:
            continue  # already flat (closed outside this loop, or never actually filled)

        if force_close_all:
            action_result = {"action": "close_everything_halt", "reason": account_action["reason"]}
        else:
            mids = fetch_option_mids([position["short_symbol"], position["long_symbol"]])
            action_result = evaluate_position(
                position, today,
                current_short_mid=mids.get(position["short_symbol"]),
                current_long_mid=mids.get(position["long_symbol"]),
            )

        if action_result["action"] == "hold":
            continue

        if action_result["action"] == "emergency_close_orphan":
            held_side = action_result["orphan_leg"]
            symbol = position["short_symbol"] if held_side == "short" else position["long_symbol"]
            # Only the uncovered excess needs an emergency close -- a
            # matched portion (e.g. 3 of 6 short contracts still paired with
            # 3 long contracts) is still a valid, bounded spread.
            qty = abs(short_qty - long_qty)
            order_request = build_emergency_single_leg_close(symbol, qty, held_side)
        else:
            order_request = build_close_order(position)

        summary = f"CLOSE {position['short_symbol']}/{position['long_symbol']} ({action_result['action']}: {action_result['reason']})"
        if dry_run:
            print(f"[DRY RUN] Would submit: {summary}")
            order_result = None
        else:
            print(f"[LIVE] Submitting: {summary}")
            order_result = client.submit_order(order_request)

        append_entry({
            "mode": "MANUAL" if dry_run else "AUTO",
            "short_symbol": position["short_symbol"], "long_symbol": position["long_symbol"],
            "current_equity": account["current_equity"], "peak_equity": account["peak_equity"],
            "outcome": "DRY_RUN" if dry_run else "CLOSED",
            "close_reason": action_result["action"],
            "order_id": str(order_result.id) if order_result is not None else None,
        })
        closed.append({"position": position, "action": action_result["action"]})

    record_heartbeat("OK")
    return {"outcome": "OK", "closed": closed}


if __name__ == "__main__":
    from alpaca.trading.enums import PositionSide

    today = date(2026, 9, 1)

    base_position = {
        "short_symbol": "SPY260909P00746000", "long_symbol": "SPY260909P00745000",
        "contracts": 6, "credit_per_contract": 27.4, "expiry": date(2026, 9, 9),
        "short_qty": 6, "long_qty": 6,
    }

    # 1. Nothing fires on a fresh, healthy position (buyback $0.20 > 50% of
    # the $0.274 credit -- profit target not yet earned).
    result = evaluate_position(base_position, today, current_short_mid=0.25, current_long_mid=0.05)
    assert result["action"] == "hold", result
    print(f"Fresh position, no trigger: {result}")

    # 2. Profit target: buyback cost <= 50% of credit ($27.4/contract = $0.274/share).
    hit_target = evaluate_position(base_position, today, current_short_mid=0.05, current_long_mid=0.04)
    assert hit_target["action"] == "close_profit_target", hit_target
    print(f"Profit target hit: {hit_target}")

    # 3. Day-before-expiry: expiry is 2026-09-09, "today" one day before.
    day_before = evaluate_position(base_position, date(2026, 9, 8), current_short_mid=0.50, current_long_mid=0.10)
    assert day_before["action"] == "close_expiry_day_rule", day_before
    print(f"Day before expiry (profit target NOT hit, still forces close): {day_before}")

    # 4. One-leg orphan: only the short leg filled -- the dangerous case.
    orphan = {**base_position, "short_qty": 6, "long_qty": 0}
    orphan_result = evaluate_position(orphan, today, current_short_mid=0.20, current_long_mid=None)
    assert orphan_result["action"] == "emergency_close_orphan" and orphan_result["orphan_leg"] == "short"
    print(f"Orphaned short leg (dangerous): {orphan_result}")

    # 4b. Partial-fill mismatch: short=6, long=3 -- the more realistic
    # failure mode on a multi-contract MLEG order that only partially
    # fills. Must still be caught (item 11 fix), not just a fully one-sided fill.
    partial = {**base_position, "short_qty": 6, "long_qty": 3}
    partial_result = evaluate_position(partial, today, current_short_mid=0.20, current_long_mid=0.05)
    assert partial_result["action"] == "emergency_close_orphan" and partial_result["orphan_leg"] == "short"
    print(f"Partial-fill mismatch (short=6, long=3): {partial_result}")

    # 5. Hard drawdown.
    drawdown_state = {"current_equity": 92_000.0, "peak_equity": 100_000.0}
    dd = evaluate_account(drawdown_state)
    assert dd["action"] == "close_everything_halt", dd
    print(f"Hard drawdown (8%): {dd}")

    # 6. build_close_order shape check -- closing intents mirror opening.
    order = build_close_order(base_position, net_limit_price=0.05)
    short_leg = next(l for l in order.legs if l.symbol == base_position["short_symbol"])
    long_leg = next(l for l in order.legs if l.symbol == base_position["long_symbol"])
    assert short_leg.side == OrderSide.BUY and short_leg.position_intent == PositionIntent.BUY_TO_CLOSE
    assert long_leg.side == OrderSide.SELL and long_leg.position_intent == PositionIntent.SELL_TO_CLOSE
    print("build_close_order: correct BUY_TO_CLOSE short / SELL_TO_CLOSE long intents")

    emergency = build_emergency_single_leg_close(base_position["short_symbol"], 6, "short")
    assert emergency.side == OrderSide.BUY and emergency.position_intent == PositionIntent.BUY_TO_CLOSE
    print("build_emergency_single_leg_close: correct single-leg BUY_TO_CLOSE for an orphaned short")

    # Regression lock for the real bug found on today's first live fill:
    # Alpaca reports a SHORT position's qty as negative (broker convention).
    # A healthy, fully-matched 6-short/6-long spread must NOT compare as
    # mismatched just because the short leg's raw qty is -6.
    class _FakePosition:
        def __init__(self, symbol, side, qty):
            self.symbol, self.side, self.qty = symbol, side, str(qty)

    healthy_raw = [
        _FakePosition(base_position["short_symbol"], PositionSide.SHORT, -6),
        _FakePosition(base_position["long_symbol"], PositionSide.LONG, 6),
    ]
    s_qty = _raw_qty(healthy_raw, base_position["short_symbol"], PositionSide.SHORT)
    l_qty = _raw_qty(healthy_raw, base_position["long_symbol"], PositionSide.LONG)
    assert s_qty == 6 and l_qty == 6, f"broker's negative short qty (-6) must normalize to 6, got short={s_qty} long={l_qty}"
    healthy_result = evaluate_position({**base_position, "short_qty": s_qty, "long_qty": l_qty}, today, current_short_mid=0.25, current_long_mid=0.05)
    assert healthy_result["action"] == "hold", f"a healthy matched spread with broker-negative short qty must not be flagged orphaned: {healthy_result}"
    print(f"Broker-negative short qty (-6) normalized correctly, healthy spread correctly held: {healthy_result}")

    print("\nAll monitor.py self-checks passed.")

    import argparse

    parser = argparse.ArgumentParser(
        description="Item 1's fix: this must run on a schedule (e.g. a cron "
        "entry like '*/15 9-16 * * 1-5 cd /path/to/repo && python -m "
        "pipeline.execution.monitor --run --dry-run' during market hours) "
        "for any exit rule above to ever actually fire against a live "
        "position. Self-checks above always run first regardless of flags."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True)
    group.add_argument("--live", dest="dry_run", action="store_false")
    parser.add_argument("--run", action="store_true", help="poll the broker and evaluate real open positions (skipped by default -- self-checks only)")
    args = parser.parse_args()

    if args.run:
        cycle_result = run_once(dry_run=args.dry_run)
        print(f"\nMonitor cycle: {cycle_result}")
