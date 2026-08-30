"""
Read-only MCP server for the Reviewer.

The alpaca-mcp-server package's ALPACA_TOOLSETS env var only filters at the
toolset level, and its "trading" toolset bundles safe reads (getAllOpenPositions,
getOpenPosition, getAllOrders) together with dangerous writes (deleteOpenPosition,
deleteAllOpenPositions, optionExercise) and is also the switch that registers the
hand-crafted place_option_order / place_stock_order / place_crypto_order override
tools. There is no toolset name that gives positions without also giving those.

So this builds the server directly from the package's internals with a hand-picked
operation allowlist instead of a toolset name, and never calls
_register_trading_overrides — meaning place_option_order and friends are never
even defined, not just filtered out afterward.

Run with: python -m pipeline.mcp.reviewer_server
"""

from __future__ import annotations

import os

import httpx
from fastmcp import FastMCP

from alpaca_mcp_server.market_data_overrides import register_market_data_tools
from alpaca_mcp_server.readme_docs import register_readme_docs_tools
from alpaca_mcp_server.security import TrustBoundaryMiddleware
from alpaca_mcp_server.server import (
    MARKET_DATA_BASE_URL,
    TRADING_API_BASE_URLS,
    _build_auth_headers,
    _ensure_scheme,
    _load_spec,
    _make_customizer,
    _make_filter,
)
from alpaca_mcp_server.tool_registry import TOOL_DESCRIPTIONS, TOOL_NAMES

# Read-only subset of the "trading" spec: account state and order/position
# visibility only. Excludes deleteOpenPosition, deleteAllOpenPositions,
# deleteOrderByOrderID, deleteAllOrders, patchOrderByOrderId,
# optionExercise, optionDoNotExercise, and postOrder.
READ_ONLY_TRADING_OPS = {
    "getAccount",
    "getAccountConfig",
    "getAccountPortfolioHistory",
    "getAccountActivities",
    "getAccountActivitiesByActivityType",
    "getAllOrders",
    "getOrderByOrderID",
    "getOrderByClientOrderId",
    "getAllOpenPositions",
    "getOpenPosition",
    "getWatchlists",
    "getWatchlistById",
    "get-v2-assets",
    "get-v2-assets-symbol_or_asset_id",
    "get-options-contracts",
    "get-option-contract-symbol_or_id",
    "LegacyCalendar",
    "LegacyClock",
    "get-v2-corporate_actions-announcements",
    "get-v2-corporate_actions-announcements-id",
}

# Full market-data spec is read-only by nature (quotes, bars, chains, news).
READ_ONLY_MARKET_DATA_OPS = {
    "StockBars", "StockQuotes", "StockTrades", "StockLatestBars",
    "StockLatestQuotes", "StockLatestTrades", "StockSnapshots",
    "MostActives", "Movers",
    "optionBars", "OptionTrades", "OptionLatestTrades", "OptionLatestQuotes",
    "OptionSnapshots", "OptionChain", "OptionMetaExchanges",
    "CorporateActions", "News", "FixedIncomeLatestQuotes",
}

FORBIDDEN_OPS = {
    "postOrder", "deleteOpenPosition", "deleteAllOpenPositions",
    "deleteOrderByOrderID", "deleteAllOrders", "patchOrderByOrderId",
    "optionExercise", "optionDoNotExercise",
}


def build_reviewer_server() -> FastMCP:
    assert READ_ONLY_TRADING_OPS.isdisjoint(FORBIDDEN_OPS)

    auth_headers = _build_auth_headers()
    paper = os.environ.get("ALPACA_PAPER_TRADE", "true").lower() in ("true", "1", "yes")
    trading_base = TRADING_API_BASE_URLS["paper" if paper else "live"]
    data_base = _ensure_scheme(os.environ.get("DATA_API_URL", MARKET_DATA_BASE_URL)).rstrip("/")

    trading_client = httpx.AsyncClient(base_url=trading_base, headers=auth_headers, timeout=30.0)
    data_client = httpx.AsyncClient(base_url=data_base, headers=auth_headers, timeout=30.0)

    main = FastMCP("Alpaca Reviewer (read-only)")
    main.add_middleware(TrustBoundaryMiddleware())

    trading_spec = _load_spec("trading-api")
    trading_sub = FastMCP.from_openapi(
        trading_spec,
        client=trading_client,
        name="Alpaca Trading (read-only)",
        mcp_names=TOOL_NAMES,
        route_map_fn=_make_filter(READ_ONLY_TRADING_OPS),
        mcp_component_fn=_make_customizer(TOOL_DESCRIPTIONS),
        validate_output=False,
    )
    main.mount(trading_sub)

    data_spec = _load_spec("market-data-api")
    data_sub = FastMCP.from_openapi(
        data_spec,
        client=data_client,
        name="Alpaca Market Data",
        mcp_names=TOOL_NAMES,
        route_map_fn=_make_filter(READ_ONLY_MARKET_DATA_OPS),
        mcp_component_fn=_make_customizer(TOOL_DESCRIPTIONS),
        validate_output=False,
    )
    main.mount(data_sub)

    # Historical-bar override tools (StockBars/CryptoBars convenience wrappers) are
    # read-only; register_order_tools (place_option_order etc.) is never called.
    register_market_data_tools(main, data_client)
    register_readme_docs_tools(main)

    return main


def main() -> None:
    server = build_reviewer_server()
    server.run()


if __name__ == "__main__":
    main()
