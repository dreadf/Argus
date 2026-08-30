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


def get_account_state(peak_equity: float | None = None) -> dict:
    """Reads live account state into the shape pipeline.risk.guards expects.
    Positions are always read from the broker, never assumed (cold-start
    rule: "a fresh account genuinely has none, but the code must not depend
    on that"). `peak_equity` must be supplied by the caller (loaded from the
    audit log / a small state file) -- on a genuinely first run it defaults
    to current equity, per the cold-start table in Part 6.
    """
    client = get_trading_client()
    account = client.get_account()
    positions = client.get_all_positions()

    current_equity = float(account.equity)
    if peak_equity is None:
        peak_equity = current_equity
    peak_equity = max(peak_equity, current_equity)

    return {
        "current_equity": current_equity,
        "peak_equity": peak_equity,
        "cash": float(account.cash),
        "options_buying_power": float(account.options_buying_power),
        "options_approved_level": account.options_approved_level,
        "trading_blocked": bool(account.trading_blocked),
        "open_positions": [p for p in positions],  # option-spread bookkeeping layered on in monitor.py/reconcile.py
        "raw_account": account,
    }


def get_clock() -> dict:
    client = get_trading_client()
    clock = client.get_clock()
    return {"market_open": bool(clock.is_open), "next_open": clock.next_open, "next_close": clock.next_close}


if __name__ == "__main__":
    state = get_account_state()
    print(f"Equity: ${state['current_equity']:,.2f}")
    print(f"Options buying power: ${state['options_buying_power']:,.2f}")
    print(f"Options level: {state['options_approved_level']}")
    print(f"Open positions: {len(state['open_positions'])}")
    print(f"Trading blocked: {state['trading_blocked']}")

    clock = get_clock()
    print(f"\nMarket open: {clock['market_open']}")
    print(f"Next open: {clock['next_open']}")
    print(f"Next close: {clock['next_close']}")

    assert state["options_approved_level"] == 3
    assert not state["trading_blocked"]
    print("\nAll broker.py self-checks passed.")
