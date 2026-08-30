"""
Build and submit the two-legged MLEG order for a proposal from selector.py.
dry_run=True is the default everywhere in this module -- flipping it to
False is a deliberate, explicit choice made by the caller, never a default.

Rule #8 (Part 6): LIMIT at mid, never MARKET.
Rule #9: wait 5 min -> improve $0.01 once -> cancel and skip. That polling
loop lives in run_agent.py (the daily entry point), not here -- this module
only builds and submits a single order attempt.

The net-price sign convention for a credit spread inside an MLEG order is
NOT verified against real fills yet -- Alpaca's docs don't state it plainly,
and the plan is explicit that this must be confirmed on the first live
1-contract order (Verification #7), not assumed. `net_limit_price` below is
the best-documented-guess convention (negative = net credit, matching a
"debit-style" limit price where receiving money is a negative cost); dry-run
output prints this prominently so a human checks it before Tuesday's smoke
test flips dry_run off.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest


@dataclass
class DryRunResult:
    would_submit: bool
    order_request: LimitOrderRequest
    net_limit_price: float
    summary: str


def build_open_order(proposal: dict) -> tuple[LimitOrderRequest, float]:
    """One SELL_TO_OPEN leg (the short strike) and one BUY_TO_OPEN leg (the
    long strike, our protection), ratio 1:1 -- our spread is always the
    simplest form, so the GCD-of-ratios requirement is trivially satisfied.
    """
    legs = [
        OptionLegRequest(symbol=proposal["short_symbol"], ratio_qty=1, side=OrderSide.SELL, position_intent=PositionIntent.SELL_TO_OPEN),
        OptionLegRequest(symbol=proposal["long_symbol"], ratio_qty=1, side=OrderSide.BUY, position_intent=PositionIntent.BUY_TO_OPEN),
    ]
    # UNVERIFIED sign convention -- see module docstring. Best documented
    # guess: negative limit_price for a net credit.
    net_limit_price = -round(proposal["limit_price_per_share"], 2)

    order = LimitOrderRequest(
        qty=proposal["contracts"],
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        limit_price=net_limit_price,
        legs=legs,
    )
    return order, net_limit_price


def submit_open_order(client: TradingClient, proposal: dict, dry_run: bool = True):
    order_request, net_limit_price = build_open_order(proposal)

    summary = (
        f"SELL {proposal['contracts']}x {proposal['short_symbol']} / "
        f"BUY {proposal['contracts']}x {proposal['long_symbol']}, "
        f"net limit price {net_limit_price:+.2f} (UNVERIFIED sign convention -- "
        f"confirm on the first live 1-contract fill), "
        f"expected credit ${proposal['credit_per_contract']:.2f}/contract, "
        f"max loss ${proposal['max_loss_total']:.0f} total"
    )

    if dry_run:
        print(f"[DRY RUN] Would submit: {summary}")
        return DryRunResult(would_submit=False, order_request=order_request, net_limit_price=net_limit_price, summary=summary)

    print(f"[LIVE] Submitting: {summary}")
    return client.submit_order(order_request)


if __name__ == "__main__":
    # Self-check: build (never submit) an order from a realistic proposal
    # and confirm its shape -- two legs, correct sides/intents, MLEG class.
    fake_proposal = {
        "short_symbol": "SPY260909P00746000",
        "long_symbol": "SPY260909P00745000",
        "contracts": 32,
        "limit_price_per_share": 0.07,
        "credit_per_contract": 7.0,
        "max_loss_total": 2976.0,
    }
    order, net_price = build_open_order(fake_proposal)
    assert order.order_class == OrderClass.MLEG
    assert len(order.legs) == 2
    short_leg = next(l for l in order.legs if l.symbol == fake_proposal["short_symbol"])
    long_leg = next(l for l in order.legs if l.symbol == fake_proposal["long_symbol"])
    assert short_leg.side == OrderSide.SELL and short_leg.position_intent == PositionIntent.SELL_TO_OPEN
    assert long_leg.side == OrderSide.BUY and long_leg.position_intent == PositionIntent.BUY_TO_OPEN
    assert net_price == -0.07
    print(f"Order built: MLEG, 2 legs, net limit price {net_price} (unverified sign, see module docstring)")

    from pipeline.execution.broker import get_trading_client

    result = submit_open_order(get_trading_client(), fake_proposal, dry_run=True)
    assert isinstance(result, DryRunResult) and not result.would_submit
    print(f"\nDry run confirmed nothing was sent: {result.summary}")

    print("\nAll orders.py self-checks passed.")
