"""
W6: exposes the falsification engine as read-only MCP tools.

register_falsify_tools(server) is one additive call on an existing FastMCP
server -- revertible by deleting that one line wherever it's called from.
This module defines no server of its own and opens no account/order
access; every tool here either recomputes a published figure fresh from
already-committed data, or reads the append-only hypotheses ledger. There
is no tool defined here that writes anything except that ledger (via the
same _log_entry path W3's propose.py already uses), and none that can
place, cancel, or modify an order -- the same non-negotiable property
pipeline/mcp/reviewer_server.py's own docstring states for the Reviewer's
MCP surface.

Four tools, matching the session plan's W6 item exactly:

  - deflated_sharpe(): today's headline DSR (variants B/C), recomputed via
    pipeline.falsify.audit.run_audit(), never cached across calls -- so a
    caller always sees the CURRENT trial count's number, not a stale one.
  - false_trip_rate(guard, distance, width): replays one of the three
    guards pipeline.risk.false_trip.py already tests against real
    historical winning weeks.
  - list_killed_hypotheses(limit): summarizes output/falsify/hypotheses
    .jsonl (W3's ledger) -- survived/killed counts and the most recent
    entries.
  - falsify(signal_name, percentile, n_permutations): runs ONE hypothesis
    from the same pre-registered signal menu propose.py uses (never a
    formula, never eval'd) through the real gauntlet against real data,
    on demand. Also appends to the ledger, exactly like propose.py's own
    loop -- an MCP-driven test costs the same N as an autonomous one.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from fastmcp import FastMCP

from pipeline.falsify.engine import Hypothesis, falsify as _falsify
from pipeline.falsify.propose import (
    HYPOTHESES_LOG_PATH,
    SIGNAL_NAMES,
    _log_entry,
    _now,
    _signal_library,
    _validate_proposal,
    load_real_data,
)


def _readonly(title: str) -> dict:
    return {"title": title, "readOnlyHint": True, "openWorldHint": False}


def register_falsify_tools(server: FastMCP) -> None:
    """Registers the four tools below on `server`. Call once, additively,
    from wherever a server is assembled (e.g. an MCP surface for the
    Proposer, distinct from reviewer_server.py's Reviewer-only surface)."""

    @server.tool(annotations=_readonly("Deflated Sharpe Ratio (current headline)"))
    def deflated_sharpe() -> dict:
        """Recomputes this project's current headline Deflated Sharpe Ratio
        (variants B and C, per Experiment 29) fresh, at the live trial
        count -- never a cached or hardcoded number, so this always
        reflects whatever has been tested against this data as of the
        moment it's called, including anything this run's own falsify()
        tool has added to the ledger."""
        from pipeline.falsify.audit import run_audit

        report = run_audit()
        return {
            "headline_n": report["headline_n"],
            "variant_b": {
                "sharpe": report["variant_b"]["sharpe"],
                "dsr": report["variant_b"]["dsr_headline"],
            },
            "variant_c": {
                "sharpe": report["variant_c"]["sharpe"],
                "dsr": report["variant_c"]["dsr_headline"],
            },
        }

    @server.tool(annotations=_readonly("False-trip rate for one guard"))
    def false_trip_rate(guard: str, distance: float = 0.03, width: float = 5.0) -> dict:
        """Replays a named guard against real historical WINNING weeks and
        reports what fraction it would have blocked -- >30% means the
        guard is mis-set (Part 6's bar, pipeline/risk/options_config.py's
        FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT).

        `guard` must be one of: "credit_width", "vol_regime",
        "term_structure". Any other value is an error, not a guess.

        Validated BEFORE any import that could touch real data: importing
        pipeline.risk.false_trip pulls in pipeline.options.vol, which
        constructs a live Alpaca client at ITS OWN module import time
        (same anti-pattern this session already fixed twice elsewhere,
        found here transitively -- pipeline/options/ is outside this
        session's territory, so it's flagged, not fixed, here). Checking
        the guard name first means an invalid guard never pays that
        import cost or needs credentials at all."""
        known_guards = ("credit_width", "vol_regime", "term_structure")
        if guard not in known_guards:
            return {"error": f"guard {guard!r} not recognized; must be one of {sorted(known_guards)}"}

        from pipeline.backtest.spread_backtest import _load_spy_closes
        from pipeline.io_utils import coerce_win_column
        from pipeline.risk import false_trip as ft

        dispatch = {
            "credit_width": lambda results, spy: ft.false_trip_rate_credit_width(results, distance, width),
            "vol_regime": lambda results, spy: ft.false_trip_rate_vol_regime(results, spy, distance, width),
            "term_structure": lambda results, spy: ft.false_trip_rate_term_structure(results, distance, width),
        }
        results = coerce_win_column(pd.read_csv("output/data/spread_backtest_results.csv"))
        spy_closes = _load_spy_closes()
        spy_closes.index = pd.to_datetime(list(spy_closes.index))

        result = dispatch[guard](results, spy_closes)
        # by_regime (term_structure only) is a DataFrame -- not JSON-safe as-is.
        if "by_regime" in result and hasattr(result["by_regime"], "to_dict"):
            result = dict(result)
            result["by_regime"] = result["by_regime"].reset_index().to_dict(orient="records")
        return result

    @server.tool(annotations=_readonly("Summarize the hypotheses ledger"))
    def list_killed_hypotheses(limit: int = 20) -> dict:
        """Summarizes output/falsify/hypotheses.jsonl -- every hypothesis
        this project's LLM-proposal loop (W3) or the falsify() tool below
        has ever tried, survived or killed, and where. `limit` caps how
        many of the most recent entries are returned in full; the counts
        cover the whole ledger regardless of `limit`."""
        path = Path(HYPOTHESES_LOG_PATH)
        if not path.exists():
            return {"n_total": 0, "n_survived": 0, "n_killed": 0, "killed_at_counts": {}, "recent": []}

        entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        survived = [e for e in entries if e.get("verdict") and e["verdict"]["survived"]]
        killed = [e for e in entries if e.get("verdict") and not e["verdict"]["survived"]]
        killed_at_counts: dict[str, int] = {}
        for e in killed:
            stage = e["verdict"]["killed_at"]
            killed_at_counts[stage] = killed_at_counts.get(stage, 0) + 1

        return {
            "n_total": len(entries),
            "n_survived": len(survived),
            "n_killed": len(killed),
            "n_errored": sum(1 for e in entries if e.get("error")),
            "killed_at_counts": killed_at_counts,
            "recent": entries[-limit:],
        }

    @server.tool(annotations={"title": "Falsify a hypothesis", "readOnlyHint": False, "openWorldHint": False})
    def falsify(signal_name: str, percentile: float, n_permutations: int = 500) -> dict:
        """Runs ONE hypothesis through the real falsification gauntlet
        against real, currently-committed project data, and appends the
        result to output/falsify/hypotheses.jsonl -- this costs this
        project's trial count exactly like an autonomous W3 iteration
        does; there is no free look. `signal_name` must be one of the
        pre-registered menu names this tool reports back on error (never
        a formula -- nothing here is eval'd or exec'd). `percentile` must
        be strictly between 0 and 1."""
        proposal = {"signal_name": signal_name, "percentile": percentile, "reason": "requested via MCP falsify tool"}
        error = _validate_proposal(proposal, list(SIGNAL_NAMES))
        if error is not None:
            return {"error": error, "available_signals": list(SIGNAL_NAMES)}

        data = load_real_data()
        library = _signal_library(data)
        hyp = Hypothesis(
            name=f"{signal_name}@p{percentile:.2f}",
            description=proposal["reason"],
            signal=library[signal_name],
            pnl=data["pnl"],
        )
        verdict = _falsify(hyp, n_permutations=n_permutations)
        entry = {"iteration": None, "timestamp": _now(), "proposal": proposal,
                  "verdict": asdict(verdict), "error": None, "source": "mcp_tool"}
        _log_entry(entry, HYPOTHESES_LOG_PATH)
        return entry
