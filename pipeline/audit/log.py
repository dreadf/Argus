"""
Append-only decision log, one JSON line per decision -- including every
decision NOT to trade. Schema fixed here, before anything else writes to it
(TRADING_SYSTEM_PLAN.md:338's lesson: retrofitting an audit log is painful,
growing one from day one is free).

Cold-start rule (Part 6): a missing log file is not a reason to skip
logging -- append_entry creates the file and its parent directory on first
use.
"""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone

import pandas as pd

AUDIT_LOG_PATH = "output/audit/decisions.jsonl"

# Every field a decision row can carry. Fields not supplied on a given call
# are written as null -- e.g. a SKIP day has no order_id or fill_price, and a
# day the Reviewer never ran has no reviewer_* fields. Missing is not an
# error; it's information (what didn't happen, and why).
SCHEMA_FIELDS = [
    "timestamp", "mode", "account_number",
    "current_equity", "peak_equity",
    "spy_price", "vol_forecast",
    "gate_distance", "gate_cushion_se", "realized_distance",
    "short_symbol", "long_symbol", "net_delta_share_equiv",
    "proposed_contracts", "proposed_credit", "proposed_max_loss",
    "guards_checked", "guards_failed", "budget_remaining",
    "reviewer_decision", "reviewer_multiplier", "reviewer_reason",
    "human_action", "order_id", "fill_price", "both_legs_confirmed",
    "outcome", "realized_pnl", "close_reason",
]


def append_entry(entry: dict, path: str = AUDIT_LOG_PATH) -> dict:
    """Writes one row. Unknown keys in `entry` are rejected (schema drift
    should be a deliberate edit to SCHEMA_FIELDS, not a silent typo);
    missing keys are filled with None. Returns the row actually written."""
    unknown = set(entry.keys()) - set(SCHEMA_FIELDS)
    if unknown:
        raise ValueError(f"unknown audit log field(s): {unknown}. Add them to SCHEMA_FIELDS first.")

    row = {field: entry.get(field) for field in SCHEMA_FIELDS}
    if row["timestamp"] is None:
        row["timestamp"] = datetime.now(timezone.utc).isoformat()
    # account_number is stamped by the caller (it already has account state
    # in hand at every point that matters), never fetched here -- append_entry
    # must stay network-free, it's called from pre-flight paths before any
    # account fetch happens, and a live call here once hung the entire test
    # suite (network access is not guaranteed/fast in every environment this
    # runs in).

    os.makedirs(os.path.dirname(path), exist_ok=True)
    # An exclusive advisory lock around the write -- not triggerable today
    # (nothing runs concurrently), but becomes real the moment run_agent.py
    # and monitor.py run as separate scheduled processes writing to the
    # same file. flock releases automatically when the `with` block exits,
    # even on a crash, so this can't deadlock a future writer.
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(row, default=str) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return row


def read_log(path: str = AUDIT_LOG_PATH) -> pd.DataFrame:
    """Never raises on a missing or empty log -- the UI's cold-open drill
    (Part 8, Verification #22) requires rendering sensibly with zero rows."""
    if not os.path.exists(path):
        return pd.DataFrame(columns=SCHEMA_FIELDS)
    rows = []
    with open(path) as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                # A truncated/corrupted line (e.g. a write interrupted by a
                # killed process) must not take down every reader of this
                # log -- skip it and warn, rather than raising straight
                # through to callers like the public dashboard.
                print(f"WARNING: skipping unparseable audit log line {line_no} in {path}: {e}")
    if not rows:
        return pd.DataFrame(columns=SCHEMA_FIELDS)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_path = os.path.join(tmp, "decisions.jsonl")

        # Self-check 1: reading a log that doesn't exist yet returns an
        # empty, correctly-shaped DataFrame rather than raising.
        empty = read_log(test_path)
        assert empty.empty and list(empty.columns) == SCHEMA_FIELDS
        print("Missing log file: read_log returns empty DataFrame with the right schema")

        # Self-check 2: append_entry creates the file and parent dir.
        row1 = append_entry({"mode": "MANUAL", "spy_price": 769.28, "outcome": "SKIPPED",
                              "guards_failed": ["check_liquidity"]}, path=test_path)
        assert os.path.exists(test_path)
        assert row1["timestamp"] is not None
        print("append_entry created the file and filled in a timestamp")

        # Self-check 3: unknown field is rejected loudly, not silently dropped.
        try:
            append_entry({"not_a_real_field": 1}, path=test_path)
            raise AssertionError("expected ValueError for an unknown field")
        except ValueError as e:
            print(f"Unknown field correctly rejected: {e}")

        # Self-check 4: a second entry appends rather than overwriting.
        append_entry({"mode": "AUTO", "spy_price": 770.0, "outcome": "SOLD",
                       "proposed_contracts": 6, "realized_pnl": None}, path=test_path)
        df = read_log(test_path)
        assert len(df) == 2, len(df)
        assert df.iloc[0]["outcome"] == "SKIPPED" and df.iloc[1]["outcome"] == "SOLD"
        print(f"Two entries appended and read back in order: {df['outcome'].tolist()}")

    print("\nAll audit/log.py self-checks passed.")
