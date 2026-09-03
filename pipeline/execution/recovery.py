"""
Failure handling is not optional plumbing (OPTIONS_SYSTEM_PLAN.md: "recovery.py
is the one module that must be correct even if everything else is rough").
Three jobs, in priority order:

1. reconcile_positions() -- read positions from Alpaca and treat that as
   truth, never local state. Call this before opening anything new. If the
   broker holds an option leg the audit log doesn't know about (a manual
   trade, a crash between fill and log write), opening on top of unknown
   exposure is unsafe -- the caller must skip, not proceed.
2. verify_fill_or_emergency_close() -- after every LIVE order submission,
   confirm both legs actually filled in equal quantity. An orphaned short
   put has no floor at all, which is the one scenario where this system's
   stated max loss stops being true. This is the only place authorised to
   place an order nobody asked for, and it may only ever reduce risk.
3. record_heartbeat()/check_heartbeat_stale() -- every cycle, including one
   where nothing happened, records a timestamp, so a monitor outage with
   open positions is visible instead of silent.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from pipeline.execution.positions import open_spread_positions

HEARTBEAT_PATH = "output/audit/heartbeat.json"


def _atomic_write_json(obj: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(obj, f)
    os.replace(tmp_path, path)


def reconcile_positions(raw_positions: list, log_df=None) -> dict:
    """Compares the audit log's belief about what's open against the
    broker's actual option positions. The broker always wins.

    audit_only: the log says a spread is open but the broker shows neither
      leg -- it was actually closed/expired/assigned without a matching
      CLOSED row. A logging gap, not a real position; nothing to act on.
    broker_only: the broker holds an option leg that isn't part of any
      audit-log open spread -- the dangerous case. This system's risk
      bookkeeping doesn't know this exposure exists.
    safe_to_open: False whenever broker_only is non-empty.
    """
    from pipeline.options.contracts import parse_occ_symbol

    open_spreads = open_spread_positions(log_df)
    known_symbols = set()
    for p in open_spreads:
        known_symbols.add(p["short_symbol"])
        known_symbols.add(p["long_symbol"])

    broker_option_symbols = set()
    for p in raw_positions:
        try:
            parse_occ_symbol(p.symbol)
        except ValueError:
            # Not a SPY option leg this system recognizes -- e.g. an
            # equity position from pin-risk assignment. Out of scope for
            # this reconcile step; OPTIONS_SYSTEM_PLAN.md's pin-risk
            # section covers the assignment case separately.
            continue
        broker_option_symbols.add(p.symbol)

    audit_only = sorted(known_symbols - broker_option_symbols)
    broker_only = sorted(broker_option_symbols - known_symbols)

    return {
        "matched": len(known_symbols & broker_option_symbols),
        "audit_only": audit_only,
        "broker_only": broker_only,
        "safe_to_open": len(broker_only) == 0,
    }


def verify_fill_or_emergency_close(client, proposal: dict, dry_run: bool = True) -> dict:
    """Call immediately after a LIVE order submission, before anything
    else. Confirms both legs filled in equal quantity; if not, submits an
    emergency single-leg close for the uncovered excess and signals the
    caller to halt for the day. dry_run mirrors orders.py's convention:
    always the default, flipped only by explicit caller choice."""
    if dry_run:
        return {"ok": True, "halt": False, "reason": "dry run -- no real fill to verify"}

    from alpaca.trading.enums import PositionSide

    from pipeline.audit.log import append_entry
    from pipeline.execution.broker import get_account_state
    from pipeline.execution.monitor import build_emergency_single_leg_close

    account = get_account_state()
    raw_positions = account["raw_positions"]

    def _qty(symbol: str, side) -> int:
        """abs() is load-bearing: Alpaca reports a SHORT position's qty as
        NEGATIVE by broker convention (side already disambiguates short vs
        long). Found live via the same bug in monitor.py's _raw_qty --
        without abs(), a naked short (short_qty=-6, long_qty=0, the exact
        dangerous case this function exists to catch) computed
        orphan_side='long' instead of 'short' (since -6 > 0 is False), which
        would have tried to close a long leg that was never filled while
        leaving the real naked short completely unprotected."""
        for p in raw_positions:
            if p.symbol == symbol and p.side == side:
                return abs(int(float(p.qty)))
        return 0

    short_qty = _qty(proposal["short_symbol"], PositionSide.SHORT)
    long_qty = _qty(proposal["long_symbol"], PositionSide.LONG)

    if short_qty == long_qty:
        return {"ok": True, "halt": False, "reason": f"both legs filled equally ({short_qty} contracts each)"}

    orphan_side = "short" if short_qty > long_qty else "long"
    orphan_symbol = proposal["short_symbol"] if orphan_side == "short" else proposal["long_symbol"]
    excess_qty = abs(short_qty - long_qty)

    order_request = build_emergency_single_leg_close(orphan_symbol, excess_qty, orphan_side)
    order_result = client.submit_order(order_request)

    append_entry({
        "mode": "AUTO",
        "account_number": account.get("account_number"),
        "short_symbol": proposal["short_symbol"], "long_symbol": proposal["long_symbol"],
        "outcome": "EMERGENCY_CLOSE_ORPHAN",
        "close_reason": (
            f"post-submission leg mismatch: short={short_qty}, long={long_qty} -- "
            f"closed {excess_qty} contract(s) of the {orphan_side} leg at market"
        ),
        "order_id": str(order_result.id),
    })

    return {
        "ok": False, "halt": True,
        "reason": (
            f"leg mismatch after submission (short={short_qty}, long={long_qty}) -- "
            f"emergency-closed {excess_qty}x {orphan_side} leg, halting for today"
        ),
    }


def record_heartbeat(outcome: str, path: str = HEARTBEAT_PATH) -> None:
    _atomic_write_json({"timestamp": datetime.now(timezone.utc).isoformat(), "outcome": outcome}, path)


def check_heartbeat_stale(max_age_hours: float = 4.0, path: str = HEARTBEAT_PATH, has_open_positions: bool = False) -> tuple[bool, str]:
    """Fails closed like vix.is_vix_cache_stale: a missing heartbeat while
    positions are open is treated as stale, not as 'nothing to compare
    yet'. With no open positions, a missing file just means nothing has
    run since a clean slate -- not alarming."""
    if not os.path.exists(path):
        if has_open_positions:
            return True, "no heartbeat recorded yet, but positions are open -- treat as stale"
        return False, "no heartbeat recorded yet, no open positions -- nothing to alert on"

    with open(path) as f:
        data = json.load(f)
    last = datetime.fromisoformat(data["timestamp"])
    age_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
    if age_hours > max_age_hours:
        return True, f"last heartbeat {age_hours:.1f}h ago, exceeds {max_age_hours}h -- monitor may be down"
    return False, f"last heartbeat {age_hours:.1f}h ago -- within {max_age_hours}h"


if __name__ == "__main__":
    import tempfile

    from alpaca.trading.enums import PositionSide

    class _FakePosition:
        def __init__(self, symbol: str, side, qty: str = "6"):
            self.symbol = symbol
            self.side = side
            self.qty = qty

    fake_log = __import__("pandas").DataFrame([
        {"outcome": "SOLD", "short_symbol": "SPY260909P00746000", "long_symbol": "SPY260909P00745000",
         "proposed_contracts": 6, "proposed_credit": 27.4, "proposed_max_loss": 2838.0, "net_delta_share_equiv": 30.0},
    ])

    # 1. Matched: broker shows exactly the audit log's open spread.
    matched_raw = [
        _FakePosition("SPY260909P00746000", PositionSide.SHORT),
        _FakePosition("SPY260909P00745000", PositionSide.LONG),
    ]
    r = reconcile_positions(matched_raw, fake_log)
    assert r["safe_to_open"] and r["matched"] == 2 and not r["audit_only"] and not r["broker_only"], r
    print(f"Matched reconcile: {r}")

    # 2. broker_only: an option position the audit log has never heard of
    # -- the dangerous case, must block new opens.
    unknown_raw = matched_raw + [_FakePosition("SPY260916P00700000", PositionSide.SHORT)]
    r = reconcile_positions(unknown_raw, fake_log)
    assert not r["safe_to_open"] and r["broker_only"] == ["SPY260916P00700000"], r
    print(f"Unknown broker position blocks new opens: {r}")

    # 3. audit_only: the log thinks a spread is open, broker shows nothing
    # -- a logging gap, not a real position; must NOT block new opens.
    r = reconcile_positions([], fake_log)
    assert r["safe_to_open"] and set(r["audit_only"]) == {"SPY260909P00746000", "SPY260909P00745000"}, r
    print(f"Audit-only (stale log row) does not block: {r}")

    # 4. An assigned equity SPY position (not an OCC option symbol) is
    # ignored by this reconcile step, not misread as an unknown option.
    equity_raw = matched_raw + [_FakePosition("SPY", PositionSide.LONG)]
    r = reconcile_positions(equity_raw, fake_log)
    assert r["safe_to_open"], r
    print(f"Equity position (pin-risk assignment) ignored, not flagged as an option mismatch: {r}")

    # 5. verify_fill_or_emergency_close: dry run never touches the network.
    result = verify_fill_or_emergency_close(client=None, proposal={"short_symbol": "x", "long_symbol": "y"}, dry_run=True)
    assert result == {"ok": True, "halt": False, "reason": "dry run -- no real fill to verify"}
    print(f"Dry run: {result}")

    # 6. verify_fill_or_emergency_close: both legs filled equally -> no halt.
    # verify_fill_or_emergency_close does its `from X import Y` INSIDE the
    # function body (lazy, matching monitor.py's own convention -- avoids
    # eager network/client setup at self-check time), so patching must
    # target the SOURCE modules' attributes, not this module's globals():
    # a local `from X import Y` re-reads X's current attribute at call
    # time, but only if X itself is a single shared module instance. That
    # holds here (broker/audit.log/monitor are imported normally, not
    # re-imported under __main__ the way reviewer.py's self-test was
    # bitten by a second module instance) -- so patching the source
    # modules' attributes is correct and sufficient.
    import pipeline.audit.log as _audit_log_module
    import pipeline.execution.broker as _broker_module
    import pipeline.execution.monitor as _monitor_module

    proposal = {"short_symbol": "SPY260909P00746000", "long_symbol": "SPY260909P00745000", "contracts": 6}

    class _FakeClient:
        def submit_order(self, order_request):
            class _Order:
                id = "fake-order-id"
            return _Order()

    _broker_module.get_account_state = lambda: {"raw_positions": [
        _FakePosition("SPY260909P00746000", PositionSide.SHORT),
        _FakePosition("SPY260909P00745000", PositionSide.LONG),
    ]}
    _monitor_module.build_emergency_single_leg_close = lambda symbol, qty, side: object()
    _audit_log_module.append_entry = lambda entry: entry

    # Both legs match -> ok, no halt, no emergency order.
    result = verify_fill_or_emergency_close(_FakeClient(), proposal, dry_run=False)
    assert result == {"ok": True, "halt": False, "reason": "both legs filled equally (6 contracts each)"}, result
    print(f"Matched live fill: {result}")

    # 7. verify_fill_or_emergency_close: orphaned short leg -> emergency
    # close submitted, halt=True. qty="-6" matches real Alpaca behavior
    # (a short position's qty is reported negative) -- an earlier version
    # of this test hardcoded qty="6" for every fake position regardless of
    # side, which meant it never actually exercised the sign the broker
    # really sends and missed a real bug where the un-abs()'d qty picked
    # 'long' as the orphan side instead of 'short'.
    _broker_module.get_account_state = lambda: {"raw_positions": [
        _FakePosition("SPY260909P00746000", PositionSide.SHORT, qty="-6"),  # long leg never filled
    ]}
    emergency_calls = []
    _monitor_module.build_emergency_single_leg_close = lambda symbol, qty, side: emergency_calls.append((symbol, qty, side)) or object()
    logged = []
    _audit_log_module.append_entry = lambda entry: logged.append(entry) or entry

    result = verify_fill_or_emergency_close(_FakeClient(), proposal, dry_run=False)
    assert result["halt"] and not result["ok"], result
    # The naked SHORT leg (no protective long to cap the loss) is what
    # gets bought back -- same "close the uncovered excess" convention as
    # monitor.py's evaluate_position orphan-leg handling, not the empty
    # long leg (there's nothing there to close).
    assert emergency_calls == [("SPY260909P00746000", 6, "short")], emergency_calls
    assert logged and logged[0]["outcome"] == "EMERGENCY_CLOSE_ORPHAN", logged
    print(f"Orphaned leg: {result}\n  emergency close submitted: {emergency_calls[0]}")

    # 8. Heartbeat: fresh write is never stale; backdated write past the
    # window is stale; a missing file is stale only if positions are open.
    with tempfile.TemporaryDirectory() as tmp:
        hb_path = os.path.join(tmp, "heartbeat.json")

        record_heartbeat("OK", path=hb_path)
        stale, reason = check_heartbeat_stale(max_age_hours=4.0, path=hb_path, has_open_positions=True)
        assert not stale, reason
        print(f"Fresh heartbeat: {reason}")

        old = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        with open(hb_path, "w") as f:
            json.dump({"timestamp": old, "outcome": "OK"}, f)
        stale, reason = check_heartbeat_stale(max_age_hours=4.0, path=hb_path, has_open_positions=True)
        assert stale, reason
        print(f"Backdated (5h) heartbeat: {reason}")

        missing_path = os.path.join(tmp, "never_written.json")
        stale, reason = check_heartbeat_stale(path=missing_path, has_open_positions=True)
        assert stale, reason
        stale, reason = check_heartbeat_stale(path=missing_path, has_open_positions=False)
        assert not stale, reason
        print("Missing heartbeat: stale (fails closed) with open positions, not stale with none")

    print("\nAll execution/recovery.py self-checks passed.")
