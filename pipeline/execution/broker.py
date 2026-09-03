"""
Thin wrapper around the Alpaca trading client: the single place that talks to
the broker for account/position state. Deliberately not MCP -- execution
stays in plain, unit-testable Python (OPTIONS_SYSTEM_PLAN.md Part 8: "Uses
MCP? No - direct alpaca-py" for both fetching and placing orders).
"""

from __future__ import annotations

import os

from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

load_dotenv()

_client: TradingClient | None = None


def get_trading_client() -> TradingClient:
    global _client
    if _client is None:
        _client = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
    return _client


_account_number_cache: str | None = None


def get_account_number() -> str:
    """Cached per-process (cron spawns a fresh process every tick, so this
    is at most one extra API call per run). Exists so the audit log can
    stamp every row with which account produced it -- added after a real
    incident where switching .env mid-day to a new Alpaca account left the
    shared log with no way to tell which account a decision belonged to,
    and run_agent.py's _already_decided_today() silently applied the old
    account's decision to the new account's idempotency check."""
    global _account_number_cache
    if _account_number_cache is None:
        _account_number_cache = get_trading_client().get_account().account_number
    return _account_number_cache


def get_account_state(peak_equity: float | None = None, open_positions: list[dict] | None = None) -> dict:
    """Reads live account state into the shape pipeline.risk.guards expects.
    `peak_equity` must be supplied by the caller (loaded from the audit log
    / a small state file) -- on a genuinely first run it defaults to current
    equity, per the cold-start table in Part 6.

    `open_positions` must be supplied by the caller too, as a list of plain
    dicts carrying this system's synthetic risk fields (max_loss_total,
    net_delta_share_equiv) -- see pipeline.execution.positions.
    open_spread_positions(), which derives them from the audit log. The
    broker's own client.get_all_positions() returns pydantic BaseModel
    Position objects with no .get() method and none of these fields; passing
    them straight through here used to crash guards.py/selector.py on the
    very next run after any successful trade. Raw broker positions are
    still returned separately, under `raw_positions`, for callers (e.g.
    monitor.py) that need real fill quantities for orphan-leg detection.
    """
    client = get_trading_client()
    account = client.get_account()
    raw_positions = client.get_all_positions()

    current_equity = float(account.equity)
    if peak_equity is None:
        peak_equity = current_equity
    peak_equity = max(peak_equity, current_equity)

    return {
        "account_number": account.account_number,
        "current_equity": current_equity,
        "peak_equity": peak_equity,
        "cash": float(account.cash),
        "options_buying_power": float(account.options_buying_power),
        "options_approved_level": account.options_approved_level,
        "trading_blocked": bool(account.trading_blocked),
        "open_positions": open_positions if open_positions is not None else [],
        "raw_positions": [p for p in raw_positions],
        "raw_account": account,
    }


def get_clock() -> dict:
    client = get_trading_client()
    clock = client.get_clock()
    return {"market_open": bool(clock.is_open), "next_open": clock.next_open, "next_close": clock.next_close}


if __name__ == "__main__":
    from pipeline.execution.positions import open_spread_positions

    state = get_account_state(open_positions=open_spread_positions())
    print(f"Equity: ${state['current_equity']:,.2f}")
    print(f"Options buying power: ${state['options_buying_power']:,.2f}")
    print(f"Options level: {state['options_approved_level']}")
    print(f"Open positions (from audit log): {len(state['open_positions'])}")
    print(f"Raw broker positions: {len(state['raw_positions'])}")
    print(f"Trading blocked: {state['trading_blocked']}")

    clock = get_clock()
    print(f"\nMarket open: {clock['market_open']}")
    print(f"Next open: {clock['next_open']}")
    print(f"Next close: {clock['next_close']}")

    # open_positions must be plain dicts with .get() -- confirmed this is
    # what broke before: raw alpaca-py Position objects have no .get().
    assert all(hasattr(p, "get") for p in state["open_positions"])
    assert state["options_approved_level"] == 3
    assert not state["trading_blocked"]
    print("\nAll broker.py self-checks passed.")
