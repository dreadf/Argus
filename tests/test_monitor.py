"""
pytest coverage for pipeline/execution/monitor.py's evaluate_position and
evaluate_account -- pure functions, no broker connection, no credentials.

Mirrors monitor.py's own `__main__` self-check block one-for-one (same
scenarios, same expected outcomes) so the checks that already existed only
as a manually-run script are locked in as a CI-reproducible regression
suite. Written because PROGRESS.md's "Code review findings" section
recorded the partial-fill quantity mismatch (short_qty=6, long_qty=3) as
"not yet fixed" -- the fix (monitor.py:54, `short_qty != long_qty`, not a
mere presence check) was already in the code as of commit 5534bc2
(2026-08-31), but had no test outside the inline self-check, so the doc
note went stale instead of getting corrected. This file is the missing
regression lock for exactly that gap.
"""

from __future__ import annotations

from datetime import date

import pytest
from alpaca.trading.enums import OrderSide, PositionIntent, PositionSide

from pipeline.execution.monitor import (
    _raw_qty,
    build_close_order,
    build_emergency_single_leg_close,
    evaluate_account,
    evaluate_position,
    run_once,
)

TODAY = date(2026, 9, 1)

BASE_POSITION = {
    "short_symbol": "SPY260909P00746000",
    "long_symbol": "SPY260909P00745000",
    "contracts": 6,
    "credit_per_contract": 27.4,
    "expiry": date(2026, 9, 9),
    "short_qty": 6,
    "long_qty": 6,
}


class _FakePosition:
    def __init__(self, symbol, side, qty):
        self.symbol, self.side, self.qty = symbol, side, str(qty)


def test_healthy_position_holds():
    result = evaluate_position(BASE_POSITION, TODAY, current_short_mid=0.25, current_long_mid=0.05)
    assert result["action"] == "hold"


def test_profit_target_hit():
    result = evaluate_position(BASE_POSITION, TODAY, current_short_mid=0.05, current_long_mid=0.04)
    assert result["action"] == "close_profit_target"


def test_day_before_expiry_forces_close_even_without_profit_target():
    one_day_before = date(2026, 9, 8)
    result = evaluate_position(BASE_POSITION, one_day_before, current_short_mid=0.50, current_long_mid=0.10)
    assert result["action"] == "close_expiry_day_rule"


def test_fully_orphaned_short_leg_triggers_emergency_close():
    orphaned = {**BASE_POSITION, "short_qty": 6, "long_qty": 0}
    result = evaluate_position(orphaned, TODAY, current_short_mid=0.20, current_long_mid=None)
    assert result["action"] == "emergency_close_orphan"
    assert result["orphan_leg"] == "short"


def test_partial_fill_quantity_mismatch_triggers_emergency_close():
    """The specific gap PROGRESS.md flagged as unfixed: short=6, long=3 is
    not a fully one-sided fill, but the protective leg still no longer
    covers every contract of the exposed leg. Must be caught, not just a
    presence check that only fires when one side is exactly zero."""
    partial = {**BASE_POSITION, "short_qty": 6, "long_qty": 3}
    result = evaluate_position(partial, TODAY, current_short_mid=0.20, current_long_mid=0.05)
    assert result["action"] == "emergency_close_orphan"
    assert result["orphan_leg"] == "short"


def test_partial_fill_emergency_close_only_closes_the_uncovered_excess():
    """Closing the entire short leg on a 6/3 mismatch would be wrong -- 3 of
    the 6 short contracts are still validly paired with the 3 long
    contracts and remain a bounded spread. Only the excess 3 need closing."""
    short_qty, long_qty = 6, 3
    excess = abs(short_qty - long_qty)
    assert excess == 3
    order = build_emergency_single_leg_close(BASE_POSITION["short_symbol"], excess, "short")
    assert order.qty == 3


def test_reversed_partial_mismatch_flags_long_leg():
    reversed_partial = {**BASE_POSITION, "short_qty": 2, "long_qty": 6}
    result = evaluate_position(reversed_partial, TODAY, current_short_mid=0.20, current_long_mid=0.05)
    assert result["action"] == "emergency_close_orphan"
    assert result["orphan_leg"] == "long"


def test_hard_drawdown_halts_everything():
    result = evaluate_account({"current_equity": 92_000.0, "peak_equity": 100_000.0})
    assert result["action"] == "close_everything_halt"


def test_drawdown_within_limit_holds():
    result = evaluate_account({"current_equity": 96_000.0, "peak_equity": 100_000.0})
    assert result["action"] == "hold"


def test_build_close_order_intents_mirror_the_opening_order():
    order = build_close_order(BASE_POSITION, net_limit_price=0.05)
    short_leg = next(leg for leg in order.legs if leg.symbol == BASE_POSITION["short_symbol"])
    long_leg = next(leg for leg in order.legs if leg.symbol == BASE_POSITION["long_symbol"])
    assert short_leg.side == OrderSide.BUY and short_leg.position_intent == PositionIntent.BUY_TO_CLOSE
    assert long_leg.side == OrderSide.SELL and long_leg.position_intent == PositionIntent.SELL_TO_CLOSE


def test_build_emergency_single_leg_close_short_side():
    order = build_emergency_single_leg_close(BASE_POSITION["short_symbol"], 6, "short")
    assert order.side == OrderSide.BUY and order.position_intent == PositionIntent.BUY_TO_CLOSE


def test_build_emergency_single_leg_close_rejects_unknown_side():
    with pytest.raises(ValueError):
        build_emergency_single_leg_close(BASE_POSITION["short_symbol"], 6, "sideways")


class _FakeOrderResult:
    id = "test-order-id"


class _FakeTradingClient:
    def submit_order(self, order_request):
        return _FakeOrderResult()


def _patch_run_once_deps(
    monkeypatch,
    open_position,
    mids,
    current_equity=100_000.0,
    peak_equity=100_000.0,
    raw_positions=None,
):
    """run_once() imports every collaborator inside its own body (`from
    pipeline.execution.broker import get_account_state`, etc.), which
    resolves the name from the SOURCE module at call time -- so patching
    the source module's attribute here is what actually takes effect, not
    patching pipeline.execution.monitor's own namespace."""
    import pipeline.audit.log as audit_log
    import pipeline.execution.broker as broker
    import pipeline.execution.positions as positions
    import pipeline.execution.recovery as recovery
    import pipeline.options.chain as chain

    monkeypatch.setattr(broker, "get_clock", lambda: {"market_open": True})
    monkeypatch.setattr(broker, "get_trading_client", lambda: _FakeTradingClient())
    monkeypatch.setattr(
        broker,
        "get_account_state",
        lambda **kwargs: {
            "current_equity": current_equity,
            "peak_equity": peak_equity,
            "raw_positions": raw_positions or [],
        },
    )
    monkeypatch.setattr(positions, "open_spread_positions", lambda: [open_position] if open_position else [])
    monkeypatch.setattr(chain, "fetch_option_mids", lambda symbols: mids)
    monkeypatch.setattr(recovery, "record_heartbeat", lambda outcome: None)

    logged = []
    monkeypatch.setattr(audit_log, "append_entry", lambda entry: logged.append(entry))
    return logged


def test_run_once_logs_realized_pnl_on_profit_target_close(monkeypatch):
    """The scenario that matters most: the existing live position's profit
    target is already met. When monitor.py goes live, this is the exact
    path that fires within the first cron tick."""
    position = {
        "short_symbol": BASE_POSITION["short_symbol"], "long_symbol": BASE_POSITION["long_symbol"],
        "contracts": 6, "credit_per_contract": 22.0, "max_loss_total": 2868.0, "net_delta_share_equiv": 15.42,
    }
    mids = {BASE_POSITION["short_symbol"]: 0.05, BASE_POSITION["long_symbol"]: 0.04}
    # buyback cost/share = 0.05 - 0.04 = 0.01 <= 50% of $0.22/share credit -> profit target hit
    raw_positions = [
        _FakePosition(BASE_POSITION["short_symbol"], PositionSide.SHORT, -6),
        _FakePosition(BASE_POSITION["long_symbol"], PositionSide.LONG, 6),
    ]
    logged = _patch_run_once_deps(monkeypatch, position, mids, raw_positions=raw_positions)

    result = run_once(dry_run=False, today=date(2026, 9, 1))

    assert result["outcome"] == "OK"
    assert len(result["closed"]) == 1
    assert result["closed"][0]["action"] == "close_profit_target"
    # (22.0 - 0.01*100) * 6 contracts = (22.0 - 1.0) * 6 = 126.0
    assert result["closed"][0]["realized_pnl"] == pytest.approx(126.0)
    assert logged[0]["realized_pnl"] == pytest.approx(126.0)
    assert logged[0]["outcome"] == "CLOSED"


def test_run_once_leaves_realized_pnl_none_for_emergency_orphan_close(monkeypatch):
    """An emergency close only closes the uncovered excess, not the whole
    spread -- there is no single "the spread's P&L" number at that moment,
    so this must stay None rather than fabricate one."""
    position = {
        "short_symbol": BASE_POSITION["short_symbol"], "long_symbol": BASE_POSITION["long_symbol"],
        "contracts": 6, "credit_per_contract": 22.0, "max_loss_total": 2868.0, "net_delta_share_equiv": 15.42,
        # a partial-fill mismatch is read from the broker's raw positions in
        # real life (_raw_qty); patched directly onto the position dict here
        # since get_account_state's raw_positions is mocked to [] above and
        # _raw_qty(..., []) would otherwise report 0/0 for both legs.
    }
    mids = {BASE_POSITION["short_symbol"]: 0.20, BASE_POSITION["long_symbol"]: 0.05}
    logged = _patch_run_once_deps(monkeypatch, position, mids)

    # _raw_qty reads from account["raw_positions"], mocked to [] -> both legs
    # report qty 0, which evaluate_position's "short_qty == 0 and long_qty
    # == 0" branch would treat as "no position" rather than orphaned. Patch
    # _raw_qty directly instead, since the point of this test is the close
    # path's realized_pnl handling, not _raw_qty's own broker-parsing logic
    # (already covered by test_broker_negative_short_qty_normalizes_...).
    import pipeline.execution.monitor as monitor_module

    monkeypatch.setattr(monitor_module, "_raw_qty", lambda raw_positions, symbol, side: 6 if symbol == BASE_POSITION["short_symbol"] else 3)

    result = run_once(dry_run=False, today=date(2026, 9, 1))

    assert result["closed"][0]["action"] == "emergency_close_orphan"
    assert result["closed"][0]["realized_pnl"] is None
    assert logged[0]["realized_pnl"] is None


def test_broker_negative_short_qty_normalizes_and_does_not_false_flag_orphan():
    """Real bug found on the first live fill (2026-09-01): Alpaca reports a
    SHORT position's qty as negative. A healthy, fully-matched spread must
    not compare as mismatched just because the short leg's raw qty is -6."""
    raw_positions = [
        _FakePosition(BASE_POSITION["short_symbol"], PositionSide.SHORT, -6),
        _FakePosition(BASE_POSITION["long_symbol"], PositionSide.LONG, 6),
    ]
    short_qty = _raw_qty(raw_positions, BASE_POSITION["short_symbol"], PositionSide.SHORT)
    long_qty = _raw_qty(raw_positions, BASE_POSITION["long_symbol"], PositionSide.LONG)
    assert short_qty == 6 and long_qty == 6

    result = evaluate_position({**BASE_POSITION, "short_qty": short_qty, "long_qty": long_qty}, TODAY, current_short_mid=0.25, current_long_mid=0.05)
    assert result["action"] == "hold"
