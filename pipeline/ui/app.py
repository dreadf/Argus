"""
Streamlit dashboard. Deliberately reads from FILES (the committed backtest
and evidence-gate CSVs, the audit log) rather than requiring a live trade to
have happened -- so the public URL always has real content, even on a fresh
deploy with zero positions and before market open (Part 7's design: "the
dashboard's headline content comes from the backtest, which exists before
any trade does").

CONTROLS_ENABLED gates write actions (approve/reject, limit sliders, stop).
Defaults to OFF. No write actions exist yet as of this build step (modes.py
and reviewer.py are stretch items, Part 8's file list) -- this app is
read-only regardless of the flag today, but the flag is wired now so a
future write action can check it rather than being added as an afterthought
on a public deploy.

Every section is wrapped so a missing file, a broker error, or an empty log
renders a plain message instead of a stack trace (Verification #22, the
cold-open drill).

Layout (post-feedback rewrite): a first version put four equally-weighted
sections in one long scroll -- a 24-row table and a 27-column raw audit
dump with no visual signal for which row mattered, and no single answer to
"is this working right now" before scrolling past all of it. Fixed by (1)
a one-line status hero above everything else, derived from the latest
logged decision, and (2) moving the dense material (the full evidence-gate
sweep, the full audit trail, the architecture explainer) behind tabs so
only one thing is on screen by default instead of everything at once.
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

# Design tokens: a warm-neutral "instrument panel" system, grounded in the
# subject rather than generic fintech-dark-mode. Palette set in
# .streamlit/config.toml (native widgets like st.dataframe/st.metric read
# theme colors directly -- CSS cannot reach inside their canvas-rendered
# internals); this block covers typography and the status readout.
#
# IBM Plex Sans/Mono instead of Inter/JetBrains Mono -- Inter is a
# well-known "safe default" that most AI-generated interfaces reach for,
# which is exactly the generic-template read this page was getting
# flagged for. Plex was designed for technical/engineering seriousness
# and its Sans and Mono cuts share real DNA, which Inter+an unrelated
# mono face doesn't. Fraunces (a serif with actual character) is used
# ONLY for the page title, for a ledger/instrument-label feel, without
# making the rest of the page decorative.
#
# State is communicated by colored TEXT (the status readout, chart
# lines), never a tinted pill or a rounded card with an accent bar --
# both of those are exactly the templated pattern that was flagged.
# Semantic colors (good/caution/danger) are kept distinct from the one
# brand accent (amber), not the same hue doing double duty.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap');

    html, body, [class*="css"] { font-family: 'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif; }

    /* Financial figures: tabular numerals so columns of dollar amounts
       align, same convention terminals and trading UIs use. */
    [data-testid="stMetricValue"] {
        font-family: 'IBM Plex Mono', 'SF Mono', monospace;
        font-variant-numeric: tabular-nums;
        font-weight: 500;
    }
    [data-testid="stMetricLabel"] { font-size: 0.8rem; color: #93897A; }

    h1.page-title {
        font-family: 'Fraunces', Georgia, serif;
        font-weight: 600;
        font-size: 2.1rem;
        letter-spacing: -0.01em;
        margin-bottom: 0.15rem;
    }
    h2, h3 { font-weight: 600; }

    .subtitle { color: #93897A; font-size: 0.92rem; margin-bottom: 1.2rem; }

    .status-readout { margin-bottom: 1.4rem; }
    .status-readout .label {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase;
        margin-bottom: 0.2rem;
    }
    .status-readout .label.good { color: #5B8A5A; }
    .status-readout .label.caution { color: #B5502E; }
    .status-readout .label.danger { color: #9C3B3B; }
    .status-readout .label.neutral { color: #93897A; }
    .status-readout .headline { font-size: 1.05rem; color: #EDE6D8; }
    .status-readout .meta {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.78rem; color: #6B6357; margin-top: 0.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<h1 class="page-title">Evidence Gate</h1>', unsafe_allow_html=True)
mode_text = "Controls enabled, local session" if CONTROLS_ENABLED else "Read-only, public deployment"
st.markdown(
    f'<p class="subtitle">{mode_text} &mdash; an options agent that sells S&amp;P 500 volatility premium only when '
    "the measured edge clears a statistical bar, and refuses to trade when it doesn't.</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Load everything up front, once, into plain variables (None on any
# failure) -- both the status hero and the tabs below read from these, so
# nothing is fetched or parsed twice.
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
    from pipeline.data.vix import contango_ratio, current_contango_and_threshold, load_cached_vix
    from pipeline.options.chain import get_spot
    from pipeline.options.vol import fetch_recent_closes

    from pipeline.data.vix import refresh_vix_cache

    _spot = get_spot()
    _closes = fetch_recent_closes()
    # A fresh Streamlit Cloud container has no cache file on disk at all
    # (it's gitignored, same as the audit log -- generated state, not
    # source) -- refresh before reading, same order run_agent.py uses,
    # so the dashboard self-heals on first load instead of erroring.
    refresh_vix_cache()
    _vix9d = load_cached_vix("VIX9D")
    _vix3m = load_cached_vix("VIX3M")
    _, _contango_threshold = current_contango_and_threshold()
    today_snapshot = {
        "spot": _spot,
        "yesterday_move_pct": float(_closes.pct_change().iloc[-1]),
        "vix9d": float(_vix9d.iloc[-1]),
        "vix3m": float(_vix3m.iloc[-1]),
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
# Status hero: the one sentence a viewer should read before anything else.
# Derived from the most recent logged decision, not a fresh computation --
# it should say exactly what the audit log says happened, nothing more.
# ---------------------------------------------------------------------------
def _status_hero(log_df: pd.DataFrame | None) -> tuple[str, str, str, str]:
    """Returns (semantic_class, label, headline, meta). semantic_class is
    one of good/caution/danger/neutral -- kept distinct from the page's
    amber brand accent, same discipline as the evidence-gate/chart colors."""
    if log_df is None:
        return "neutral", "Status unknown", "Could not read the decision log.", ""
    if log_df.empty:
        return "neutral", "Not yet run", "No decisions logged yet -- the agent hasn't run today.", ""

    latest = log_df.sort_values("timestamp", ascending=False).iloc[0]
    outcome = latest.get("outcome")
    ts = latest.get("timestamp", "")
    meta = f"Last decision: {ts}"

    if outcome == "SOLD":
        return ("good", "Trading",
                f"Opened {latest.get('short_symbol')} / {latest.get('long_symbol')}, "
                f"{int(latest['proposed_contracts']) if pd.notna(latest.get('proposed_contracts')) else '?'} contract(s).",
                meta)
    if outcome == "DRY_RUN":
        return ("neutral", "Dry run",
                f"Would have opened {latest.get('short_symbol')} / {latest.get('long_symbol')} "
                "-- dry-run mode, no real order sent.", meta)
    if outcome == "SKIPPED":
        reasons = latest.get("guards_failed")
        if isinstance(reasons, list) and reasons:
            reason_text = "; ".join(str(r) for r in reasons)
        else:
            reason_text = "No reason recorded."
        return ("caution", "Declined to trade today", reason_text, meta)
    if outcome == "CLOSED":
        return ("neutral", "Position closed", str(latest.get("close_reason", "")), meta)
    if outcome == "EMERGENCY_CLOSE_ORPHAN":
        return ("danger", "Emergency close", str(latest.get("close_reason", "")), meta)
    return ("neutral", str(outcome), "", meta)


hero_class, hero_label, hero_headline, hero_meta = _status_hero(log_df)
st.markdown(
    f"""
    <div class="status-readout">
        <div class="label {hero_class}">{hero_label}</div>
        <div class="headline">{hero_headline}</div>
        <div class="meta">{hero_meta}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_overview, tab_track_record, tab_evidence, tab_log, tab_how = st.tabs(
    ["Overview", "Track record", "Evidence", "Decision log", "How it works"]
)

# ---------------------------------------------------------------------------
# Overview: an operations view of TODAY, not a backtest teaser (that lives
# in Track record). Order: what's open right now -> today's raw market
# data -> what that data means for the guards -> the bigger picture, last.
# ---------------------------------------------------------------------------
with tab_overview:
    st.markdown("##### Current positions")
    if account_error is not None:
        st.info(f"Live account data unavailable right now ({account_error}).")
    elif account_state is not None:
        raw_positions = account_state.get("raw_positions") or []
        if not raw_positions:
            st.write("No open positions right now.")
        else:
            rows = [{
                "symbol": p.symbol, "side": str(p.side).replace("PositionSide.", ""),
                "qty": p.qty,
                "avg entry": f"${float(p.avg_entry_price):.2f}",
                "current": f"${float(p.current_price):.2f}" if p.current_price is not None else "-",
                "unrealized P&L": f"${float(p.unrealized_pl):+,.2f}" if p.unrealized_pl is not None else "-",
            } for p in raw_positions]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        col1, col2 = st.columns(2)
        col1.metric("Equity", f"${account_state['current_equity']:,.0f}")
        col2.metric("Positions open", f"{len(raw_positions)} of {MAX_CONCURRENT_POSITIONS}",
                    help="Concurrent put credit spreads open now, against the hard cap the Guard enforces.")

    st.write("")
    st.markdown("##### Today's SPY & volatility snapshot")
    if snapshot_error is not None:
        st.info(f"Live market data unavailable right now ({snapshot_error}).")
    elif today_snapshot is not None:
        s = today_snapshot
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("SPY spot", f"${s['spot']:.2f}")
        col2.metric("Yesterday's move", f"{s['yesterday_move_pct']:+.2%}",
                    help="The gap-risk leg of the volatility-regime guard blocks a new trade above 2% in either direction.")
        col3.metric("VIX9D / VIX3M", f"{s['vix9d']:.1f} / {s['vix3m']:.1f}",
                    help="CBOE's 9-day and 3-month implied volatility indices -- the inputs to the term-structure guard.")
        col4.metric("Contango (VIX3M/VIX9D)", f"{s['contango']:.3f}",
                    help="Below its own trailing 33rd percentile means the term structure is flattening/inverting.")

        st.markdown("**What this means today:**")
        if abs(s["yesterday_move_pct"]) > 0.02:
            st.write(f"- SPY moved {s['yesterday_move_pct']:+.1%} yesterday, past the 2% gap-risk threshold -- "
                     "the volatility-regime guard would block a new trade today.")
        else:
            st.write(f"- SPY moved {s['yesterday_move_pct']:+.1%} yesterday, within the normal range -- "
                     "no block from the gap-risk guard.")
        if s["contango_threshold"] is not None:
            if s["contango"] < s["contango_threshold"]:
                st.write(f"- Term structure is flattening ({s['contango']:.3f} < trailing 33rd pct "
                         f"{s['contango_threshold']:.3f}) -- the term-structure guard would block a new trade today.")
            else:
                st.write(f"- Term structure is normal ({s['contango']:.3f} >= trailing 33rd pct "
                         f"{s['contango_threshold']:.3f}) -- no block from this guard today.")
        else:
            st.write("- Not enough trailing history yet to set a term-structure threshold.")
    else:
        st.warning("Could not compute today's snapshot.")

    st.write("")
    st.divider()
    st.markdown("##### The bigger picture")

    if curve_df is not None:
        dd_u, dd_f = _max_dd(curve_df["cum_pnl_unfiltered"]), _max_dd(curve_df["cum_pnl_filtered"])
        total_f = float(curve_df["pnl_filtered"].sum())
        col1, col2, col3 = st.columns(3)
        col1.metric("10-year total P&L, $/contract", f"{total_f:+.2f}",
                    help="Cumulative P&L per contract from the validated reconstruction, 2016-2026, VIX filter applied.")
        col2.metric("Worst drawdown, $/contract", f"{dd_f:.2f}",
                    help=f"With no filter this would have been {dd_u:.2f} -- see the Track record tab for the full picture.")
        col3.metric("vs. SPY buy-and-hold", "~0.35 vs 0.66 Sharpe",
                    help="Roughly half the risk-adjusted return of just holding the index, bought with a much shallower drawdown. Full numbers in EXPERIMENT.md.")
        st.caption("Full 10-year chart, year-by-year breakdown, and the SPY/cash comparison are in the **Track record** tab.")
    else:
        st.warning("Reconstruction not computed yet -- run `python -m pipeline.backtest.reconstruct`.")

    if gate_df is not None:
        if gate_choice is None:
            st.warning("No (distance, width) combination currently clears the evidence bar. The system declines to trade, on purpose.")
        else:
            n_survivors = int(gate_df["passes_gate"].sum())
            st.success(
                f"Today's evidence: **{gate_choice['distance']:.0%} distance, ${gate_choice['width']:.0f} width** clears its "
                f"statistical bar with a **{gate_choice['cushion_se']:.2f} standard-error cushion** ({n_survivors} of "
                f"{len(gate_df)} combinations tested currently qualify). Full sweep in the **Evidence** tab."
            )
    else:
        st.warning("Evidence gate not computed yet.")

    st.write("")
    st.caption(
        "Architecture, in one line: a volatility forecast feeds fixed picking rules, every proposal passes "
        "15 hard safety limits it cannot override, and an AI reviewer may only veto or shrink what's left -- "
        "never choose or enlarge a trade. Full breakdown in **How it works**."
    )

# ---------------------------------------------------------------------------
# Track record: the full ten-year picture, for a viewer who wants the
# detail behind the Overview tab's two headline numbers.
# ---------------------------------------------------------------------------
with tab_track_record:
    st.write(
        "Real option prices only go back to Feb 2024, so fees before that are reconstructed from "
        "CBOE's VIX9D and validated per volatility quartile before use -- see `EXPERIMENT.md`, "
        "Experiment 12d. Every loss shown is computed from real SPY closes; only the credit side "
        "before Feb 2024 is modelled."
    )

    if curve_error is not None:
        st.error(f"Could not render the equity curve ({curve_error}).")
    elif curve_df is None:
        st.warning("Reconstruction has not been computed yet. Run `python -m pipeline.backtest.reconstruct`.")
    else:
        st.caption("Cumulative P&L per contract, $ -- trade every week vs. the VIX term-structure filter")
        st.line_chart(
            curve_df[["cum_pnl_unfiltered", "cum_pnl_filtered"]].rename(columns={
                "cum_pnl_unfiltered": "trade every week", "cum_pnl_filtered": "VIX filter",
            }),
            color=["#C9722E", "#5B8A5A"],  # amber = unfiltered (exposed to the volatility spike that breaks 2018), sage = the filter we recommend
        )

        dd_u, dd_f = _max_dd(curve_df["cum_pnl_unfiltered"]), _max_dd(curve_df["cum_pnl_filtered"])
        wy_u, wy_f = _worst_year(curve_df, "pnl_unfiltered"), _worst_year(curve_df, "pnl_filtered")
        weeks_traded = int(curve_df["traded"].sum())

        col1, col2, col3 = st.columns(3)
        col1.metric("Max drawdown, $/contract", f"{dd_f:.2f}", delta=f"{dd_f - dd_u:+.2f} vs. unfiltered",
                    delta_color="inverse", help="Peak-to-trough decline in cumulative P&L per contract.")
        col2.metric("Worst year, filtered", f"{wy_f[1]:+.2f}", help=f"Year {wy_f[0]}. Unfiltered worst year: "
                    f"{wy_u[1]:+.2f} in {wy_u[0]}.")
        col3.metric("Weeks traded", f"{weeks_traded} of {len(curve_df)}",
                    help="The filter skips a week entirely when the VIX term structure is flattening/inverting.")

        with st.expander("Shape comparison against SPY and cash (indexed to 100, not dollar-matched)"):
            st.caption(
                "These two lines are NOT on the same $-per-contract basis as the P&L chart above -- a real "
                "dollar comparison needs a position-sizing assumption, which is in `EXPERIMENT.md`'s portfolio-basis "
                "Sharpe/drawdown table instead. This chart exists only to show when SPY itself was falling."
            )
            st.line_chart(
                curve_df[["spy_indexed", "cash_indexed"]].rename(columns={
                    "spy_indexed": "SPY (indexed)", "cash_indexed": "cash @ 3%/yr (indexed)",
                }),
                color=["#93897A", "#4A4438"],
            )

# ---------------------------------------------------------------------------
# Evidence: the current pick stated plainly up front, the full 24-row
# sweep collapsed behind an expander for whoever wants to audit it.
# ---------------------------------------------------------------------------
with tab_evidence:
    st.write(
        "Every (distance, width) combination swept against 128 real historical weeks. "
        "A cell only ships if its measured win-rate cushion clears 2 standard errors "
        "above its own breakeven rate -- see `EXPERIMENT.md`, Experiment 11."
    )

    if gate_error is not None:
        st.error(f"Could not render the evidence gate table ({gate_error}).")
    elif gate_df is None:
        st.warning(
            "Evidence gate has not been computed yet. Run `python -m pipeline.backtest.spread_backtest` "
            "then `python -m pipeline.backtest.evidence_gate`."
        )
    else:
        n_survivors = int(gate_df["passes_gate"].sum())
        if gate_choice is None:
            st.warning("No (distance, width) cell currently clears the 2-SE bar. The system declines to trade.")
        else:
            st.success(
                f"Currently tradable: {gate_choice['distance']:.0%} distance, ${gate_choice['width']:.0f} width "
                f"-- cushion {gate_choice['cushion_se']:.2f} SE, {n_survivors} cell(s) clear the bar in total."
            )

        with st.expander(f"See all {len(gate_df)} combinations tested", expanded=False):
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
# Decision log: the last handful of decisions in plain language by
# default; the full 27-field audit trail one click away for anyone
# auditing the system rather than just checking on it.
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
                if isinstance(reasons, list) and reasons:
                    return "; ".join(str(r) for r in reasons)
                return ""
            if row.get("outcome") == "CLOSED":
                return str(row.get("close_reason", ""))
            return ""

        recent["reason"] = recent.apply(_reason, axis=1)
        st.dataframe(
            recent[["timestamp", "mode", "outcome", "reason"]],
            width="stretch", hide_index=True,
        )

        with st.expander(f"See the full audit trail ({len(log_df)} rows, every field)"):
            full = log_df.sort_values("timestamp", ascending=False)
            st.dataframe(full, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# How it works: the architecture explainer, as steps rather than one
# dense paragraph buried at the bottom of a long page.
# ---------------------------------------------------------------------------
with tab_how:
    st.markdown(
        """
1. **Picker** -- fixed rules, calibrated from the ten-year backtest, propose one trade a day (which strikes, how many contracts). No model, no discretion.
2. **Guard** -- 15 hard safety limits check the proposal (liquidity, position caps, drawdown limits, a VIX term-structure filter, and more). Any single failure blocks the trade. These cannot be overridden by anything downstream.
3. **Reviewer** -- an AI (Gemini) may look at a Guard-approved proposal and *veto or shrink it* -- it can never raise the size and can never originate a trade of its own. That property is enforced in code, not by asking the prompt nicely.
4. **Monitor** -- once open, a position is checked every 15 minutes for a profit target, a forced close the day before expiry (to avoid assignment risk), or a hard drawdown stop.
5. **Recovery** -- if the broker ever shows a position this system doesn't recognize, or an order only partially fills, trading halts and the excess risk is closed immediately rather than left unprotected.

Full design rationale: `OPTIONS_SYSTEM_PLAN.md`. Full experiment log, including two retracted findings and why: `EXPERIMENT.md`.
        """
    )
