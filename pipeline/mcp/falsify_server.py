"""
MCP server exposing the falsification engine (W6): deflated_sharpe,
false_trip_rate, list_killed_hypotheses, and falsify (see
pipeline/falsify/mcp_tools.py for what each does).

Deliberately a SEPARATE server from pipeline/mcp/reviewer_server.py, not
one more registration call bolted onto it. reviewer_server.py's own
docstring states it is read-only and gates live order review; this
server's falsify tool is NOT read-only (it appends to
output/falsify/hypotheses.jsonl), so mounting it there would make that
file's own "read-only" claim false. Keeping them separate means
reviewer_server.py needed zero changes for W6 to exist -- the Reviewer's
safety surface is untouched.

No Alpaca account/order access of any kind: every tool here operates on
already-committed local data (CSVs, cached VIX history, the hypotheses
ledger) or the falsification engine itself. There is no client, no auth
headers, nothing to close on shutdown -- unlike build_reviewer_server(),
this one needs no aclose_* counterpart.

Run with: python -m pipeline.mcp.falsify_server
"""

from __future__ import annotations

from fastmcp import FastMCP

from pipeline.falsify.mcp_tools import register_falsify_tools


def build_falsify_server() -> FastMCP:
    server = FastMCP("Falsification Engine")
    register_falsify_tools(server)
    return server


def main() -> None:
    server = build_falsify_server()
    server.run()


if __name__ == "__main__":
    main()
