"""
Reconstructs "open spread" risk bookkeeping from the audit log's own
history, not from the broker's raw Position objects.

Fix for the bug where guards.py/selector.py called `.get(...)` on real
alpaca-py `Position` objects (pydantic BaseModels, no `.get()` method) and
would crash on the session after any successful trade. Those objects also
don't carry this system's synthetic risk fields (max_loss_total,
net_delta_share_equiv) at all -- a comment in broker.py falsely claimed
bookkeeping was "layered on in monitor.py/reconcile.py", but neither file
did that.

The audit log is the only durable state this project writes (same
principle _load_peak_equity() in run_agent.py already relies on), so a
spread is treated as open from the moment it is logged SOLD until a
matching CLOSED row (same short_symbol/long_symbol pair) is logged by
monitor.py.
"""

from __future__ import annotations

import pandas as pd

from pipeline.audit.log import read_log


def _current_account_log() -> pd.DataFrame:
    """read_log(), scoped to whichever account .env currently points at.

    The audit log is one shared file regardless of which Alpaca account is
    configured -- switching accounts mid-day (a real incident: swapping a
    disqualified account for a compliant one) would otherwise let the old
    account's SOLD/CLOSED rows be read as the new account's open positions.
    Rows logged before account_number existed, or if the account can't be
    reached, fall back to the unscoped log rather than returning nothing."""
    log_df = read_log()
    if log_df.empty:
        return log_df
    if "account_number" not in log_df.columns:
        # No row has ever carried this field -- since we can't confirm ANY
        # row belongs to the current account, the safe read is "none of
        # them do," matching run_agent.py's _already_decided_today() fix.
        # A row genuinely open right now will have been logged AFTER this
        # fix landed and will carry the field; only pre-fix, already-closed
        # history is excluded here, which is the position this exists to
        # protect against showing as open in the first place.
        return log_df.iloc[0:0]
    try:
        from pipeline.execution.broker import get_account_number
        current = get_account_number()
    except Exception:
        return log_df.iloc[0:0]
    return log_df[log_df["account_number"] == current]


def closed_spread_positions(log_df: pd.DataFrame | None = None) -> list[dict]:
    """The mirror of open_spread_positions(): every CLOSED row, joined back
    to its opening economics (preferring the latest FILLED row for the same
    pair, same reprice-safe logic as above) so a closed position's realized
    P&L can be shown alongside what it opened for and why it closed.

    realized_pnl is whatever monitor.py logged at close time -- None where
    it wasn't computable (an emergency orphan close only closes the
    uncovered excess, not the whole spread; a manual/drawdown-halt
    force-close never fetches a live quote before submitting). Callers must
    handle None explicitly rather than treat it as zero -- summing a mix of
    real numbers and silently-zeroed Nones would understate a stat's
    coverage without saying so, exactly the failure mode this project's
    audit log already avoids by writing missing fields as null."""
    if log_df is None:
        log_df = _current_account_log()
    if log_df.empty:
        return []

    opens = log_df[log_df["outcome"] == "SOLD"].dropna(subset=["short_symbol", "long_symbol"])
    closes = log_df[log_df["outcome"] == "CLOSED"].dropna(subset=["short_symbol", "long_symbol"])
    if closes.empty:
        return []

    fills = log_df[log_df["outcome"] == "FILLED"].dropna(subset=["short_symbol", "long_symbol"])
    latest_fill_by_pair = {}
    if not fills.empty:
        for _, frow in fills.sort_values("timestamp").iterrows():
            latest_fill_by_pair[(frow["short_symbol"], frow["long_symbol"])] = frow

    opens_by_pair = {}
    if not opens.empty:
        for _, orow in opens.sort_values("timestamp").iterrows():
            opens_by_pair[(orow["short_symbol"], orow["long_symbol"])] = orow

    closed_positions = []
    for _, crow in closes.sort_values("timestamp").iterrows():
        pair = (crow["short_symbol"], crow["long_symbol"])
        source = latest_fill_by_pair.get(pair, opens_by_pair.get(pair))
        closed_positions.append(
            {
                "short_symbol": crow["short_symbol"],
                "long_symbol": crow["long_symbol"],
                "closed_at": crow["timestamp"],
                "close_reason": crow.get("close_reason"),
                "contracts": int(source["proposed_contracts"]) if source is not None and pd.notna(source.get("proposed_contracts")) else None,
                "credit_per_contract": float(source["proposed_credit"]) if source is not None and pd.notna(source.get("proposed_credit")) else None,
                "realized_pnl": float(crow["realized_pnl"]) if pd.notna(crow.get("realized_pnl")) else None,
            }
        )
    return closed_positions


def closed_position_stats(log_df: pd.DataFrame | None = None) -> dict:
    """Aggregate stats for the UI. n_with_pnl < n_closed is the honest,
    expected case whenever an emergency or force-close happened -- shown
    explicitly rather than treating the gap as zero."""
    closed = closed_spread_positions(log_df)
    with_pnl = [c for c in closed if c["realized_pnl"] is not None]
    total_realized_pnl = sum(c["realized_pnl"] for c in with_pnl)
    wins = sum(1 for c in with_pnl if c["realized_pnl"] > 0)
    return {
        "n_closed": len(closed),
        "n_with_pnl": len(with_pnl),
        "total_realized_pnl": total_realized_pnl,
        "wins": wins,
        "losses": len(with_pnl) - wins,
        "win_rate": wins / len(with_pnl) if with_pnl else None,
    }


def open_spread_positions(log_df: pd.DataFrame | None = None) -> list[dict]:
    if log_df is None:
        log_df = _current_account_log()
    if log_df.empty:
        return []

    opens = log_df[log_df["outcome"] == "SOLD"].dropna(subset=["short_symbol", "long_symbol"])
    if opens.empty:
        return []
    closes = log_df[log_df["outcome"] == "CLOSED"].dropna(subset=["short_symbol", "long_symbol"])
    closed_pairs = set(zip(closes["short_symbol"], closes["long_symbol"]))

    # A cancel/reprice/resubmit (submit_with_retry) logs a later FILLED row
    # for the same pair with the actual fill economics, which can differ
    # from the original SOLD row's proposed credit/max-loss. Prefer the
    # latest FILLED row per pair when one exists, so this doesn't report a
    # stale proposed price after a reprice.
    fills = log_df[log_df["outcome"] == "FILLED"].dropna(subset=["short_symbol", "long_symbol"])
    latest_fill_by_pair = {}
    if not fills.empty:
        for _, frow in fills.sort_values("timestamp").iterrows():
            latest_fill_by_pair[(frow["short_symbol"], frow["long_symbol"])] = frow

    open_positions = []
    for _, row in opens.iterrows():
        pair = (row["short_symbol"], row["long_symbol"])
        if pair in closed_pairs:
            continue
        source = latest_fill_by_pair.get(pair, row)
        open_positions.append(
            {
                "short_symbol": row["short_symbol"],
                "long_symbol": row["long_symbol"],
                "contracts": int(source["proposed_contracts"]) if pd.notna(source.get("proposed_contracts")) else 0,
                "credit_per_contract": float(source["proposed_credit"]) if pd.notna(source.get("proposed_credit")) else 0.0,
                "max_loss_total": float(source["proposed_max_loss"]) if pd.notna(source.get("proposed_max_loss")) else 0.0,
                "net_delta_share_equiv": float(row["net_delta_share_equiv"]) if pd.notna(row.get("net_delta_share_equiv")) else 0.0,
            }
        )
    return open_positions


if __name__ == "__main__":
    # Self-check: a SOLD row with no matching CLOSED row is open; a SOLD row
    # followed by a CLOSED row for the same pair is not.
    fake_log = pd.DataFrame(
        [
            {"outcome": "SOLD", "short_symbol": "SPY260909P00746000", "long_symbol": "SPY260909P00745000",
             "proposed_contracts": 6, "proposed_credit": 27.4, "proposed_max_loss": 2838.0, "net_delta_share_equiv": 30.0},
            {"outcome": "SOLD", "short_symbol": "SPY260916P00740000", "long_symbol": "SPY260916P00739000",
             "proposed_contracts": 4, "proposed_credit": 22.0, "proposed_max_loss": 1600.0, "net_delta_share_equiv": 20.0},
            {"outcome": "CLOSED", "short_symbol": "SPY260916P00740000", "long_symbol": "SPY260916P00739000",
             "close_reason": "profit_target"},
            {"outcome": "SKIPPED", "short_symbol": None, "long_symbol": None},
        ]
    )
    open_positions = open_spread_positions(fake_log)
    assert len(open_positions) == 1, open_positions
    assert open_positions[0]["short_symbol"] == "SPY260909P00746000"
    print(f"1 of 2 SOLD rows still open after 1 CLOSED row: {open_positions}")

    empty = open_spread_positions(pd.DataFrame(columns=["outcome", "short_symbol", "long_symbol"]))
    assert empty == []
    print("Empty log: no open positions")

    # A cancel/reprice/resubmit logs SOLD at the original (never-filled)
    # price, then FILLED at the actual fill price for the same pair -- the
    # summary must reflect the FILLED row's economics, not the stale SOLD
    # proposal (the bug found live on 2026-09-01's T-LIVE reprice).
    reprice_log = pd.DataFrame(
        [
            {"timestamp": "2026-09-01T16:38:25", "outcome": "SOLD",
             "short_symbol": "SPY260911P00735000", "long_symbol": "SPY260911P00730000",
             "proposed_contracts": 6, "proposed_credit": 27.0, "proposed_max_loss": 2838.0,
             "net_delta_share_equiv": 15.42},
            {"timestamp": "2026-09-01T17:20:30", "outcome": "FILLED",
             "short_symbol": "SPY260911P00735000", "long_symbol": "SPY260911P00730000",
             "proposed_contracts": 6, "proposed_credit": 22.0, "proposed_max_loss": 2868.0,
             "net_delta_share_equiv": None},
        ]
    )
    repriced = open_spread_positions(reprice_log)
    assert len(repriced) == 1, repriced
    assert repriced[0]["credit_per_contract"] == 22.0, repriced
    assert repriced[0]["max_loss_total"] == 2868.0, repriced
    print(f"Reprice: FILLED row's economics win over the stale SOLD proposal: {repriced}")

    print("\nAll execution/positions.py self-checks passed.")
