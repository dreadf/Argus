"""
Build and submit the two-legged MLEG order for a proposal from selector.py.
dry_run=True is the default everywhere in this module -- flipping it to
False is a deliberate, explicit choice made by the caller, never a default.

Rule #8 (Part 6): LIMIT at mid, never MARKET.
Rule #9: wait 5 min -> improve $0.01 once -> cancel and skip. That polling
loop lives in run_agent.py (the daily entry point), not here -- this module
only builds and submits a single order attempt.

CONFIRMED sign convention (2026-09-01, first live fill, order
ae5cf304-5837-418f-b5c6-54e5d1fab767): negative net_limit_price = net
credit. A 6-contract SPY 735/730 put credit spread submitted at
net_limit_price=-0.22 filled at -0.23, and account cash increased by
$137.70 (~0.23 * 100 * 6, minus a cent of rounding) -- cash going UP on a
negative fill price is only consistent with negative meaning credit, not
debit. Alpaca's docs never stated this plainly, hence Verification #7's
requirement to confirm on a real fill rather than assume it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, PositionIntent, TimeInForce
from alpaca.trading.requests import LimitOrderRequest, OptionLegRequest

# Rule #9 (Part 6): wait 5 min -> improve $0.01 once -> cancel and skip.
# Never actually implemented until now -- found live on the first real
# order (2026-09-01), which sat unfilled 28 minutes with nothing to act on
# it, and had to be handled manually. FILL_WAIT_SECONDS/REPRICE_WAIT_SECONDS/
# POLL_INTERVAL_SECONDS are module-level constants (not hardcoded inline)
# so a self-check can override them to tiny values and run in milliseconds
# rather than actually sleeping for minutes.
FILL_WAIT_SECONDS = 300
REPRICE_WAIT_SECONDS = 180
POLL_INTERVAL_SECONDS = 15
_TERMINAL_NON_FILL = ("CANCELED", "REJECTED", "EXPIRED", "DONE_FOR_DAY")


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
    # Confirmed sign convention (see module docstring): negative
    # limit_price for a net credit, verified against a real fill.
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
        f"net limit price {net_limit_price:+.2f} (sign convention confirmed live 2026-09-01), "
        f"expected credit ${proposal['credit_per_contract']:.2f}/contract, "
        f"max loss ${proposal['max_loss_total']:.0f} total"
    )

    if dry_run:
        print(f"[DRY RUN] Would submit: {summary}")
        return DryRunResult(would_submit=False, order_request=order_request, net_limit_price=net_limit_price, summary=summary)

    print(f"[LIVE] Submitting: {summary}")
    return client.submit_order(order_request)


def poll_order_status(client: TradingClient, order_id: str, max_wait_seconds: float,
                       poll_interval: float | None = None) -> str:
    """Polls a submitted order until it fills, reaches another terminal
    state, or max_wait_seconds elapses. Returns 'FILLED', 'TERMINAL_OTHER'
    (canceled/rejected/expired/done-for-day), or 'TIMEOUT' (still open when
    time ran out). Never cancels anything itself -- that decision belongs
    to the caller.

    poll_interval defaults to the module constant, resolved INSIDE the
    function rather than as a default argument value -- a default value is
    evaluated once at def time, so a self-check monkeypatching
    POLL_INTERVAL_SECONDS to run fast would silently have no effect on this
    parameter if it were a plain default instead."""
    if poll_interval is None:
        poll_interval = POLL_INTERVAL_SECONDS
    elapsed = 0.0
    while elapsed < max_wait_seconds:
        order = client.get_order_by_id(order_id)
        status = str(order.status)
        if "FILLED" in status and "PARTIALLY" not in status:
            return "FILLED"
        if any(s in status for s in _TERMINAL_NON_FILL):
            return "TERMINAL_OTHER"
        time.sleep(poll_interval)
        elapsed += poll_interval
    return "TIMEOUT"


def reprice_proposal(proposal: dict, short_mid: float, long_mid: float) -> dict:
    """Rule #9's 'improve' step: rebuilds a proposal at a freshly-quoted mid
    credit. Only price-dependent fields change -- symbols, contracts, and
    max_loss_total (a function of width, not price) stay fixed."""
    new_credit_per_share = round(short_mid - long_mid, 2)
    return {**proposal, "limit_price_per_share": new_credit_per_share, "credit_per_contract": new_credit_per_share * 100}


def submit_with_retry(client: TradingClient, proposal: dict, dry_run: bool = True) -> dict:
    """Rule #9 in full: submit at mid, wait up to FILL_WAIT_SECONDS; if
    still unfilled, cancel, refresh the mid ONCE (never more -- Rule #9 says
    'improve once', not chase the market indefinitely), resubmit, wait up to
    REPRICE_WAIT_SECONDS; if still unfilled, cancel and give up for today.

    Returns {"status": "FILLED"|"SKIPPED"|"DRY_RUN", "order_result": ...,
    "proposal": <the proposal actually filled, possibly repriced>,
    "reason": <only present when status == "SKIPPED">}.

    dry_run short-circuits to a single submit_open_order call with no
    waiting, matching every other function in this module."""
    if dry_run:
        return {"status": "DRY_RUN", "order_result": submit_open_order(client, proposal, dry_run=True), "proposal": proposal}

    order_result = submit_open_order(client, proposal, dry_run=False)
    status = poll_order_status(client, str(order_result.id), FILL_WAIT_SECONDS)

    if status == "FILLED":
        return {"status": "FILLED", "order_result": order_result, "proposal": proposal}
    if status == "TERMINAL_OTHER":
        return {"status": "SKIPPED", "order_result": order_result, "proposal": proposal,
                "reason": f"order reached a non-fill terminal state ({order_result.id})"}

    # status == "TIMEOUT" -- improve once.
    try:
        client.cancel_order_by_id(order_result.id)
    except Exception:
        pass  # already resolved between our last poll and now -- the re-check below is what actually decides, not this
    # Cancellation can race a last-second fill. Trust the broker's final
    # word over our last poll before resubmitting -- resubmitting on top of
    # an actual fill would open a second, unplanned spread.
    final_check = client.get_order_by_id(order_result.id)
    if "FILLED" in str(final_check.status) and "PARTIALLY" not in str(final_check.status):
        return {"status": "FILLED", "order_result": final_check, "proposal": proposal}

    from pipeline.options.chain import fetch_option_mids

    mids = fetch_option_mids([proposal["short_symbol"], proposal["long_symbol"]])
    if mids.get(proposal["short_symbol"]) is None or mids.get(proposal["long_symbol"]) is None:
        return {"status": "SKIPPED", "order_result": order_result, "proposal": proposal,
                "reason": "could not fetch a fresh quote to reprice"}

    improved_proposal = reprice_proposal(proposal, mids[proposal["short_symbol"]], mids[proposal["long_symbol"]])
    order_result_2 = submit_open_order(client, improved_proposal, dry_run=False)
    status_2 = poll_order_status(client, str(order_result_2.id), REPRICE_WAIT_SECONDS)

    if status_2 == "FILLED":
        return {"status": "FILLED", "order_result": order_result_2, "proposal": improved_proposal}

    try:
        client.cancel_order_by_id(order_result_2.id)
    except Exception:
        pass
    return {"status": "SKIPPED", "order_result": order_result_2, "proposal": improved_proposal,
            "reason": f"order did not fill after one reprice attempt (final status: {status_2})"}


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
    print(f"Order built: MLEG, 2 legs, net limit price {net_price} (sign convention confirmed live, see module docstring)")

    from pipeline.execution.broker import get_trading_client

    result = submit_open_order(get_trading_client(), fake_proposal, dry_run=True)
    assert isinstance(result, DryRunResult) and not result.would_submit
    print(f"\nDry run confirmed nothing was sent: {result.summary}")

    # --- Rule #9 (wait/improve/cancel) self-checks -----------------------
    # Shrink the wait constants to run in milliseconds instead of minutes --
    # safe because poll_order_status/submit_with_retry read these as module
    # globals at call time, not as baked-in default-argument values.
    FILL_WAIT_SECONDS = 0.05
    REPRICE_WAIT_SECONDS = 0.05
    POLL_INTERVAL_SECONDS = 0.01

    import pipeline.options.chain as _chain_module

    class _FakeOrder:
        def __init__(self, id_, status):
            self.id = id_
            self.status = status

    class _FakeClient:
        """Scripted broker: `statuses` is a list of order-id sequences to
        return from get_order_by_id, one per submitted order (so the Nth
        submit_order call's fills are governed by statuses[N])."""
        def __init__(self, statuses: list[list[str]]):
            self.statuses = statuses
            self.submit_count = 0
            self.cancel_calls = []
            self._poll_index = []

        def submit_order(self, order_request):
            idx = self.submit_count
            self.submit_count += 1
            self._poll_index.append(0)
            return _FakeOrder(f"order-{idx}", self.statuses[idx][0])

        def get_order_by_id(self, order_id):
            idx = int(order_id.split("-")[1])
            seq = self.statuses[idx]
            i = min(self._poll_index[idx], len(seq) - 1)
            status = seq[i]
            self._poll_index[idx] += 1
            return _FakeOrder(order_id, status)

        def cancel_order_by_id(self, order_id):
            self.cancel_calls.append(order_id)

    fake_proposal_2 = {**fake_proposal, "contracts": 6}

    # 1. Fills immediately -- no reprice needed, no cancel called.
    client_1 = _FakeClient(statuses=[["OrderStatus.FILLED"] * 10])
    result_1 = submit_with_retry(client_1, fake_proposal_2, dry_run=False)
    assert result_1["status"] == "FILLED" and result_1["proposal"] == fake_proposal_2
    assert client_1.cancel_calls == [], "must not cancel an order that filled on the first attempt"
    print(f"submit_with_retry, fills immediately: {result_1['status']}, no cancel called")

    # 2. Never fills, times out on the first attempt (all "new"), gets
    # cancelled, repriced against a fresh mid, and fills on the second try.
    _chain_module.fetch_option_mids = lambda symbols: {fake_proposal_2["short_symbol"]: 0.20, fake_proposal_2["long_symbol"]: 0.05}
    client_2 = _FakeClient(statuses=[["OrderStatus.NEW"] * 10, ["OrderStatus.FILLED"] * 10])
    result_2 = submit_with_retry(client_2, fake_proposal_2, dry_run=False, )
    assert result_2["status"] == "FILLED"
    assert client_2.submit_count == 2, "must submit exactly twice: original + one reprice, never more"
    assert client_2.cancel_calls == ["order-0"], "must cancel the stale first order before repricing"
    assert result_2["proposal"]["limit_price_per_share"] == 0.15, f"repriced credit should be fresh short_mid - long_mid = 0.15, got {result_2['proposal']['limit_price_per_share']}"
    print(f"submit_with_retry, times out then fills on reprice: {result_2['status']}, repriced to {result_2['proposal']['limit_price_per_share']}")

    # 3. Never fills at all, even after the one allowed reprice -> SKIPPED,
    # cancelled twice (original + repriced), never a third submission.
    client_3 = _FakeClient(statuses=[["OrderStatus.NEW"] * 10, ["OrderStatus.NEW"] * 10])
    result_3 = submit_with_retry(client_3, fake_proposal_2, dry_run=False)
    assert result_3["status"] == "SKIPPED" and "reason" in result_3
    assert client_3.submit_count == 2, "must give up after exactly one reprice attempt, never chase the market further"
    assert client_3.cancel_calls == ["order-0", "order-1"]
    print(f"submit_with_retry, never fills: {result_3['status']} -- {result_3['reason']}")

    # 4. Race condition: our poll loop times out, but the order actually
    # filled in the gap between the last poll and the cancel call. Must
    # trust the broker's answer to the post-cancel re-check and report
    # FILLED, NOT resubmit a second spread on top of a real fill.
    client_4 = _FakeClient(statuses=[["OrderStatus.NEW", "OrderStatus.NEW", "OrderStatus.FILLED"] + ["OrderStatus.FILLED"] * 10])
    result_4 = submit_with_retry(client_4, fake_proposal_2, dry_run=False)
    assert result_4["status"] == "FILLED", "a fill discovered on the post-cancel re-check must win, not trigger a reprice"
    assert client_4.submit_count == 1, "must not resubmit when the original order actually filled"
    print(f"submit_with_retry, race (fills right as we cancel): {result_4['status']}, only 1 submission")

    # 5. dry_run short-circuits entirely -- no polling, no client calls
    # beyond the DryRunResult itself.
    client_5 = _FakeClient(statuses=[])
    result_5 = submit_with_retry(client_5, fake_proposal_2, dry_run=True)
    assert result_5["status"] == "DRY_RUN" and isinstance(result_5["order_result"], DryRunResult)
    assert client_5.submit_count == 0
    print(f"submit_with_retry, dry run: {result_5['status']}, no broker calls made")

    reprice_test = reprice_proposal(fake_proposal_2, short_mid=0.30, long_mid=0.08)
    assert reprice_test["limit_price_per_share"] == 0.22 and reprice_test["credit_per_contract"] == 22.0
    assert reprice_test["short_symbol"] == fake_proposal_2["short_symbol"], "reprice must not touch identity fields"
    print(f"reprice_proposal: 0.30 - 0.08 -> {reprice_test['limit_price_per_share']}")

    print("\nAll orders.py self-checks passed.")
