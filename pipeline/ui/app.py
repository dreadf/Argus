"""
Streamlit dashboard. Deliberately reads from FILES (the committed backtest
and evidence-gate CSVs, the audit log) rather than requiring a live trade to
have happened -- so the public URL always has real content, even on a fresh
deploy with zero positions and before market open (Part 7's design: "the
dashboard's headline content comes from the backtest, which exists before
any trade does").

CONTROLS_ENABLED gates write actions. No write actions exist anywhere in
this codebase (confirmed -- the flag has never gated a real button); it's
wired for a future write action to check, not a currently-missing feature.

Every section is wrapped so a missing file, a broker error, or an empty log
renders a plain message instead of a stack trace (Verification #22, the
cold-open drill).

Layout, third rewrite. First version: four equally-weighted sections in
one long scroll, no signal for what mattered. Second version: added a
status hero + tabs, but Overview alone still carried 3 headers, ~9
metrics, a table, and several free-text bullet blocks -- fixed the
"everything on one screen" problem but created "everything on one tab"
instead, still reading as scattered rather than designed. This version
cuts hard: one status LINE (not a 3-line stacked block) above the tabs,
Overview reduced to a single bordered group of metrics plus one summary
sentence (no separate headers, no bullet essays), and Evidence merged
into Track record since both serve the same "why trust this" purpose --
four tabs instead of five, each with one clear job.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Streamlit Cloud's launch context doesn't put the repo root on sys.path the
# way `streamlit run` from the repo root locally does -- confirmed via a
# real deploy log: ModuleNotFoundError: No module named 'pipeline' at the
# `pipeline.audit.log` import below. Must run before any pipeline.* import.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from pipeline.audit.log import read_log
from pipeline.risk.options_config import MAX_CONCURRENT_POSITIONS

CONTROLS_ENABLED = os.getenv("CONTROLS_ENABLED", "false").lower() in ("true", "1", "yes")

st.set_page_config(page_title="Evidence Gate", page_icon="📉", layout="wide")

# Design tokens: a warm-neutral "instrument panel" palette (amber accent,
# tied to the subject -- the color of a volatility warning) set in
# .streamlit/config.toml; native widgets read that directly. This block
# is typography plus ONE status line -- deliberately not a card, not a
# badge, just text, since the fix requested here is fewer competing
# elements, not different colors on the same amount of stuff.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap');

    html, body, [class*="css"] { font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif; }

    [data-testid="stMetricValue"] {
        font-family: 'IBM Plex Mono', 'SF Mono', monospace;
        font-variant-numeric: tabular-nums;
        font-weight: 500;
    }
    [data-testid="stMetricLabel"] { font-size: 0.78rem; color: #93897A; }

    h1.page-title {
        font-family: 'Fraunces', Georgia, serif;
        font-weight: 600;
        font-size: 1.7rem;
        margin-bottom: 0.1rem;
        display: inline;
    }
    .mode-text { color: #6B6357; font-size: 0.85rem; margin-left: 0.6rem; }
    h2, h3 { font-weight: 600; }

    .status-line { font-size: 0.98rem; margin: 0.9rem 0 1.3rem 0; color: #C7BFAF; }
    .status-line .word { font-weight: 600; }
    .status-line .word.good { color: #5B8A5A; }
    .status-line .word.caution { color: #B5502E; }
    .status-line .word.danger { color: #9C3B3B; }
    .status-line .word.neutral { color: #93897A; }
    .status-line .time { color: #6B6357; font-size: 0.85em; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f'<h1 class="page-title">Evidence Gate</h1>'
    f'<span class="mode-text">{"Controls enabled, local session" if CONTROLS_ENABLED else "Read-only, public deployment"}</span>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Load everything up front, once (None on any failure) -- the status line
# and every tab below reuse these, nothing fetched or parsed twice.
# ---------------------------------------------------------------------------
account_state = None
try:
    from pipeline.execution.broker import get_account_state
    from pipeline.execution.positions import open_spread_positions

    account_state = get_account_state(open_positions=open_spread_positions())
except Exception as e:
    account_error = str(e)
else:
    account_error = None

log_df = None
try:
    log_df = read_log()
except Exception as e:
    log_error = str(e)
else:
    log_error = None

curve_df = None
curve_path = "output/data/equity_curve.csv"
try:
    if os.path.exists(curve_path):
        curve_df = pd.read_csv(curve_path, parse_dates=["entry"]).set_index("entry")
except Exception as e:
    curve_error = str(e)
else:
    curve_error = None

today_snapshot = None
try:
    from pipeline.data.vix import contango_ratio, current_contango_and_threshold, load_cached_vix, refresh_vix_cache
    from pipeline.options.chain import get_spot
    from pipeline.options.vol import fetch_recent_closes

    _spot = get_spot()
    _closes = fetch_recent_closes()
    # A fresh Streamlit Cloud container has no cache file on disk at all
    # (gitignored, same as the audit log) -- refresh before reading, same
    # order run_agent.py uses, so this self-heals instead of erroring.
    refresh_vix_cache()
    _vix9d = load_cached_vix("VIX9D")
    _vix3m = load_cached_vix("VIX3M")
    _, _contango_threshold = current_contango_and_threshold()
    today_snapshot = {
        "spot": _spot,
        "yesterday_move_pct": float(_closes.pct_change().iloc[-1]),
        "contango": float(contango_ratio(_vix9d, _vix3m).iloc[-1]),
        "contango_threshold": _contango_threshold,
    }
except Exception as e:
    snapshot_error = str(e)
else:
    snapshot_error = None

gate_df, gate_choice = None, None
gate_path = "output/data/evidence_gate_results.csv"
try:
    if os.path.exists(gate_path):
        gate_df = pd.read_csv(gate_path)
        from pipeline.options.selector import choose_distance_width

        gate_choice = choose_distance_width(gate_df)
except Exception as e:
    gate_error = str(e)
else:
    gate_error = None


def _max_dd(s: pd.Series) -> float:
    return float((s.cummax() - s).max())


def _worst_year(df: pd.DataFrame, col: str) -> tuple[int, float]:
    by_year = df.groupby(df.index.year)[col].sum()
    return int(by_year.idxmin()), float(by_year.min())


# ---------------------------------------------------------------------------
# Status line: ONE sentence, not a stacked label/headline/meta block.
# Derived from the most recent logged decision -- says exactly what the
# audit log says happened, nothing computed fresh.
# ---------------------------------------------------------------------------
def _status_line(log_df: pd.DataFrame | None) -> tuple[str, str, str, str]:
    """Returns (semantic_class, word, rest_of_sentence, timestamp)."""
    if log_df is None:
        return "neutral", "Status unknown", "could not read the decision log.", ""
    if log_df.empty:
        return "neutral", "Not yet run", "no decisions logged today.", ""

    latest = log_df.sort_values("timestamp", ascending=False).iloc[0]
    outcome = latest.get("outcome")
    ts = str(latest.get("timestamp", ""))

    if outcome == "SOLD":
        n = int(latest["proposed_contracts"]) if pd.notna(latest.get("proposed_contracts")) else "?"
        return ("good", "Trading",
                f"opened {latest.get('short_symbol')} / {latest.get('long_symbol')}, {n} contract(s).", ts)
    if outcome == "DRY_RUN":
        return ("neutral", "Dry run",
                f"would have opened {latest.get('short_symbol')} / {latest.get('long_symbol')} -- no real order sent.", ts)
    if outcome == "SKIPPED":
        reasons = latest.get("guards_failed")
        reason_text = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) and reasons else "no reason recorded."
        return ("caution", "Declined to trade", reason_text, ts)
    if outcome == "CLOSED":
        return ("neutral", "Position closed", str(latest.get("close_reason", "")), ts)
    if outcome == "EMERGENCY_CLOSE_ORPHAN":
        return ("danger", "Emergency close", str(latest.get("close_reason", "")), ts)
    return ("neutral", str(outcome), "", ts)


status_class, status_word, status_rest, status_ts = _status_line(log_df)
time_html = f' <span class="time">({status_ts})</span>' if status_ts else ""
st.markdown(
    f'<p class="status-line"><span class="word {status_class}">{status_word}</span> &mdash; {status_rest}{time_html}</p>',
    unsafe_allow_html=True,
)

tab_overview, tab_track_record, tab_log, tab_how = st.tabs(
    ["Overview", "Track record", "Decision log", "How it works"]
)

# ---------------------------------------------------------------------------
# Overview: today, and only today. One group of numbers, one summary
# sentence. The historical pitch lives entirely in Track record -- not
# duplicated here, so this tab has exactly one job.
# ---------------------------------------------------------------------------
with tab_overview:
    n_open = len(account_state.get("raw_positions") or []) if account_state is not None else 0

    with st.container(border=True):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("SPY spot", f"${today_snapshot['spot']:.2f}" if today_snapshot else "-")
        col2.metric("Yesterday's move", f"{today_snapshot['yesterday_move_pct']:+.2%}" if today_snapshot else "-",
                    help="The gap-risk guard blocks a new trade above 2% in either direction.")
        col3.metric("Contango (VIX3M/VIX9D)", f"{today_snapshot['contango']:.3f}" if today_snapshot else "-",
                    help="Below its own trailing 33rd percentile means the term structure is flattening -- the guard blocks a new trade.")
        col4.metric("Positions open", f"{n_open} of {MAX_CONCURRENT_POSITIONS}")

        if snapshot_error is not None:
            st.caption(f"Live market data unavailable right now ({snapshot_error}).")
        elif today_snapshot is not None:
            s = today_snapshot
            blocks = []
            if abs(s["yesterday_move_pct"]) > 0.02:
                blocks.append(f"SPY moved {s['yesterday_move_pct']:+.1%} yesterday")
            if s["contango_threshold"] is not None and s["contango"] < s["contango_threshold"]:
                blocks.append(f"term structure is flattening ({s['contango']:.3f} < {s['contango_threshold']:.3f})")
            if blocks:
                st.caption("Would block a new trade today: " + "; ".join(blocks) + ".")
            else:
                st.caption("Nothing here would block a new trade today.")

    if account_error is not None:
        st.caption(f"Live account data unavailable right now ({account_error}).")
    elif n_open > 0:
        rows = [{
            "symbol": p.symbol, "side": str(p.side).replace("PositionSide.", ""), "qty": p.qty,
            "avg entry": f"${float(p.avg_entry_price):.2f}",
            "unrealized P&L": f"${float(p.unrealized_pl):+,.2f}" if p.unrealized_pl is not None else "-",
        } for p in account_state["raw_positions"]]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Track record: the entire "why trust this" case in one place -- the
# ten-year chart, its supporting stats, and today's evidence-gate pick,
# with the full 24-row sweep one click away. Evidence used to be a
# separate tab; merged here since both serve the same reader.
# ---------------------------------------------------------------------------
with tab_track_record:
    if curve_error is not None:
        st.error(f"Could not render the equity curve ({curve_error}).")
    elif curve_df is None:
        st.warning("Reconstruction has not been computed yet. Run `python -m pipeline.backtest.reconstruct`.")
    else:
        st.caption(
            "Cumulative P&L per contract, $, 2016-2026 -- trade every week vs. the VIX term-structure filter. "
            "Fees before Feb 2024 are reconstructed from VIX9D and validated per volatility quartile (`EXPERIMENT.md`, Exp. 12d)."
        )
        st.line_chart(
            curve_df[["cum_pnl_unfiltered", "cum_pnl_filtered"]].rename(columns={
                "cum_pnl_unfiltered": "trade every week", "cum_pnl_filtered": "VIX filter",
            }),
            color=["#C9722E", "#5B8A5A"],
        )

        dd_u, dd_f = _max_dd(curve_df["cum_pnl_unfiltered"]), _max_dd(curve_df["cum_pnl_filtered"])
        wy_u, wy_f = _worst_year(curve_df, "pnl_unfiltered"), _worst_year(curve_df, "pnl_filtered")
        weeks_traded = int(curve_df["traded"].sum())

        col1, col2, col3 = st.columns(3)
        col1.metric("Max drawdown, $/contract", f"{dd_f:.2f}", delta=f"{dd_f - dd_u:+.2f} vs. unfiltered", delta_color="inverse")
        col2.metric("Worst year, filtered", f"{wy_f[1]:+.2f}", help=f"Year {wy_f[0]}. Unfiltered: {wy_u[1]:+.2f} in {wy_u[0]}.")
        col3.metric("Weeks traded", f"{weeks_traded} of {len(curve_df)}")

        with st.expander("SPY and cash, for shape comparison (indexed, not dollar-matched)"):
            st.line_chart(
                curve_df[["spy_indexed", "cash_indexed"]].rename(columns={
                    "spy_indexed": "SPY (indexed)", "cash_indexed": "cash @ 3%/yr (indexed)",
                }),
                color=["#93897A", "#4A4438"],
            )

    st.divider()

    if gate_error is not None:
        st.error(f"Could not render the evidence gate ({gate_error}).")
    elif gate_df is None:
        st.warning("Evidence gate not computed yet.")
    else:
        n_survivors = int(gate_df["passes_gate"].sum())
        if gate_choice is None:
            st.warning("No (distance, width) combination currently clears the 2-SE evidence bar -- the system declines to trade, on purpose.")
        else:
            st.success(
                f"Today's pick: **{gate_choice['distance']:.0%} distance, ${gate_choice['width']:.0f} width**, "
                f"cushion **{gate_choice['cushion_se']:.2f} SE** ({n_survivors} of {len(gate_df)} combinations qualify)."
            )
        with st.expander(f"See all {len(gate_df)} combinations tested"):
            display_df = gate_df.copy()
            display_df["distance"] = (display_df["distance"] * 100).round(0).astype(int).astype(str) + "%"
            display_df["width"] = "$" + display_df["width"].astype(int).astype(str)
            display_cols = ["distance", "width", "n", "win_rate", "required_win_rate", "cushion_se", "mean_net_pnl", "passes_gate"]
            styled = display_df[display_cols].rename(columns={
                "n": "weeks", "win_rate": "measured win rate", "required_win_rate": "breakeven win rate",
                "cushion_se": "cushion (SE)", "mean_net_pnl": "mean P&L/contract", "passes_gate": "clears 2 SE",
            })
            st.dataframe(styled, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Decision log: last 10 in plain language, full audit trail one click away.
# ---------------------------------------------------------------------------
with tab_log:
    if log_error is not None:
        st.error(f"Could not render the decision log ({log_error}).")
    elif log_df is None or log_df.empty:
        st.write("No decisions logged yet. Every day the agent runs -- including a day it declines to trade -- gets a row here.")
    else:
        recent = log_df.sort_values("timestamp", ascending=False).head(10).copy()

        def _reason(row) -> str:
            if row.get("outcome") == "SOLD":
                return f"{row.get('short_symbol')} / {row.get('long_symbol')}, {row.get('proposed_contracts')} contract(s)"
            if row.get("outcome") == "SKIPPED":
                reasons = row.get("guards_failed")
                return "; ".join(str(r) for r in reasons) if isinstance(reasons, list) and reasons else ""
            if row.get("outcome") == "CLOSED":
                return str(row.get("close_reason", ""))
            return ""

        recent["reason"] = recent.apply(_reason, axis=1)
        st.dataframe(recent[["timestamp", "mode", "outcome", "reason"]], width="stretch", hide_index=True)

        with st.expander(f"Full audit trail ({len(log_df)} rows, every field)"):
            st.dataframe(log_df.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# How it works: a real sequence, so numbering here encodes something true.
# ---------------------------------------------------------------------------
with tab_how:
    st.markdown(
        """
1. **Picker** -- fixed rules, calibrated from the ten-year backtest, propose one trade a day. No model, no discretion.
2. **Guard** -- 15 hard safety limits check the proposal (liquidity, position caps, drawdown limits, a VIX term-structure filter). Any single failure blocks the trade, and none can be overridden downstream.
3. **Reviewer** -- an AI (Gemini) may veto or shrink a Guard-approved proposal -- never raise its size, never originate one. Enforced in code, not by the prompt.
4. **Monitor** -- every 15 minutes: a profit target, a forced close the day before expiry (assignment-risk protection), or a hard drawdown stop.
5. **Recovery** -- an unrecognized broker position or a partial fill halts trading and closes the excess risk immediately.

Full design rationale: `OPTIONS_SYSTEM_PLAN.md`. Full experiment log, including two retracted findings: `EXPERIMENT.md`.
        """
    )
