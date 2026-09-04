"""
Streamlit dashboard -- the LOCAL ADMIN CONSOLE (CONTROLS_ENABLED=true). The
public-facing dashboard is now the static site in public/ (Vercel); this
file is never deployed publicly, only run locally by the operator.

Content parity with public/: this file renders from the SAME four functions
(scripts.export_dashboard_data.build_overview/build_track_record/
build_decisions/build_evidence) that produce public/data/*.json for the
Vercel site -- not a separate re-derivation of the same numbers. Two things
stay genuinely live-and-separate in both places: the direct Alpaca
account/positions fetch (Vercel: api/account.py; here: get_account_state),
and the research-track vol_forecast call (no export script wires that one
up yet). Direct feedback after an earlier round drifted the two dashboards
apart in both palette and content: "the layout needs to be identical, the
numbers and the visualization needs to be identical... the visual
hierarchy, the content, the placement, the tabs are all the same." Card
chrome (exact borders/shadows) is allowed to differ -- Streamlit's
component model can't be pixel-identical to hand-built HTML/CSS.

Every section is wrapped so a missing file, a broker error, or an empty log
renders a plain message instead of a stack trace (Verification #22, the
cold-open drill).
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

# Streamlit Cloud's launch context doesn't put the repo root on sys.path the
# way `streamlit run` from the repo root locally does -- confirmed via a
# real deploy log: ModuleNotFoundError: No module named 'pipeline' at the
# `pipeline.audit.log` import below. Must run before any pipeline.* import.
# Also puts scripts/ (an implicit namespace package, no __init__.py needed)
# on the path for build_overview() etc. below.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from pipeline.audit.log import read_log
from scripts.export_dashboard_data import build_decisions, build_evidence, build_overview, build_track_record

CONTROLS_ENABLED = os.getenv("CONTROLS_ENABLED", "false").lower() in ("true", "1", "yes")

st.set_page_config(page_title="Argus", page_icon="📉", layout="wide")

# Design tokens matched token-for-token to public/style.css's :root block, so
# this reads as the same product's operator view, not a different tool.
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
    [data-testid="stMetricLabel"] { font-size: 0.78rem; color: #8B98A0; }

    h1.page-title { font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 1.7rem; margin-bottom: 0.1rem; display: inline; }
    .mode-text { color: #63707A; font-size: 0.85rem; margin-left: 0.6rem; }

    .status-line { font-size: 0.98rem; margin: 0.9rem 0 1.2rem 0; color: #C5CFD4; }
    .status-line .word { font-weight: 600; }
    .status-line .word.good { color: #5FBF95; }
    .status-line .word.bad { color: #E2726E; }
    .status-line .word.neutral { color: #8B98A0; }
    .status-line .time { color: #63707A; font-size: 0.85em; }

    .card-title { font-family: 'IBM Plex Mono', monospace; font-size: 0.74rem; letter-spacing: 0.07em; text-transform: uppercase; color: #E7ECEF; font-weight: 600; }
    .card-subtitle { font-size: 0.82rem; color: #8B98A0; margin: 0.1rem 0 0.7rem 0; }
    .card-section-label { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; color: #63707A; margin: 0 0 0.7rem 0; }
    .card-note { font-size: 0.86rem; color: #C5CFD4; margin: 0.6rem 0 0; }
    .card-note.good { color: #5FBF95; }
    .card-note.bad { color: #E2726E; }

    /* KPI tile: one large headline number (Account card's Equity). */
    .kpi-row { display: flex; gap: 0.8rem; margin-bottom: 1rem; }
    .kpi-tile { background: transparent; border: 1px solid #2A3238; border-left: 3px solid #4FBDBA; border-radius: 8px; padding: 0.75rem 1rem; flex: 1; }
    .kpi-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #8B98A0; margin-bottom: 0.3rem; }
    .kpi-value { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; font-size: 1.75rem; font-weight: 600; line-height: 1.15; color: #E7ECEF; }

    /* Metric tile: smaller supporting numbers (a metric-row of several). */
    .metric-row { display: flex; flex-wrap: wrap; gap: 0.7rem; margin-bottom: 1rem; }
    .metric-tile { background: transparent; border: 1px solid #2A3238; border-left: 3px solid #2A3238; border-radius: 8px; padding: 0.6rem 0.85rem; flex: 1; min-width: 9.5rem; }
    .metric-tile.accent { border-left-color: #4FBDBA; }
    .metric-tile.good { border-left-color: #5FBF95; }
    .metric-tile.bad { border-left-color: #E2726E; }
    .metric-label { font-size: 0.76rem; color: #8B98A0; margin-bottom: 0.15rem; }
    .metric-value { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; font-size: 1.2rem; font-weight: 500; color: #E7ECEF; }
    .metric-value.good { color: #5FBF95; }
    .metric-value.bad { color: #E2726E; }
    .metric-help { font-size: 0.76rem; color: #63707A; margin-top: 0.15rem; }

    /* "Today, in plain terms" narrative lines. */
    .narrative-line { display: grid; grid-template-columns: 11.5rem 1fr; gap: 0.9rem; padding: 0.45rem 0; align-items: baseline; }
    .narrative-label { font-weight: 700; }
    .narrative-label.good { color: #5FBF95; }
    .narrative-label.bad { color: #E2726E; }
    .narrative-label.neutral { color: #8B98A0; }
    .narrative-detail { font-size: 0.92rem; color: #C5CFD4; }

    /* Volatility "equation" -- value / value = ratio -> verdict, one line. */
    .equation { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; font-size: 1rem; margin-bottom: 0.5rem; }
    .equation-box { background: transparent; border: 1px solid #2A3238; border-left: 3px solid #2A3238; border-radius: 8px; padding: 0.85rem 1rem; }
    .equation-box.good { border-left-color: #5FBF95; }
    .equation-box.bad { border-left-color: #E2726E; }
    .equation-box.neutral { border-left-color: #2A3238; }
    .equation .eq-item { display: flex; align-items: baseline; gap: 0.35rem; }
    .equation .eq-label { font-size: 0.78rem; color: #8B98A0; }
    .equation .eq-val { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; font-weight: 600; color: #E7ECEF; }
    .equation .eq-op { color: #63707A; font-size: 1.05rem; }
    .equation .eq-verdict { font-weight: 700; padding: 0.15rem 0.65rem; border-radius: 999px; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.03em; }
    .equation .eq-verdict.good { color: #06201F; background: #5FBF95; }
    .equation .eq-verdict.bad { color: #2B0906; background: #E2726E; }
    .equation .eq-verdict.neutral { color: #E7ECEF; background: #2A3238; }

    .path-row { display: flex; align-items: baseline; gap: 0.7rem; padding: 0.35rem 0; border-bottom: 1px solid #2A3238; flex-wrap: wrap; }
    .path-row:last-child { border-bottom: none; }
    .path-stage { font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: #63707A; width: 6.5rem; flex-shrink: 0; }
    .path-word { font-weight: 600; width: 7rem; flex-shrink: 0; }
    .path-word.good { color: #5FBF95; }
    .path-word.bad { color: #E2726E; }
    .path-word.neutral { color: #8B98A0; }
    .path-detail { font-size: 0.86rem; color: #C5CFD4; }

    /* Vertical stepper -- ported verbatim from public/style.css so "How it
       works" is the same diagram, not a redrawn one. */
    .stepper { list-style: none; margin: 1.2rem 0 0; padding: 0; }
    .step { position: relative; display: flex; gap: 1rem; padding-bottom: 1.5rem; }
    .step:last-child { padding-bottom: 0; }
    .step:not(:last-child)::before {
        content: ""; position: absolute; left: 1.05rem; top: 2.3rem; bottom: -0.3rem;
        width: 1px; background: #2A3238; transform: translateX(-50%);
    }
    .step:has(+ .step-parallel)::before { background: none; border-left: 1px dashed #E2726E; width: 0; }
    .step-marker {
        position: relative; z-index: 1; flex-shrink: 0; width: 2.1rem; height: 2.1rem; border-radius: 50%;
        border: 1px solid #2A3238; background: #171D21; display: flex; align-items: center; justify-content: center;
        font-family: 'IBM Plex Mono', monospace; font-weight: 600; font-size: 0.9rem; color: #E7ECEF;
    }
    .step-marker.bad { border-color: #E2726E; color: #E2726E; }
    .step-marker.accent { border-color: #4FBDBA; color: #4FBDBA; }
    .step-body { flex: 1; min-width: 0; padding-top: 0.2rem; }
    .step-title { position: relative; display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; font-weight: 600; margin-bottom: 0.3rem; color: #E7ECEF; }
    .step-tag { font-family: 'IBM Plex Mono', monospace; font-size: 0.74rem; font-weight: 400; color: #8B98A0; }
    .step-body p { margin: 0; font-size: 0.9rem; color: #C5CFD4; line-height: 1.55; }
    .info-btn {
        display: inline-flex; align-items: center; justify-content: center; width: 1.05rem; height: 1.05rem;
        border-radius: 50%; border: 1px solid #63707A; color: #8B98A0; background: transparent;
        font-family: 'IBM Plex Mono', monospace; font-size: 0.64rem; line-height: 1; padding: 0; cursor: pointer;
    }
    .info-btn:hover, .info-btn:focus-visible { border-color: #4FBDBA; color: #4FBDBA; }
    .info-tip {
        display: none; position: absolute; z-index: 20; left: 0; top: 1.6rem; width: min(22rem, 80vw);
        background: #1D252A; border: 1px solid #2A3238; border-radius: 8px; padding: 0.65rem 0.8rem;
        font-size: 0.8rem; font-weight: 400; line-height: 1.5; color: #C5CFD4; text-transform: none;
        letter-spacing: normal; box-shadow: 0 10px 28px rgba(0, 0, 0, 0.45);
    }
    .info-btn:hover + .info-tip, .info-btn:focus-visible + .info-tip, .info-tip:hover { display: block; }

    /* Navbar-style tabs: Streamlit's tabs use BaseWeb components under
       these selectors -- rendered and confirmed present in this version
       (1.62.0) before relying on them. */
    [data-baseweb="tab-list"] { gap: 0.2rem; border-bottom: 1px solid #2A3238; margin-bottom: 1rem; }
    [data-baseweb="tab"] {
        font-family: 'IBM Plex Sans', sans-serif; font-size: 0.95rem; font-weight: 500;
        height: 2.8rem; color: #8B98A0;
    }
    [data-baseweb="tab"][aria-selected="true"] { color: #E7ECEF; }
    [data-baseweb="tab-highlight"] { background-color: #4FBDBA; height: 2px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _card_header(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="card-title">{title}</div><div class="card-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def _section_label(text: str) -> None:
    st.markdown(f'<div class="card-section-label">{text}</div>', unsafe_allow_html=True)


def _kpi_tile(label: str, value: str) -> str:
    return f'<div class="kpi-tile"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>'


def _metric_tile(label: str, value: str, help_text: str | None = None, cls: str = "") -> str:
    help_html = f'<div class="metric-help">{help_text}</div>' if help_text else ""
    return f'<div class="metric-tile {cls}"><div class="metric-label">{label}</div><div class="metric-value {cls}">{value}</div>{help_html}</div>'


def _metric_row(tiles: list[str]) -> None:
    st.markdown(f'<div class="metric-row">{"".join(tiles)}</div>', unsafe_allow_html=True)


st.markdown(
    f'<h1 class="page-title">Argus</h1>'
    f'<span class="mode-text">{"Controls enabled, local session" if CONTROLS_ENABLED else "Read-only, public deployment"}</span>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Load everything up front, once. overview/track_record/decisions/evidence
# come from the SAME functions that build public/data/*.json for the public
# Vercel site -- one source of truth for every non-live number, so the two
# dashboards can't silently drift into different numbers again.
# ---------------------------------------------------------------------------
try:
    overview = build_overview()
    track_record = build_track_record()
    decisions_data = build_decisions()
    evidence_data = build_evidence()
    dashboard_data_error = None
except Exception as e:
    overview = track_record = decisions_data = evidence_data = None
    dashboard_data_error = str(e)

account_state = None
try:
    from pipeline.execution.broker import get_account_state
    from pipeline.execution.positions import open_spread_positions

    account_state = get_account_state(open_positions=open_spread_positions())
except Exception as e:
    account_error = str(e)
else:
    account_error = None

# closed_position_stats reads only the audit log (no broker call), so it
# has its own try/except rather than sharing account_state's -- a live
# account fetch failing (network, rate limit) shouldn't also hide realized
# P&L, which needs nothing but the local log file.
closed_stats = None
try:
    from pipeline.execution.positions import closed_position_stats

    closed_stats = closed_position_stats()
except Exception as e:
    closed_stats_error = str(e)
else:
    closed_stats_error = None

vol_forecast = None
try:
    from pipeline.vol.deliverable import decide as vol_decide

    # live=True: refit on all history for a CURRENT number. The walk-forward
    # series necessarily lags real data by up to one 63-day test block.
    vol_forecast = vol_decide(date.today(), live=True)
except Exception as e:
    vol_forecast_error = str(e)
else:
    vol_forecast_error = None

# ---------------------------------------------------------------------------
# Status line: ONE sentence, straight from build_overview()'s own status
# dict -- the same status computation the public site's narrative reads.
# ---------------------------------------------------------------------------
if dashboard_data_error is not None:
    st.error(f"Could not load dashboard data ({dashboard_data_error}).")
else:
    status = overview["status"]
    time_html = f' <span class="time">({status["timestamp"]})</span>' if status["timestamp"] else ""
    st.markdown(
        f'<p class="status-line"><span class="word {status["cls"]}">{status["word"]}</span> &mdash; {status["rest"]}{time_html}</p>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Manual controls -- gated entirely on CONTROLS_ENABLED, not just disabled:
# an earlier round shipped these always-visible-but-disabled (direct
# feedback: take them back out). Placed immediately after the status line,
# before any tab, so it's visible without scrolling in a controls-enabled
# session -- direct feedback that burying it at the bottom of Overview
# meant it wasn't immediately visible.
# ---------------------------------------------------------------------------
if CONTROLS_ENABLED:
    with st.container(border=True):
        _card_header("Manual controls", "Local session only -- acts on the real paper account immediately")

        from pipeline.execution.pause import is_trading_paused, pause_trading, resume_trading

        pause_state = is_trading_paused()
        col_pause, col_run, col_close = st.columns(3)

        with col_pause:
            if pause_state is not None:
                if st.button("Resume trading", help=f"Paused: {pause_state['reason']} (since {pause_state['paused_at']}). Resuming lets today's evaluation happen if it hasn't yet."):
                    resume_trading()
                    st.rerun()
            else:
                if st.button("Pause trading", help="Stops the NEXT run before it evaluates anything. Today's decision, if any, already happened -- this doesn't undo it."):
                    pause_trading("paused from local admin panel")
                    st.rerun()

        with col_run:
            if st.button("Run agent now (live)", help="Runs the real decision pipeline immediately, LIVE -- same Guards/Reviewer/one-decision-per-day rule the cron uses, just on demand. No-op if today's already decided."):
                from pipeline.run_agent import run_once as run_agent_once

                with st.spinner("Running..."):
                    result = run_agent_once(dry_run=False)
                st.write(result)

        with col_close:
            confirm = st.checkbox("Confirm", key="confirm_force_close", help="Required before the button below activates.")
            if st.button(
                "Force-close all",
                disabled=not confirm,
                type="primary",
                help="Closes every open spread at market immediately, via the same path monitor.py's hard-drawdown auto-close uses. Irreversible once submitted.",
            ):
                from pipeline.execution.monitor import run_once as run_monitor_once

                with st.spinner("Closing..."):
                    result = run_monitor_once(dry_run=False, manual_close_reason="operator requested via local admin panel")
                st.write(result)
                st.session_state["confirm_force_close"] = False

        if pause_state is not None:
            st.caption(f"Paused: {pause_state['reason']} (since {pause_state['paused_at']})")

if dashboard_data_error is not None:
    st.stop()

tab_overview, tab_track_record, tab_log, tab_how = st.tabs(
    ["Overview", "Track record", "Decision log", "How it works"]
)

# ---------------------------------------------------------------------------
# Overview -- same section order as public/index.html: narrative + account
# side by side, then market/volatility/forecast, then decision path, then
# open positions.
# ---------------------------------------------------------------------------
with tab_overview:
    col_narrative, col_account = st.columns(2)

    with col_narrative:
        with st.container(border=True):
            _card_header("Today, in plain terms", "The short version. Everything below is the supporting detail")
            lines_html = "".join(
                f'<div class="narrative-line"><span class="narrative-label {line["cls"]}">{line["label"]}</span>'
                f'<span class="narrative-detail">{line["detail"]}</span></div>'
                for line in overview["narrative"]
            )
            st.markdown(lines_html, unsafe_allow_html=True)
            if overview["status"]["timestamp"]:
                st.markdown(f'<p class="card-note">Last decision logged: {overview["status"]["timestamp"]}</p>', unsafe_allow_html=True)

    with col_account:
        with st.container(border=True):
            _card_header("Account", "Cash plus what any open positions are worth right now, live from Alpaca")
            if account_error is not None:
                st.caption(f"Live account data unavailable right now ({account_error}).")
            elif account_state is not None:
                n_open = len(account_state.get("raw_positions") or [])
                equity_value = f"${account_state['current_equity']:,.0f}"
                st.markdown(f'<div class="kpi-row">{_kpi_tile("Equity", equity_value)}</div>', unsafe_allow_html=True)
                tiles = [
                    _metric_tile("Cash", f"${account_state['cash']:,.0f}"),
                    _metric_tile("Options buying power", f"${account_state['options_buying_power']:,.0f}"),
                    _metric_tile("Open positions", str(n_open)),
                ]
                if n_open > 0:
                    unrealized = sum(
                        float(p.unrealized_pl) for p in account_state["raw_positions"] if p.unrealized_pl is not None
                    )
                    tiles.append(_metric_tile("Unrealized P&L", f"${unrealized:+,.2f}", cls="good" if unrealized >= 0 else "bad"))
                _metric_row(tiles)

                if closed_stats_error is not None:
                    st.caption(f"Closed-position stats unavailable ({closed_stats_error}).")
                elif closed_stats is not None and closed_stats["n_closed"] > 0:
                    st.write("")
                    realized = closed_stats["total_realized_pnl"]
                    coverage_note = (
                        f" ({closed_stats['n_with_pnl']} of {closed_stats['n_closed']} have a recorded P&L)"
                        if closed_stats["n_with_pnl"] < closed_stats["n_closed"] else ""
                    )
                    realized_tiles = [
                        _metric_tile("Realized P&L", f"${realized:+,.2f}", cls="good" if realized >= 0 else "bad"),
                        _metric_tile("Closed positions", str(closed_stats["n_closed"])),
                    ]
                    if closed_stats["win_rate"] is not None:
                        realized_tiles.append(_metric_tile("Win rate", f"{closed_stats['win_rate']:.0%} ({closed_stats['wins']}W/{closed_stats['losses']}L)"))
                    _metric_row(realized_tiles)
                    if coverage_note:
                        st.caption(
                            "Realized P&L is only computed for a profit-target or day-before-expiry close, "
                            "where a live quote for both legs was already fetched at the decision moment -- "
                            "an emergency or force-close doesn't have that, so it's left out rather than guessed."
                            + coverage_note
                        )

    with st.container(border=True):
        _section_label("Today's market")
        if overview["market_error"] is not None:
            st.caption(f"Live market data unavailable right now ({overview['market_error']}).")
        elif overview["market"] is not None:
            m = overview["market"]
            move_blocks = abs(m["yesterday_move_pct"]) > 0.02
            contango_blocks = m["contango_threshold"] is not None and m["contango"] < m["contango_threshold"]
            _metric_row([
                _metric_tile("SPY spot", f"${m['spot']:.2f}"),
                _metric_tile("Yesterday's move", f"{m['yesterday_move_pct']:+.1%}", "Blocks a new trade above 2%.", "bad" if move_blocks else ""),
                _metric_tile("Contango (VIX3M/VIX9D)", f"{m['contango']:.3f}", "Flattening below its own 33rd percentile.", "bad" if contango_blocks else ""),
            ])
            blocks = []
            if move_blocks:
                blocks.append(f"SPY moved {m['yesterday_move_pct']:+.1%} yesterday (blocks above 2%)")
            if contango_blocks:
                blocks.append(f"term structure is flattening ({m['contango']:.3f} < {m['contango_threshold']:.3f})")
            note_cls = "bad" if blocks else "good"
            note_text = ("Would block a new trade today: " + "; ".join(blocks) + ".") if blocks else "Nothing here would block a new trade today."
            st.markdown(f'<p class="card-note {note_cls}">{note_text}</p>', unsafe_allow_html=True)

        st.divider()
        _section_label("Volatility (SPY)")
        if overview["market_error"] is not None or overview["volatility"] is None:
            st.caption("Not enough data to compute today.")
        else:
            v = overview["volatility"]
            eq_html = (
                f'<div class="equation equation-box {v["verdict_class"]}">'
                f'<span class="eq-item"><span class="eq-label">VIX9D</span><span class="eq-val">{v["vix9d_decimal"]:.1%}</span></span>'
                f'<span class="eq-op">÷</span>'
                f'<span class="eq-item"><span class="eq-label">realized (10d)</span><span class="eq-val">{v["rv10d"]:.1%}</span></span>'
                f'<span class="eq-op">=</span>'
                f'<span class="eq-item"><span class="eq-label">ratio</span><span class="eq-val">{v["ratio"]:.2f}</span></span>'
                f'<span class="eq-op">&rarr;</span>'
                f'<span class="eq-verdict {v["verdict_class"]}">{v["verdict_text"].split(":", 1)[0]}</span>'
                f'</div>'
            )
            st.markdown(eq_html, unsafe_allow_html=True)
            if v["verdict_class"] == "good":
                threshold_text = f'above the {v["rich_threshold"]:.2f} "rich" line'
            elif v["verdict_class"] == "bad":
                threshold_text = f'below the {v["thin_threshold"]:.2f} "thin" line'
            else:
                threshold_text = f'between the {v["thin_threshold"]:.2f}-{v["rich_threshold"]:.2f} "fair" band'
            st.markdown(f'<p class="card-note {v["verdict_class"]}">{v["verdict_text"]}: the ratio is {threshold_text}.</p>', unsafe_allow_html=True)

        st.divider()
        _section_label("Volatility forecast (research track)")
        if vol_forecast_error is not None:
            st.caption(f"Forecast unavailable right now ({vol_forecast_error}).")
        elif vol_forecast is not None:
            _metric_row([
                _metric_tile("Forecast vol (annualized)", f"{vol_forecast['forecast_vol_annualized_pct']:.1f}%"),
                _metric_tile("Implied breach prob. (3% / weekly)", f"{vol_forecast['forecast_breach_prob']:.1%}"),
            ])
            st.markdown(
                f'<p class="card-note">HAR-X, a separate model validated on real data (EXPERIMENT.md Exp. 14/18) -- '
                f'informational only, not used by the Picker, Guard, or Reviewer above. As of {vol_forecast["forecast_as_of"]}.</p>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("Forecast not available.")

    with st.container(border=True):
        _card_header("Today's decision path", "The four gates one proposal a day has to clear, in order")
        html_rows = "".join(
            f'<div class="path-row"><span class="path-stage">{row["stage"]}</span>'
            f'<span class="path-word {row["cls"]}">{row["cls"].upper() if row["cls"] != "neutral" else "N/A"}</span>'
            f'<span class="path-detail">{row["detail"]}</span></div>'
            for row in overview["decision_path"]
        )
        st.markdown(html_rows, unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Open positions -- overview["open_positions"] carries strikes/room/
    # expiry/collected/max-loss; joined here to live raw broker positions
    # for unrealized P&L, same join Vercel's app.js does client-side.
    # ------------------------------------------------------------------
    open_positions = overview.get("open_positions") or []
    if open_positions:
        with st.container(border=True):
            _card_header("Open positions", "Live from Alpaca, joined to the audit log for what was collected and the max loss at entry")
            raw_by_symbol = {}
            if account_error is None and account_state is not None:
                raw_by_symbol = {p.symbol: p for p in account_state["raw_positions"]}

            position_rows = []
            for p in open_positions:
                unrealized = 0.0
                for sym in (p["short_symbol"], p["long_symbol"]):
                    rp = raw_by_symbol.get(sym)
                    if rp is not None and rp.unrealized_pl is not None:
                        unrealized += float(rp.unrealized_pl)
                position_rows.append({
                    "underlying": p["underlying"],
                    "strikes": p["strikes"],
                    "room": f"{p['room_pct']:+.1%}" if p["room_pct"] is not None else "N/A",
                    "expires": f"{p['expires_days']}d" if p["expires_days"] is not None else "N/A",
                    "qty": p["qty"],
                    "collected": f"${p['collected']:,.2f}",
                    "max loss": f"${p['max_loss']:,.0f}",
                    "unrealized": f"${unrealized:+,.2f}",
                })
            st.dataframe(pd.DataFrame(position_rows), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Track record -- same section order as public/index.html: equity curve
# (with headline, trade statistics, and the benchmark chart un-collapsed),
# then validation and false-trip side by side, then the evidence gate.
# ---------------------------------------------------------------------------
with tab_track_record:
    errors = track_record.get("errors", {})

    with st.container(border=True):
        if errors.get("equity_curve") is not None:
            st.error(f"Could not render the equity curve ({errors['equity_curve']}).")
        else:
            _card_header(
                "Equity curve, 2016-2026",
                "Cumulative $ per contract: trade every week vs. the VIX term-structure filter",
            )
            if track_record.get("equity_headline"):
                st.markdown(f'<p class="card-note">{track_record["equity_headline"]}</p>', unsafe_allow_html=True)

            ec = track_record["equity_curve"]
            curve_df = pd.DataFrame({
                "trade every week": ec["cum_pnl_unfiltered"],
                "VIX filter": ec["cum_pnl_filtered"],
            }, index=pd.to_datetime(ec["dates"]))
            st.line_chart(curve_df, color=["#E2726E", "#5FBF95"])

            s = track_record["stats"]
            _metric_row([
                _metric_tile("Max drawdown, $/contract", f"{s['dd_filtered']:.2f}", f"{s['dd_filtered'] - s['dd_unfiltered']:+.2f} vs. unfiltered"),
                _metric_tile("Worst year, filtered", f"{s['worst_year_filtered']['pnl']:+.2f}",
                             f"Year {s['worst_year_filtered']['year']}. Unfiltered: {s['worst_year_unfiltered']['pnl']:+.2f} in {s['worst_year_unfiltered']['year']}."),
                _metric_tile("Weeks traded", f"{s['weeks_traded']} of {s['weeks_total']}"),
            ])

            st.divider()
            _section_label("Trade statistics")
            _metric_row([
                _metric_tile("Win rate", f"{s['win_rate']:.1%}", f"{s['n_wins']} wins, {s['n_losses']} losses", "good" if s["win_rate"] >= 0.5 else "bad"),
                _metric_tile("Profit factor", f"{s['profit_factor']:.2f}", "Gross wins / gross losses", "good" if s["profit_factor"] >= 1 else "bad"),
                _metric_tile("Avg win / avg loss", f"${s['avg_win']:,.2f} / ${s['avg_loss']:,.2f}", "Per traded week, $/contract"),
                _metric_tile("Best / worst week", f"${s['best_week']:,.2f} / ${s['worst_week']:,.2f}", "Single-week extremes, $/contract"),
            ])

            st.divider()
            _section_label("Benchmark: SPY buy-and-hold and cash")
            bench_df = pd.DataFrame({
                "SPY (indexed)": ec["spy_indexed"],
                "cash @ 3%/yr (indexed)": ec["cash_indexed"],
            }, index=pd.to_datetime(ec["dates"]))
            st.line_chart(bench_df, color=["#8B98A0", "#45505A"])
            st.markdown(
                f'<p class="card-note">SPY buy-and-hold returned {s["spy_final_pct"]:+.0%} over {s["date_range"]} '
                f'(full market exposure); cash at 3%/yr returned {s["cash_final_pct"]:+.0%}. Neither carries the same '
                f'risk as a defined-loss options spread, so these are context, not a head-to-head with the '
                f'${s["final_filtered"]:.2f}/contract chart above.</p>',
                unsafe_allow_html=True,
            )

    col_validation, col_false_trip = st.columns(2)

    with col_validation:
        with st.container(border=True):
            _card_header("Why the reconstruction can be trusted", "A per-quartile check against real market data, not just an aggregate score")
            if errors.get("validation") is not None:
                st.error(f"Could not compute validation ({errors['validation']}).")
            else:
                v = track_record["validation"]
                all_inside = all(v["band"][0] <= q["ratio"] <= v["band"][1] for q in v["quartiles"])
                _metric_row([
                    _metric_tile("Correlation (real vs. modelled credit)", f"{v['correlation']:.3f}"),
                    _metric_tile("Quartiles inside band", f"{len(v['quartiles'])} of {len(v['quartiles'])}",
                                 f"Band: {v['band'][0]}-{v['band'][1]}", "good" if all_inside else "bad"),
                ])
                q_df = pd.DataFrame([{
                    "Quartile": q["bucket"], "Weeks": q["n"], "Mean VIX9D": f"{q['vix9d_mean']:.1%}",
                    "Real credit": f"${q['real_credit']:.2f}", "Model credit": f"${q['model_credit']:.2f}",
                    "Model/real": f"{q['ratio']:.3f}",
                } for q in v["quartiles"]])
                st.dataframe(q_df, width="stretch", hide_index=True)

    with col_false_trip:
        with st.container(border=True):
            _card_header("Do the safety guards actually work?", "How often the term-structure guard would have blocked a real, historically winning week")
            if errors.get("false_trip") is not None:
                st.error(f"Could not compute the false-trip test ({errors['false_trip']}).")
            else:
                ft = track_record["false_trip"]
                ft_good = ft["blocked_pct"] <= ft["bar"]
                _metric_row([
                    _metric_tile("Blocked (aggregate)", f"{ft['blocked_pct']:.1%}", f"Bar: <={ft['bar']:.0%}", "good" if ft_good else "bad"),
                    _metric_tile("Real winning weeks tested", str(ft["n_winners"])),
                ])
                r_df = pd.DataFrame([{
                    "Regime": r["regime"], "Weeks": r["n"], "Blocked": r["blocked"], "Blocked %": f"{r['blocked_pct']:.1%}",
                } for r in ft["by_regime"]])
                st.dataframe(r_df, width="stretch", hide_index=True)

    with st.container(border=True):
        _card_header("Evidence gate", "Every (distance, width) combination swept against 128 real historical weeks. A cell only ships if its win-rate cushion clears 2 standard errors above breakeven.")
        if not evidence_data["rows"]:
            st.warning("Evidence gate not computed yet.")
        else:
            pick = evidence_data["current_pick"]
            if pick is None:
                st.warning("No (distance, width) combination currently clears the 2-SE evidence bar -- the system declines to trade, on purpose.")
            else:
                st.success(
                    f"Today's pick: **{pick['distance']:.0%} distance, ${pick['width']:.0f} width**, "
                    f"cushion **{pick['cushion_se']:.2f} SE** ({pick['n_survivors']} of {pick['n_total']} combinations qualify)."
                )
            with st.expander(f"See all {len(evidence_data['rows'])} combinations tested"):
                ev_df = pd.DataFrame([{
                    "distance": f"{r['distance']:.0%}", "width": f"${r['width']:.0f}", "weeks": r["n"],
                    "measured win rate": f"{r['win_rate']:.1%}", "breakeven win rate": f"{r['required_win_rate']:.1%}",
                    "cushion (SE)": f"{r['cushion_se']:.2f}", "mean P&L/contract": f"${r['mean_net_pnl']:.2f}",
                    "clears 2 SE": "Yes" if r["passes_gate"] else "No",
                } for r in evidence_data["rows"]])
                st.dataframe(ev_df, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Decision log -- summary counts, then filter chips, then the table --
# sourced from build_decisions() so counts and rows can't drift from the
# public site's numbers.
# ---------------------------------------------------------------------------
with tab_log:
    _card_header("Decisions", "Every day the agent runs, including a day it declines to trade, gets a row here")

    summary = decisions_data["summary"]
    if summary["total"] == 0:
        st.write("No decisions logged yet.")
    else:
        _metric_row([
            _metric_tile("Total", str(summary["total"])),
            _metric_tile("Traded", str(summary["traded"])),
            _metric_tile("Guard-blocked", str(summary["guard_blocked"])),
            _metric_tile("Reviewer-vetoed", str(summary["reviewer_vetoed"])),
            _metric_tile("Dry run", str(summary["dry_run"])),
        ])

        options = ["All", "Traded", "Guard-blocked", "Reviewer-vetoed", "Dry run"]
        choice = st.segmented_control("Filter", options, default="All", label_visibility="collapsed")
        rows = decisions_data["rows"]
        filtered = rows if choice in (None, "All") else [r for r in rows if r["category"] == choice]

        if not filtered:
            st.write("No decisions in this category.")
        else:
            page_size = 15
            total_pages = max(1, -(-len(filtered) // page_size))  # ceil div
            page = st.number_input(
                "Page", min_value=1, max_value=total_pages, value=1, step=1,
                key=f"decisions_page_{choice}",
            )
            st.caption(f"Page {page} of {total_pages} ({len(filtered)} rows)")
            start = (page - 1) * page_size
            page_rows = filtered[start:start + page_size]
            display_df = pd.DataFrame(page_rows)[["timestamp_display", "account_display", "mode", "outcome", "reason"]]
            display_df = display_df.rename(columns={"timestamp_display": "timestamp", "account_display": "account"})
            st.dataframe(display_df, width="stretch", hide_index=True)

        with st.expander("Full audit trail (every field, unfiltered)"):
            log_df = read_log()
            if log_df.empty:
                st.write("No decisions logged yet.")
            else:
                st.dataframe(log_df.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# How it works -- the real 6-step pipeline, ported verbatim from
# public/index.html's stepper so the diagram and the wording match exactly.
# ---------------------------------------------------------------------------
with tab_how:
    _card_header("How it works", "One proposal a day moves through five gates in order; Recovery watches the last two continuously")

    steps = [
        {"marker": "1", "marker_cls": "", "title": "Picker", "tag": "proposes", "info": None,
         "body": "Fixed rules, calibrated from the ten-year backtest, propose one trade a day. No model, no discretion."},
        {"marker": "2", "marker_cls": "bad", "title": "Guard", "tag": "15 hard limits", "info": None,
         "body": "15 hard safety limits check the proposal. Any single failure blocks the trade, and none can be overridden downstream."},
        {"marker": "3", "marker_cls": "accent", "title": "Reviewer", "tag": "veto / shrink only",
         "info": "Verified live end-to-end: a real MCP account fetch plus a real Gemini call returned a genuine APPROVE decision.",
         "body": "An AI (Gemini) may veto or shrink a Guard-approved proposal, never raise its size, never originate one. Enforced in code, not by the prompt."},
        {"marker": "4", "marker_cls": "", "title": "Order", "tag": "to broker", "info": None,
         "body": "Sent to the broker as a single two-legged order once both Guard and Reviewer have cleared it."},
        {"marker": "5", "marker_cls": "", "title": "Monitor", "tag": "every 15 min", "info": None,
         "body": "Every 15 minutes: a profit target, a forced close the day before expiry (assignment-risk protection), or a hard drawdown stop."},
        {"marker": "&#8635;", "marker_cls": "bad", "title": "Recovery", "tag": "runs alongside Order &amp; Monitor", "info": None,
         "body": "An unrecognized broker position or a partial fill halts trading and closes the excess risk immediately.", "parallel": True},
    ]

    lis = []
    for s in steps:
        parallel_cls = " step-parallel" if s.get("parallel") else ""
        info_html = f'<button class="info-btn" type="button">?</button><span class="info-tip">{s["info"]}</span>' if s.get("info") else ""
        lis.append(
            f'<li class="step{parallel_cls}"><div class="step-marker {s["marker_cls"]}">{s["marker"]}</div>'
            f'<div class="step-body"><div class="step-title">{s["title"]} <span class="step-tag">{s["tag"]}</span>{info_html}</div>'
            f'<p>{s["body"]}</p></div></li>'
        )
    st.markdown(f'<ol class="stepper">{"".join(lis)}</ol>', unsafe_allow_html=True)

    st.markdown(
        '<p class="card-note">The AI is deliberately the least-trusted component here: it sits after every hard '
        'limit has already passed, and the only actions it\'s structurally capable of are subtracting risk or '
        'refusing. Enforced by <code>apply_reviewer_decision</code>, not by asking the prompt nicely.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="card-note">Full design rationale: <code>OPTIONS_SYSTEM_PLAN.md</code>. Full experiment log, '
        'including two retracted findings: <code>EXPERIMENT.md</code>.</p>',
        unsafe_allow_html=True,
    )
