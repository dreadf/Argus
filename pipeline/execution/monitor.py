"""
The 15-minute position monitor -- the only thing that ever closes a
position. Alpaca accepts MARKET and LIMIT only on multi-leg option orders
(no broker-side brackets/stops), so every exit rule in the plan is fiction
unless something actively polls and acts (OPTIONS_SYSTEM_PLAN.md Part 8).

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
"""

from __future__ import annotations

from datetime import date

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

    if (short_qty > 0) != (long_qty > 0):
        orphan_leg = "short" if short_qty > 0 else "long"
        return {
            "action": "emergency_close_orphan",
            "orphan_leg": orphan_leg,
            "reason": f"only the {orphan_leg} leg is held -- structural loss cap no longer holds, close immediately",
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
    credit_received = position["credit_per_contract"] / 100
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
    from alpaca.trading.requests import MarketOrderRequest as SingleLegMarketOrderRequest

    if held_side == "short":
        side, intent = OrderSide.BUY, PositionIntent.BUY_TO_CLOSE
    elif held_side == "long":
        side, intent = OrderSide.SELL, PositionIntent.SELL_TO_CLOSE
    else:
        raise ValueError(f"held_side must be 'short' or 'long', got {held_side!r}")
    return SingleLegMarketOrderRequest(symbol=symbol, qty=contracts, side=side, time_in_force=TimeInForce.DAY, position_intent=intent)


if __name__ == "__main__":
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

    print("\nAll monitor.py self-checks passed.")
