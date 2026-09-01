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

st.title("Evidence Gate")
st.caption(
    "An options agent that sells S&P 500 volatility premium only when the measured edge "
    "clears a statistical bar -- and refuses to trade when it doesn't."
)
st.caption(f"Mode: {'controls enabled (local)' if CONTROLS_ENABLED else 'read-only (public)'}")

st.divider()

# ---------------------------------------------------------------------------
# Headline account numbers -- live if reachable, a plain message if not.
# ---------------------------------------------------------------------------
st.subheader("Account")

account_state = None
try:
    from pipeline.execution.broker import get_account_state
    from pipeline.execution.positions import open_spread_positions

    account_state = get_account_state(open_positions=open_spread_positions())
except Exception as e:
    st.info(f"Live account data unavailable right now ({e}). Showing backtest and log content below.")

if account_state is not None:
    n_open = len(account_state["open_positions"])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Equity", f"${account_state['current_equity']:,.0f}",
                help="Total account value, cash plus any open positions marked to market.")
    col2.metric("Options buying power", f"${account_state['options_buying_power']:,.0f}",
                help="How much the broker will let this account commit to new options positions right now.")
    col3.metric("Positions open", f"{n_open} of {MAX_CONCURRENT_POSITIONS}",
                help="Concurrent put credit spreads open now, against the hard cap the Guard enforces.")
    col4.metric("Options level", account_state["options_approved_level"],
                help="Alpaca's own broker-approved permission tier (0-3). Level 3 is required to trade "
                     "defined-risk multi-leg spreads like this system's put credit spreads -- it's the "
                     "account's real regulatory clearance, not something this app computes.")

    if n_open == 0:
        st.write("No open positions right now.")
    else:
        st.write(f"{n_open} open position(s) -- detail rendering lands with reconcile.py (post-hackathon stretch item).")

st.divider()

# ---------------------------------------------------------------------------
# S1/S2 (the plan's flagship artifact): the ten-year reconstructed track
# record, unfiltered vs the VIX term-structure filter, with SPY and cash
# as shape-only reference lines.
# ---------------------------------------------------------------------------
st.subheader("Ten-year track record (reconstructed)")
st.write(
    "Real option prices only go back to Feb 2024, so fees before that are reconstructed from "
    "CBOE's VIX9D and validated per volatility quartile before use -- see `EXPERIMENT.md`, "
    "Experiment 12d. Every loss shown is computed from real SPY closes; only the credit side "
    "before Feb 2024 is modelled."
)

curve_path = "output/data/equity_curve.csv"
try:
    if os.path.exists(curve_path):
        curve_df = pd.read_csv(curve_path, parse_dates=["entry"]).set_index("entry")

        st.caption("Cumulative P&L per contract, $ -- trade every week vs. the VIX term-structure filter")
        st.line_chart(curve_df[["cum_pnl_unfiltered", "cum_pnl_filtered"]].rename(columns={
            "cum_pnl_unfiltered": "trade every week", "cum_pnl_filtered": "VIX filter",
        }))

        def _max_dd(s: pd.Series) -> float:
            return float((s.cummax() - s).max())

        def _worst_year(df: pd.DataFrame, col: str) -> tuple[int, float]:
            by_year = df.groupby(df.index.year)[col].sum()
            return int(by_year.idxmin()), float(by_year.min())

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
            st.line_chart(curve_df[["spy_indexed", "cash_indexed"]].rename(columns={
                "spy_indexed": "SPY (indexed)", "cash_indexed": "cash @ 3%/yr (indexed)",
            }))
    else:
        st.warning(
            "Reconstruction has not been computed yet. Run `python -m pipeline.backtest.reconstruct`."
        )
except Exception as e:
    st.error(f"Could not render the equity curve ({e}).")

st.divider()

# ---------------------------------------------------------------------------
# The flagship finding: the evidence gate's per-(distance, width) table.
# ---------------------------------------------------------------------------
st.subheader("The evidence gate")
st.write(
    "Every (distance, width) combination swept against 128 real historical weeks. "
    "A cell only ships if its measured win-rate cushion clears 2 standard errors "
    "above its own breakeven rate -- see `EXPERIMENT.md`, Experiment 11."
)

gate_path = "output/data/evidence_gate_results.csv"
try:
    if os.path.exists(gate_path):
        gate_df = pd.read_csv(gate_path)

        # Picks the same cell the live agent would (Rule #3/#5's highest-
        # cushion tie-break) by calling the actual Picker function instead
        # of re-implementing its idxmax() logic here -- a second inline copy
        # previously risked silently diverging from selector.py the moment
        # a minimum-n eligibility floor or similar filter gets added there.
        from pipeline.options.selector import choose_distance_width

        choice = choose_distance_width(gate_df)

        display_df = gate_df.copy()
        display_df["distance"] = (display_df["distance"] * 100).round(0).astype(int).astype(str) + "%"
        display_df["width"] = "$" + display_df["width"].astype(int).astype(str)
        display_cols = ["distance", "width", "n", "win_rate", "required_win_rate", "cushion_se", "mean_net_pnl", "passes_gate"]
        styled = display_df[display_cols].rename(columns={
            "n": "weeks", "win_rate": "measured win rate", "required_win_rate": "breakeven win rate",
            "cushion_se": "cushion (SE)", "mean_net_pnl": "mean P&L/contract", "passes_gate": "clears 2 SE",
        })
        st.dataframe(styled, width='stretch', hide_index=True)

        n_survivors = int(gate_df["passes_gate"].sum())
        if choice is None:
            st.warning("No (distance, width) cell currently clears the 2-SE bar. The system declines to trade.")
        else:
            st.success(
                f"Currently tradable: {choice['distance']:.0%} distance, ${choice['width']:.0f} width "
                f"-- cushion {choice['cushion_se']:.2f} SE, {n_survivors} cell(s) clear the bar in total."
            )
    else:
        st.warning(
            "Evidence gate has not been computed yet. Run `python -m pipeline.backtest.spread_backtest` "
            "then `python -m pipeline.backtest.evidence_gate`."
        )
except Exception as e:
    st.error(f"Could not render the evidence gate table ({e}).")

st.divider()

# ---------------------------------------------------------------------------
# Decision log -- every day, including every day it did nothing.
# ---------------------------------------------------------------------------
st.subheader("Decision log")

try:
    log_df = read_log()
    if log_df.empty:
        st.write("No decisions logged yet. Every day the agent runs -- including a day it declines to trade -- gets a row here.")
    else:
        log_df = log_df.sort_values("timestamp", ascending=False)
        st.dataframe(log_df, width='stretch', hide_index=True)
except Exception as e:
    st.error(f"Could not render the decision log ({e}).")

st.divider()

st.caption(
    "Architecture: a volatility forecast feeds the Picker (fixed rules from the backtest), "
    "every proposal passes through the Guard (14 hard limits, cannot be overridden), and an "
    "LLM Reviewer may only veto or shrink a trade the Guard already approved -- never choose "
    "one, never make one bigger. See `OPTIONS_SYSTEM_PLAN.md` for the full design."
)
