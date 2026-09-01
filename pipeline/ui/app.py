"""
Streamlit dashboard. Deliberately reads from FILES (the committed backtest
and evidence-gate CSVs, the audit log) rather than requiring a live trade to
have happened -- so the public URL always has real content, even on a fresh
deploy with zero positions and before market open (Part 7's design: "the
dashboard's headline content comes from the backtest, which exists before
any trade does").

CONTROLS_ENABLED gates write actions. No write actions exist anywhere in
this codebase -- the flag is wired for a future write action to check, not
a currently-missing feature.

Every section is wrapped so a missing file, a broker error, or an empty log
renders a plain message instead of a stack trace (Verification #22, the
cold-open drill).

Layout, fourth rewrite. Prior rounds fixed the wrong layer: round 2 added a
status hero + tabs but Overview still carried 3 headers, ~9 metrics, a
table, and bullet essays -- direct feedback was "no clear hierarchy...
nothing that actually make sense," and separately "I don't like the
yellowish look" (the amber accent) and "add a headline to every graph and
table". This round: (1) drops amber for a two-color semantic system
(teal=good/active, coral=negative/blocked) that isn't reused for four
different meanings, (2) gives every chart/table a small-caps title + a
one-line description of how to read it, (3) restyles st.tabs into a
navbar-like bar via Streamlit's underlying BaseWeb selectors, (4) adds a
"today's decision path" card -- the four real gates (evidence bar / guard
check / reviewer / order) today's one proposal actually passed through,
framed honestly as a single-candidate pipeline, not a multi-candidate
funnel this system doesn't run, and (5) an enriched open-positions table
and a filterable decision log, both built from data that already exists
(parse_occ_symbol, the audit log, live broker positions) rather than any
new data source.
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
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from pipeline.audit.log import read_log
from pipeline.risk.options_config import MAX_CONCURRENT_POSITIONS

CONTROLS_ENABLED = os.getenv("CONTROLS_ENABLED", "false").lower() in ("true", "1", "yes")

st.set_page_config(page_title="Evidence Gate", page_icon="📉", layout="wide")

# Design tokens: warm-neutral instrument-panel background, ONE brand accent
# (teal -- replacing amber after "I don't like the yellowish look"), and
# exactly two semantic colors (sage=good, coral=negative/blocked) instead
# of the four-way system the previous round used, which was itself part of
# "too many things competing." Palette also set in .streamlit/config.toml
# so native widgets (st.dataframe, st.metric) pick it up directly.
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
    [data-testid="stMetricLabel"] { font-size: 0.78rem; color: #8F8575; }

    h1.page-title { font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: 1.7rem; margin-bottom: 0.1rem; display: inline; }
    .mode-text { color: #6B6357; font-size: 0.85rem; margin-left: 0.6rem; }

    .status-line { font-size: 0.98rem; margin: 0.9rem 0 1.2rem 0; color: #C7BFAF; }
    .status-line .word { font-weight: 600; }
    .status-line .word.good { color: #6FBF8A; }
    .status-line .word.bad { color: #E0796B; }
    .status-line .word.neutral { color: #8F8575; }
    .status-line .time { color: #6B6357; font-size: 0.85em; }

    /* Every chart/table gets this: a small-caps title and a one-line
       description of how to read it -- the explicit ask this round. */
    .card-title { font-family: 'IBM Plex Mono', monospace; font-size: 0.74rem; letter-spacing: 0.07em; text-transform: uppercase; color: #EAE3D6; font-weight: 600; }
    .card-subtitle { font-size: 0.82rem; color: #8F8575; margin: 0.1rem 0 0.7rem 0; }

    .path-row { display: flex; align-items: baseline; gap: 0.7rem; padding: 0.35rem 0; border-bottom: 1px solid #262119; }
    .path-row:last-child { border-bottom: none; }
    .path-stage { font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: #6B6357; width: 6.5rem; flex-shrink: 0; }
    .path-word { font-weight: 600; width: 7rem; flex-shrink: 0; }
    .path-word.good { color: #6FBF8A; }
    .path-word.bad { color: #E0796B; }
    .path-word.neutral { color: #8F8575; }
    .path-detail { font-size: 0.86rem; color: #C7BFAF; }

    /* Navbar-style tabs: Streamlit's tabs use BaseWeb components under
       these selectors -- rendered and confirmed present in this version
       (1.62.0) before relying on them. */
    [data-baseweb="tab-list"] { gap: 0.2rem; border-bottom: 1px solid #322D26; margin-bottom: 1rem; }
    [data-baseweb="tab"] {
        font-family: 'IBM Plex Sans', sans-serif; font-size: 0.95rem; font-weight: 500;
        height: 2.8rem; color: #8F8575;
    }
    [data-baseweb="tab"][aria-selected="true"] { color: #EAE3D6; }
    [data-baseweb="tab-highlight"] { background-color: #4FBDBA; height: 2px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _card_header(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="card-title">{title}</div><div class="card-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def _clean(v):
    """None/NaN -> None, otherwise pass through -- audit log rows round-trip
    through JSON/CSV with inconsistent missing-value representations."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


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

latest_row = None
if log_df is not None and not log_df.empty:
    latest_row = log_df.sort_values("timestamp", ascending=False).iloc[0]

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
    from pipeline.options.vol import fetch_recent_closes, realized_vol

    _spot = get_spot()
    _closes = fetch_recent_closes()
    # A fresh Streamlit Cloud container has no cache file on disk at all
    # (gitignored, same as the audit log) -- refresh before reading, same
    # order run_agent.py uses, so this self-heals instead of erroring.
    refresh_vix_cache()
    _vix9d = load_cached_vix("VIX9D")
    _vix3m = load_cached_vix("VIX3M")
    _, _contango_threshold = current_contango_and_threshold()
    _vix9d_decimal = float(_vix9d.iloc[-1]) / 100.0
    _rv10d = realized_vol(_closes, 10)
    today_snapshot = {
        "spot": _spot,
        "yesterday_move_pct": float(_closes.pct_change().iloc[-1]),
        "contango": float(contango_ratio(_vix9d, _vix3m).iloc[-1]),
        "contango_threshold": _contango_threshold,
        "vix9d_decimal": _vix9d_decimal,
        "rv10d": _rv10d,
        "vol_ratio": _vix9d_decimal / _rv10d if _rv10d else None,
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

# A separate research track (pipeline/vol/, EXPERIMENT.md Experiments 13-27)
# built and validated a real volatility forecaster (HAR-X), then tested 8
# independent ways of using it to pick strikes, size positions, or gate
# trades -- all 8 came back negative. So it is INFORMATIONAL ONLY here,
# never consumed by the Picker/Guard/Reviewer pipeline above.
vol_forecast = None
try:
    from pipeline.vol.deliverable import decide as vol_decide

    # live=True: refit on all history for a CURRENT number. The walk-forward
    # series necessarily lags real data by up to one 63-day test block, which
    # was showing a 55-day-stale forecast here.
    vol_forecast = vol_decide(date.today(), live=True)
except Exception as e:
    vol_forecast_error = str(e)
else:
    vol_forecast_error = None


def _max_dd(s: pd.Series) -> float:
    return float((s.cummax() - s).max())


def _worst_year(df: pd.DataFrame, col: str) -> tuple[int, float]:
    by_year = df.groupby(df.index.year)[col].sum()
    return int(by_year.idxmin()), float(by_year.min())


# ---------------------------------------------------------------------------
# Status line: ONE sentence, derived from the most recent logged decision.
# ---------------------------------------------------------------------------
def _status_line(latest_row: pd.Series | None) -> tuple[str, str, str, str]:
    """Returns (semantic_class, word, rest_of_sentence, timestamp)."""
    if log_df is None:
        return "neutral", "Status unknown", "could not read the decision log.", ""
    if latest_row is None:
        return "neutral", "Not yet run", "no decisions logged today.", ""

    outcome = _clean(latest_row.get("outcome"))
    ts = str(latest_row.get("timestamp", ""))

    if outcome == "SOLD":
        n = int(latest_row["proposed_contracts"]) if pd.notna(latest_row.get("proposed_contracts")) else "?"
        return ("good", "Trading",
                f"opened {latest_row.get('short_symbol')} / {latest_row.get('long_symbol')}, {n} contract(s).", ts)
    if outcome == "DRY_RUN":
        return ("neutral", "Dry run",
                f"would have opened {latest_row.get('short_symbol')} / {latest_row.get('long_symbol')} -- no real order sent.", ts)
    if outcome == "SKIPPED":
        reasons = latest_row.get("guards_failed")
        reason_text = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) and reasons else "no reason recorded."
        return ("bad", "Declined to trade", reason_text, ts)
    if outcome == "CLOSED":
        return ("neutral", "Position closed", str(latest_row.get("close_reason", "")), ts)
    if outcome == "EMERGENCY_CLOSE_ORPHAN":
        return ("bad", "Emergency close", str(latest_row.get("close_reason", "")), ts)
    return ("neutral", str(outcome), "", ts)


status_class, status_word, status_rest, status_ts = _status_line(latest_row)
time_html = f' <span class="time">({status_ts})</span>' if status_ts else ""
st.markdown(
    f'<p class="status-line"><span class="word {status_class}">{status_word}</span> &mdash; {status_rest}{time_html}</p>',
    unsafe_allow_html=True,
)

tab_overview, tab_track_record, tab_log, tab_how = st.tabs(
    ["Overview", "Track record", "Decision log", "How it works"]
)

# ---------------------------------------------------------------------------
# Overview: today, and only today. Four headline+subtext cards -- account,
# market, volatility, and the decision path -- then the positions table.
# The historical pitch lives entirely in Track record, not duplicated here.
# ---------------------------------------------------------------------------
with tab_overview:
    n_open = len(account_state.get("raw_positions") or []) if account_state is not None else 0

    with st.container(border=True):
        _card_header("Account", "Cash plus what any open positions are worth right now")
        if account_error is not None:
            st.caption(f"Live account data unavailable right now ({account_error}).")
        elif account_state is not None:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Equity", f"${account_state['current_equity']:,.0f}")
            col2.metric("Cash", f"${account_state['cash']:,.0f}")
            col3.metric("Options buying power", f"${account_state['options_buying_power']:,.0f}")
            col4.metric("Positions open", f"{n_open} of {MAX_CONCURRENT_POSITIONS}")

    with st.container(border=True):
        _card_header("Today's market", "Live SPY price and the two numbers the Guard checks before opening anything")
        if snapshot_error is not None:
            st.caption(f"Live market data unavailable right now ({snapshot_error}).")
        elif today_snapshot is not None:
            s = today_snapshot
            col1, col2, col3 = st.columns(3)
            col1.metric("SPY spot", f"${s['spot']:.2f}")
            col2.metric("Yesterday's move", f"{s['yesterday_move_pct']:+.2%}",
                        help="Blocks a new trade above 2% in either direction.")
            col3.metric("Contango (VIX3M/VIX9D)", f"{s['contango']:.3f}",
                        help="Below its own trailing 33rd percentile means the term structure is flattening -- blocks a new trade.")
            blocks = []
            if abs(s["yesterday_move_pct"]) > 0.02:
                blocks.append(f"SPY moved {s['yesterday_move_pct']:+.1%} yesterday")
            if s["contango_threshold"] is not None and s["contango"] < s["contango_threshold"]:
                blocks.append(f"term structure is flattening ({s['contango']:.3f} < {s['contango_threshold']:.3f})")
            st.caption("Would block a new trade today: " + "; ".join(blocks) + "." if blocks else "Nothing here would block a new trade today.")

    with st.container(border=True):
        _card_header("Volatility (SPY)", "Implied vs. realized -- whether selling premium is currently well paid. Bands are a reasonable first cut, not backtested.")
        if snapshot_error is not None:
            st.caption(f"Live market data unavailable right now ({snapshot_error}).")
        elif today_snapshot is not None and today_snapshot["vol_ratio"] is not None:
            ratio = today_snapshot["vol_ratio"]
            if ratio > 1.15:
                verdict_class, verdict_text = "good", "Rich -- selling is well compensated right now"
            elif ratio < 0.85:
                verdict_class, verdict_text = "bad", "Thin -- selling isn't well compensated right now"
            else:
                verdict_class, verdict_text = "neutral", "Fair -- normal compensation"
            col1, col2, col3 = st.columns(3)
            col1.metric("VIX9D (implied)", f"{today_snapshot['vix9d_decimal']:.1%}")
            col2.metric("Realized vol (10d)", f"{today_snapshot['rv10d']:.1%}")
            col3.metric("Ratio", f"{ratio:.2f}")
            st.markdown(f'<span class="path-word {verdict_class}">{verdict_text}</span>', unsafe_allow_html=True)
        else:
            st.caption("Not enough data to compute today.")

    with st.container(border=True):
        _card_header("Volatility forecast (research track)",
                     "HAR-X, a separate model validated on real data (EXPERIMENT.md Exp. 14/18) -- informational only, not used by the Picker, Guard, or Reviewer above.")
        if vol_forecast_error is not None:
            st.caption(f"Forecast unavailable right now ({vol_forecast_error}).")
        elif vol_forecast is not None:
            col1, col2 = st.columns(2)
            col1.metric("Forecasted annualized vol", f"{vol_forecast['forecast_vol_annualized_pct']:.1f}%",
                        help=f"As of {vol_forecast['forecast_as_of']} (walk-forward, no lookahead).")
            col2.metric("Implied breach prob. (3% / weekly)", f"{vol_forecast['forecast_breach_prob']:.1%}")
            st.caption(
                "8 independent tests (strike timing, position sizing, a skip filter) all failed to convert this "
                "forecast into a validated trading edge -- shown here as context, not a signal. See EXPERIMENT.md, "
                "\"Volatility Track — Final Synthesis.\""
            )
        else:
            st.caption("Forecast not available.")

    with st.container(border=True):
        _card_header("Today's decision path", "The gates one proposal a day has to clear, in order. Evidence gate is a standing backtest fact (not recomputed daily); the rest are today's actual run.")

        rows = []
        if gate_df is None:
            rows.append(("1. Evidence", "neutral", "not computed"))
        elif gate_choice is None:
            rows.append(("1. Evidence", "bad", "no cell currently clears the 2-SE bar"))
        else:
            rows.append(("1. Evidence", "good",
                         f"{gate_choice['distance']:.0%} / ${gate_choice['width']:.0f} clears, cushion {gate_choice['cushion_se']:.2f} SE"))

        if latest_row is None:
            rows.append(("2. Guards", "neutral", "no decision logged today"))
            rows.append(("3. Reviewer", "neutral", "--"))
            rows.append(("4. Order", "neutral", "--"))
        else:
            guards_checked = _clean(latest_row.get("guards_checked"))
            guards_failed = latest_row.get("guards_failed")
            has_failures = isinstance(guards_failed, list) and len(guards_failed) > 0
            if guards_checked is None:
                rows.append(("2. Guards", "neutral", "not reached today"))
            elif has_failures:
                rows.append(("2. Guards", "bad", f"{int(guards_checked)} checked -- blocked: " + "; ".join(str(g) for g in guards_failed)))
            else:
                rows.append(("2. Guards", "good", f"all {int(guards_checked)} passed"))

            reviewer_decision = _clean(latest_row.get("reviewer_decision"))
            if reviewer_decision is None:
                rows.append(("3. Reviewer", "neutral", "not reached today"))
            else:
                reviewer_reason = _clean(latest_row.get("reviewer_reason")) or ""
                r_class = "good" if reviewer_decision == "APPROVE" else ("bad" if reviewer_decision == "VETO" else "neutral")
                rows.append(("3. Reviewer", r_class, f"{reviewer_decision} -- {reviewer_reason}"))

            outcome_map = {
                "SOLD": ("good", "sent live"),
                "DRY_RUN": ("neutral", "dry run, no order sent"),
                "SKIPPED": ("bad", "never reached -- blocked upstream"),
                "CLOSED": ("neutral", "position closed"),
                "EMERGENCY_CLOSE_ORPHAN": ("bad", "emergency close"),
            }
            outcome = _clean(latest_row.get("outcome"))
            o_class, o_detail = outcome_map.get(outcome, ("neutral", str(outcome) if outcome else "no decision today"))
            rows.append(("4. Order", o_class, o_detail))

        html_rows = "".join(
            f'<div class="path-row"><span class="path-stage">{stage}</span>'
            f'<span class="path-word {cls}">{cls.upper() if cls != "neutral" else "--"}</span>'
            f'<span class="path-detail">{detail}</span></div>'
            for stage, cls, detail in rows
        )
        st.markdown(html_rows, unsafe_allow_html=True)

    # ------------------------------------------------------------------
    # Open positions -- enriched from real broker legs + the matching
    # audit-log row (for credit/max-loss, which the broker doesn't carry).
    # ------------------------------------------------------------------
    if account_error is None and n_open > 0 and account_state is not None:
        with st.container(border=True):
            _card_header("Open positions", "Live from Alpaca, joined to the audit log for what was collected and the max loss at entry")
            from pipeline.options.contracts import parse_occ_symbol

            raw_by_symbol = {p.symbol: p for p in account_state["raw_positions"]}
            today = date.today()
            spot = today_snapshot["spot"] if today_snapshot is not None else None
            position_rows = []
            for spread in account_state["open_positions"]:
                short_sym, long_sym = spread["short_symbol"], spread["long_symbol"]
                try:
                    short_info = parse_occ_symbol(short_sym)
                    long_info = parse_occ_symbol(long_sym)
                except ValueError:
                    short_info = long_info = None

                unrealized = 0.0
                for sym in (short_sym, long_sym):
                    p = raw_by_symbol.get(sym)
                    if p is not None and p.unrealized_pl is not None:
                        unrealized += float(p.unrealized_pl)

                if short_info is not None and spot is not None:
                    strike, right = short_info["strike"], short_info["right"]
                    room_pct = (spot - strike) / spot if right == "P" else (strike - spot) / spot
                    expires_days = (short_info["expiry"] - today).days
                    strikes_text = f"SELL ${strike:.2f}{right} / BUY ${long_info['strike']:.2f}{right}"
                    underlying = short_info["root"]
                else:
                    room_pct, expires_days, strikes_text, underlying = None, None, f"{short_sym} / {long_sym}", "?"

                position_rows.append({
                    "underlying": underlying,
                    "strikes": strikes_text,
                    "room": f"{room_pct:+.1%}" if room_pct is not None else "-",
                    "expires": f"{expires_days}d" if expires_days is not None else "-",
                    "qty": spread["contracts"],
                    "collected": f"${spread['credit_per_contract'] * spread['contracts']:,.2f}",
                    "max loss": f"${spread['max_loss_total']:,.0f}",
                    "unrealized": f"${unrealized:+,.2f}",
                })
            st.dataframe(pd.DataFrame(position_rows), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Track record: the entire "why trust this" case in one place.
# ---------------------------------------------------------------------------
with tab_track_record:
    if curve_error is not None:
        st.error(f"Could not render the equity curve ({curve_error}).")
    elif curve_df is None:
        st.warning("Reconstruction has not been computed yet. Run `python -m pipeline.backtest.reconstruct`.")
    else:
        _card_header(
            "Equity curve, 2016-2026",
            "Cumulative P&L per contract, $ -- trade every week vs. the VIX term-structure filter. "
            "Fees before Feb 2024 are reconstructed from VIX9D and validated per volatility quartile (EXPERIMENT.md, Exp. 12d).",
        )
        st.line_chart(
            curve_df[["cum_pnl_unfiltered", "cum_pnl_filtered"]].rename(columns={
                "cum_pnl_unfiltered": "trade every week", "cum_pnl_filtered": "VIX filter",
            }),
            color=["#E0796B", "#6FBF8A"],
        )

        dd_u, dd_f = _max_dd(curve_df["cum_pnl_unfiltered"]), _max_dd(curve_df["cum_pnl_filtered"])
        wy_u, wy_f = _worst_year(curve_df, "pnl_unfiltered"), _worst_year(curve_df, "pnl_filtered")
        weeks_traded = int(curve_df["traded"].sum())

        col1, col2, col3 = st.columns(3)
        col1.metric("Max drawdown, $/contract", f"{dd_f:.2f}", delta=f"{dd_f - dd_u:+.2f} vs. unfiltered", delta_color="inverse")
        col2.metric("Worst year, filtered", f"{wy_f[1]:+.2f}", help=f"Year {wy_f[0]}. Unfiltered: {wy_u[1]:+.2f} in {wy_u[0]}.")
        col3.metric("Weeks traded", f"{weeks_traded} of {len(curve_df)}")

        with st.expander("SPY and cash, for shape comparison (indexed, not dollar-matched)"):
            _card_header("SPY vs. cash, indexed to 100", "Shape comparison only -- not on the same $-per-contract basis as the chart above.")
            st.line_chart(
                curve_df[["spy_indexed", "cash_indexed"]].rename(columns={
                    "spy_indexed": "SPY (indexed)", "cash_indexed": "cash @ 3%/yr (indexed)",
                }),
                color=["#8F8575", "#4A4438"],
            )

    st.divider()

    if gate_error is not None:
        st.error(f"Could not render the evidence gate ({gate_error}).")
    elif gate_df is None:
        st.warning("Evidence gate not computed yet.")
    else:
        _card_header("Evidence gate", "Every (distance, width) combination swept against 128 real historical weeks. A cell only ships if its win-rate cushion clears 2 standard errors above breakeven.")
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
# Decision log: filter chips over real outcome/guard/reviewer values, a
# synthesized reasoning column, full audit trail one click away.
# ---------------------------------------------------------------------------
with tab_log:
    _card_header("Decisions", "Every day the agent runs, including a day it declines to trade, gets a row here")

    if log_error is not None:
        st.error(f"Could not render the decision log ({log_error}).")
    elif log_df is None or log_df.empty:
        st.write("No decisions logged yet.")
    else:
        def _category(row) -> str:
            outcome = row.get("outcome")
            if outcome == "SOLD":
                return "Traded"
            if outcome == "DRY_RUN":
                return "Dry run"
            if outcome == "SKIPPED":
                reasons = row.get("guards_failed")
                if isinstance(reasons, list) and any(str(r).startswith("REVIEWER_VETO") for r in reasons):
                    return "Reviewer-vetoed"
                return "Guard-blocked"
            return "Other"

        def _reason(row) -> str:
            if row.get("outcome") == "SOLD":
                return f"{row.get('short_symbol')} / {row.get('long_symbol')}, {row.get('proposed_contracts')} contract(s)"
            if row.get("outcome") == "SKIPPED":
                reasons = row.get("guards_failed")
                return "; ".join(str(r) for r in reasons) if isinstance(reasons, list) and reasons else ""
            if row.get("outcome") == "CLOSED":
                return str(row.get("close_reason", ""))
            return ""

        log_df = log_df.copy()
        log_df["category"] = log_df.apply(_category, axis=1)
        log_df["reason"] = log_df.apply(_reason, axis=1)

        options = ["All", "Traded", "Guard-blocked", "Reviewer-vetoed", "Dry run"]
        choice = st.segmented_control("Filter", options, default="All", label_visibility="collapsed")
        filtered = log_df if choice in (None, "All") else log_df[log_df["category"] == choice]

        recent = filtered.sort_values("timestamp", ascending=False).head(10)
        st.dataframe(recent[["timestamp", "mode", "outcome", "reason"]], width="stretch", hide_index=True)

        with st.expander(f"Full audit trail ({len(log_df)} rows, every field)"):
            st.dataframe(log_df.sort_values("timestamp", ascending=False), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# How it works: a real sequence, so numbering here encodes something true.
# ---------------------------------------------------------------------------
with tab_how:
    _card_header("How it works", "Picker -> Guard -> Reviewer -> order, in order")
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
