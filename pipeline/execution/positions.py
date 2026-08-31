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


def open_spread_positions(log_df: pd.DataFrame | None = None) -> list[dict]:
    if log_df is None:
        log_df = read_log()
    if log_df.empty:
        return []

    opens = log_df[log_df["outcome"] == "SOLD"].dropna(subset=["short_symbol", "long_symbol"])
    if opens.empty:
        return []
    closes = log_df[log_df["outcome"] == "CLOSED"].dropna(subset=["short_symbol", "long_symbol"])
    closed_pairs = set(zip(closes["short_symbol"], closes["long_symbol"]))

    open_positions = []
    for _, row in opens.iterrows():
        pair = (row["short_symbol"], row["long_symbol"])
        if pair in closed_pairs:
            continue
        open_positions.append(
            {
                "short_symbol": row["short_symbol"],
                "long_symbol": row["long_symbol"],
                "contracts": int(row["proposed_contracts"]) if pd.notna(row.get("proposed_contracts")) else 0,
                "credit_per_contract": float(row["proposed_credit"]) if pd.notna(row.get("proposed_credit")) else 0.0,
                "max_loss_total": float(row["proposed_max_loss"]) if pd.notna(row.get("proposed_max_loss")) else 0.0,
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

    print("\nAll execution/positions.py self-checks passed.")
