"""
Tests for pipeline/falsify/mcp_tools.py (W6): register_falsify_tools and
the four tools it defines.

Fast tests here cover registration, schema, and every code path that
doesn't need real committed data (list_killed_hypotheses against a
monkeypatched log path, false_trip_rate's/falsify's error paths on bad
input). Tests that actually recompute against real project data
(deflated_sharpe(), a real false_trip_rate() call, a real falsify() call)
are marked slow, matching this project's existing split (test_audit.py) --
they reproduce real figures end to end rather than exercising new logic.
"""

import asyncio
import json

import pytest
from fastmcp import Client, FastMCP

from pipeline.falsify import mcp_tools


def _build_server() -> FastMCP:
    server = FastMCP("test-falsify")
    mcp_tools.register_falsify_tools(server)
    return server


def _call(server: FastMCP, name: str, args: dict) -> dict:
    async def _run():
        async with Client(server) as client:
            result = await client.call_tool(name, args)
            return json.loads(result.content[0].text)

    return asyncio.run(_run())


def test_build_falsify_server_wires_the_same_four_tools():
    from pipeline.mcp.falsify_server import build_falsify_server

    server = build_falsify_server()

    async def _list():
        return await server.list_tools()

    names = {t.name for t in asyncio.run(_list())}
    assert names == {"deflated_sharpe", "false_trip_rate", "list_killed_hypotheses", "falsify"}


def test_register_falsify_tools_adds_exactly_the_four_planned_tools():
    server = _build_server()

    async def _list():
        return await server.list_tools()

    tools = asyncio.run(_list())
    names = {t.name for t in tools}
    assert names == {"deflated_sharpe", "false_trip_rate", "list_killed_hypotheses", "falsify"}


def test_falsify_tool_is_marked_not_readonly_the_others_are():
    server = _build_server()

    async def _list():
        return await server.list_tools()

    tools = {t.name: t for t in asyncio.run(_list())}
    assert tools["deflated_sharpe"].annotations.readOnlyHint is True
    assert tools["false_trip_rate"].annotations.readOnlyHint is True
    assert tools["list_killed_hypotheses"].annotations.readOnlyHint is True
    assert tools["falsify"].annotations.readOnlyHint is False  # it writes to the ledger


def test_list_killed_hypotheses_on_a_missing_ledger_returns_zeros(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_tools, "HYPOTHESES_LOG_PATH", str(tmp_path / "does_not_exist.jsonl"))
    server = _build_server()
    out = _call(server, "list_killed_hypotheses", {})
    assert out == {"n_total": 0, "n_survived": 0, "n_killed": 0, "killed_at_counts": {}, "recent": []}


def test_list_killed_hypotheses_summarizes_a_populated_ledger(tmp_path, monkeypatch):
    log_path = tmp_path / "hypotheses.jsonl"
    entries = [
        {"iteration": 0, "proposal": {"signal_name": "vrp_edge"}, "verdict": {"survived": True, "killed_at": None}, "error": None},
        {"iteration": 1, "proposal": {"signal_name": "contango"}, "verdict": {"survived": False, "killed_at": "randomization_null"}, "error": None},
        {"iteration": 2, "proposal": {"signal_name": "contango"}, "verdict": {"survived": False, "killed_at": "randomization_null"}, "error": None},
        {"iteration": 3, "proposal": {"signal_name": "bad"}, "verdict": None, "error": "not in the pre-registered menu"},
    ]
    log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    monkeypatch.setattr(mcp_tools, "HYPOTHESES_LOG_PATH", str(log_path))

    server = _build_server()
    out = _call(server, "list_killed_hypotheses", {"limit": 2})

    assert out["n_total"] == 4
    assert out["n_survived"] == 1
    assert out["n_killed"] == 2
    assert out["n_errored"] == 1
    assert out["killed_at_counts"] == {"randomization_null": 2}
    assert len(out["recent"]) == 2
    assert out["recent"][-1]["iteration"] == 3


def test_false_trip_rate_rejects_an_unrecognized_guard_without_touching_real_data():
    server = _build_server()
    out = _call(server, "false_trip_rate", {"guard": "not_a_real_guard"})
    assert "error" in out
    assert "credit_width" in out["error"] and "vol_regime" in out["error"] and "term_structure" in out["error"]


def test_falsify_tool_rejects_an_unrecognized_signal_name_without_loading_real_data(monkeypatch):
    # If this reached load_real_data() it would try to read real committed
    # CSVs/VIX cache; patching load_real_data to raise proves the
    # validation happens first for a bad signal_name.
    def _boom():
        raise AssertionError("load_real_data() should not be called for an invalid signal_name")

    monkeypatch.setattr(mcp_tools, "load_real_data", _boom)
    server = _build_server()
    out = _call(server, "falsify", {"signal_name": "made_up_signal", "percentile": 0.3})
    assert "error" in out
    assert "not in the pre-registered menu" in out["error"]


def test_falsify_tool_rejects_an_out_of_range_percentile_without_loading_real_data(monkeypatch):
    def _boom():
        raise AssertionError("load_real_data() should not be called for a bad percentile")

    monkeypatch.setattr(mcp_tools, "load_real_data", _boom)
    server = _build_server()
    out = _call(server, "falsify", {"signal_name": "vrp_edge", "percentile": 1.5})
    assert "error" in out


# --- Slow: exercise the three tools that recompute against real,
# currently-committed project data (reconstruction replay, real VIX/SPY
# history, real backtest CSV). Matches test_audit.py's split -- these
# reproduce real figures end to end rather than new logic, so they're
# excluded from the default (<10s) run. See pyproject.toml's addopts.

@pytest.mark.slow
def test_deflated_sharpe_tool_matches_a_live_audit_run():
    from pipeline.falsify.audit import run_audit

    server = _build_server()
    out = _call(server, "deflated_sharpe", {})
    report = run_audit()

    assert out["headline_n"] == report["headline_n"]
    assert out["variant_b"]["sharpe"] == pytest.approx(report["variant_b"]["sharpe"], abs=1e-9)
    assert out["variant_b"]["dsr"] == pytest.approx(report["variant_b"]["dsr_headline"], abs=1e-9)
    assert out["variant_c"]["dsr"] == pytest.approx(report["variant_c"]["dsr_headline"], abs=1e-9)


@pytest.mark.slow
def test_false_trip_rate_tool_term_structure_matches_the_direct_call():
    """A real (non-error) guard call transitively imports
    pipeline.options.vol (via pipeline.risk.false_trip), which -- outside
    this session's territory, not fixed here -- constructs a live Alpaca
    client at ITS OWN module import time, so this genuinely needs real
    credentials to even import, the same documented, accepted limitation
    SUBMISSION_CHECKLIST.md already states for pipeline.risk.false_trip
    directly ("needs Alpaca credentials to run... not this session's fix
    to make"). Skips rather than fails on a bare clone with no .env,
    exactly like reviewer.py's own REVIEWER_LIVE_TEST-gated check --
    still runs and still verified on any machine with real credentials."""
    import pandas as pd

    try:
        from pipeline.backtest.spread_backtest import _load_spy_closes
        from pipeline.io_utils import coerce_win_column
        from pipeline.risk import false_trip as ft
    except ValueError as e:
        pytest.skip(f"needs real Alpaca credentials to import (pipeline.options.vol's known, "
                    f"accepted limitation, outside this session's territory): {e}")

    server = _build_server()
    out = _call(server, "false_trip_rate", {"guard": "term_structure", "distance": 0.03, "width": 5.0})

    results = coerce_win_column(pd.read_csv("output/data/spread_backtest_results.csv"))
    spy_closes = _load_spy_closes()
    spy_closes.index = pd.to_datetime(list(spy_closes.index))
    direct = ft.false_trip_rate_term_structure(results, 0.03, 5.0)

    assert out["blocked_pct"] == pytest.approx(direct["blocked_pct"], abs=1e-9)
    assert out["n_winners"] == direct["n_winners"]
    assert isinstance(out["by_regime"], list)  # DataFrame was made JSON-safe


@pytest.mark.slow
def test_falsify_tool_runs_against_real_data_without_polluting_the_real_ledger(tmp_path, monkeypatch):
    # Critical: this must NOT write to the real output/falsify/hypotheses.jsonl
    # -- that file's line count IS this project's live trial count N (see
    # trial_count.py). A test run inflating N would be exactly the kind of
    # silent, hard-to-notice corruption this project's whole audit exists
    # to prevent.
    fake_log = tmp_path / "hypotheses.jsonl"
    monkeypatch.setattr(mcp_tools, "HYPOTHESES_LOG_PATH", str(fake_log))

    server = _build_server()
    out = _call(server, "falsify", {"signal_name": "vrp_edge", "percentile": 0.33, "n_permutations": 50})

    assert out["error"] is None
    assert out["verdict"]["hypothesis_name"] == "vrp_edge@p0.33"
    assert fake_log.exists()
    assert len(fake_log.read_text().strip().splitlines()) == 1
