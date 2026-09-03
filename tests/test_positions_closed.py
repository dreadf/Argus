"""
pytest coverage for pipeline/execution/positions.py's closed_spread_positions
and closed_position_stats -- pure functions over a plain DataFrame, no
broker connection, no credentials. Mirrors open_spread_positions()'s
existing test style (see its own __main__ self-check) rather than
introducing a new pattern.
"""

from __future__ import annotations

import pandas as pd

from pipeline.execution.positions import closed_position_stats, closed_spread_positions

PAIR_A = ("SPY260909P00746000", "SPY260909P00745000")
PAIR_B = ("SPY260916P00740000", "SPY260916P00739000")


def _row(**kwargs):
    base = {"outcome": None, "short_symbol": None, "long_symbol": None}
    base.update(kwargs)
    return base


def test_empty_log_has_no_closed_positions():
    assert closed_spread_positions(pd.DataFrame(columns=["outcome", "short_symbol", "long_symbol"])) == []
    stats = closed_position_stats(pd.DataFrame(columns=["outcome", "short_symbol", "long_symbol"]))
    assert stats == {"n_closed": 0, "n_with_pnl": 0, "total_realized_pnl": 0, "wins": 0, "losses": 0, "win_rate": None}


def test_open_position_with_no_close_is_not_listed():
    log = pd.DataFrame([
        _row(timestamp="2026-09-01T16:38:25", outcome="SOLD", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             proposed_contracts=6, proposed_credit=22.0),
    ])
    assert closed_spread_positions(log) == []


def test_closed_position_joins_entry_economics_and_realized_pnl():
    log = pd.DataFrame([
        _row(timestamp="2026-09-01T16:38:25", outcome="SOLD", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             proposed_contracts=6, proposed_credit=22.0),
        _row(timestamp="2026-09-02T15:00:00", outcome="CLOSED", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             close_reason="close_profit_target", realized_pnl=126.0),
    ])
    closed = closed_spread_positions(log)
    assert len(closed) == 1
    assert closed[0]["contracts"] == 6
    assert closed[0]["credit_per_contract"] == 22.0
    assert closed[0]["close_reason"] == "close_profit_target"
    assert closed[0]["realized_pnl"] == 126.0


def test_reprice_prefers_filled_row_economics_same_as_open_positions():
    log = pd.DataFrame([
        _row(timestamp="2026-09-01T16:38:25", outcome="SOLD", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             proposed_contracts=6, proposed_credit=27.0),
        _row(timestamp="2026-09-01T17:20:30", outcome="FILLED", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             proposed_contracts=6, proposed_credit=22.0),
        _row(timestamp="2026-09-02T15:00:00", outcome="CLOSED", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             close_reason="close_profit_target", realized_pnl=126.0),
    ])
    closed = closed_spread_positions(log)
    assert closed[0]["credit_per_contract"] == 22.0


def test_realized_pnl_none_when_not_computable_and_not_treated_as_zero():
    """An emergency close never logs a realized_pnl. Must surface as None,
    not silently zero, so downstream stats can distinguish "we don't know"
    from "broke even"."""
    log = pd.DataFrame([
        _row(timestamp="2026-09-01T16:38:25", outcome="SOLD", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             proposed_contracts=6, proposed_credit=22.0),
        _row(timestamp="2026-09-02T15:00:00", outcome="CLOSED", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             close_reason="emergency_close_orphan", realized_pnl=None),
    ])
    closed = closed_spread_positions(log)
    assert closed[0]["realized_pnl"] is None


def test_stats_aggregate_across_multiple_closed_positions_and_exclude_none_from_the_average():
    log = pd.DataFrame([
        _row(timestamp="2026-09-01T10:00:00", outcome="SOLD", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             proposed_contracts=6, proposed_credit=22.0),
        _row(timestamp="2026-09-02T10:00:00", outcome="CLOSED", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             close_reason="close_profit_target", realized_pnl=126.0),
        _row(timestamp="2026-09-03T10:00:00", outcome="SOLD", short_symbol=PAIR_B[0], long_symbol=PAIR_B[1],
             proposed_contracts=4, proposed_credit=15.0),
        _row(timestamp="2026-09-04T10:00:00", outcome="CLOSED", short_symbol=PAIR_B[0], long_symbol=PAIR_B[1],
             close_reason="close_expiry_day_rule", realized_pnl=-20.0),
    ])
    stats = closed_position_stats(log)
    assert stats["n_closed"] == 2
    assert stats["n_with_pnl"] == 2
    assert stats["total_realized_pnl"] == 106.0
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["win_rate"] == 0.5


def test_stats_report_partial_pnl_coverage_honestly():
    """One closed position has a known P&L, one (emergency close) does not.
    n_with_pnl must show 1 of 2, not silently average over a zeroed gap."""
    log = pd.DataFrame([
        _row(timestamp="2026-09-01T10:00:00", outcome="SOLD", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             proposed_contracts=6, proposed_credit=22.0),
        _row(timestamp="2026-09-02T10:00:00", outcome="CLOSED", short_symbol=PAIR_A[0], long_symbol=PAIR_A[1],
             close_reason="close_profit_target", realized_pnl=126.0),
        _row(timestamp="2026-09-03T10:00:00", outcome="SOLD", short_symbol=PAIR_B[0], long_symbol=PAIR_B[1],
             proposed_contracts=4, proposed_credit=15.0),
        _row(timestamp="2026-09-04T10:00:00", outcome="CLOSED", short_symbol=PAIR_B[0], long_symbol=PAIR_B[1],
             close_reason="emergency_close_orphan", realized_pnl=None),
    ])
    stats = closed_position_stats(log)
    assert stats["n_closed"] == 2
    assert stats["n_with_pnl"] == 1
    assert stats["total_realized_pnl"] == 126.0
    assert stats["win_rate"] == 1.0
