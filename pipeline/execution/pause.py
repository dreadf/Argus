"""
Local-only "pause trading" flag for the admin controls panel
(CONTROLS_ENABLED=true, pipeline/ui/app.py).

A plain JSON flag file, not an audit-log row: pausing is an operator
decision about whether future runs should even evaluate, not itself a
trading decision, so it doesn't belong in the schema-locked audit log
(pipeline/audit/log.py). Local only -- output/state/ is gitignored, and
there is no remote way to set this, consistent with CONTROLS_ENABLED
gating every write action to a local session.

run_agent.run_once() checks this before anything else, including the
idempotency check, so pausing never gets recorded as a "real decision"
for the day -- resuming later the same day must still let a real
evaluation happen.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

PAUSE_FLAG_PATH = "output/state/trading_paused.json"


def is_trading_paused() -> dict | None:
    """None if not paused, else {"reason": str, "paused_at": iso str}."""
    if not os.path.exists(PAUSE_FLAG_PATH):
        return None
    with open(PAUSE_FLAG_PATH) as f:
        return json.load(f)


def pause_trading(reason: str) -> None:
    os.makedirs(os.path.dirname(PAUSE_FLAG_PATH), exist_ok=True)
    with open(PAUSE_FLAG_PATH, "w") as f:
        json.dump({"reason": reason, "paused_at": datetime.now(timezone.utc).isoformat()}, f)


def resume_trading() -> None:
    if os.path.exists(PAUSE_FLAG_PATH):
        os.remove(PAUSE_FLAG_PATH)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        PAUSE_FLAG_PATH = os.path.join(tmp, "sub", "trading_paused.json")

        assert is_trading_paused() is None, "fresh state must report not paused"
        print("Not paused initially: correct")

        pause_trading("testing")
        state = is_trading_paused()
        assert state is not None and state["reason"] == "testing", state
        print(f"Paused with reason recorded: {state}")

        resume_trading()
        assert is_trading_paused() is None, "must report not paused after resume"
        print("Resumed correctly")

        resume_trading()  # must not raise if already resumed
        print("Double-resume is a safe no-op")

    print("\nAll pause.py self-checks passed.")
