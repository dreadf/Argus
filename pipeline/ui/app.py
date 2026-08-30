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

import pandas as pd
import streamlit as st

from pipeline.audit.log import read_log

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

    account_state = get_account_state()
except Exception as e:
    st.info(f"Live account data unavailable right now ({e}). Showing backtest and log content below.")

if account_state is not None:
    n_open = len(account_state["open_positions"])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Equity", f"${account_state['current_equity']:,.0f}")
    col2.metric("Options buying power", f"${account_state['options_buying_power']:,.0f}")
    col3.metric("Positions open", f"{n_open} of 4")
    col4.metric("Options level", account_state["options_approved_level"])

    if n_open == 0:
        st.write("No open positions right now.")
    else:
        st.write(f"{n_open} open position(s) -- detail rendering lands with reconcile.py (post-hackathon stretch item).")

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
if os.path.exists(gate_path):
    gate_df = pd.read_csv(gate_path)
    gate_df["distance"] = (gate_df["distance"] * 100).round(0).astype(int).astype(str) + "%"
    gate_df["width"] = "$" + gate_df["width"].astype(int).astype(str)
    display_cols = ["distance", "width", "n", "win_rate", "required_win_rate", "cushion_se", "mean_net_pnl", "passes_gate"]
    styled = gate_df[display_cols].rename(columns={
        "n": "weeks", "win_rate": "measured win rate", "required_win_rate": "breakeven win rate",
        "cushion_se": "cushion (SE)", "mean_net_pnl": "mean P&L/contract", "passes_gate": "clears 2 SE",
    })
    st.dataframe(styled, width='stretch', hide_index=True)

    survivors = gate_df[gate_df["passes_gate"]]
    if survivors.empty:
        st.warning("No (distance, width) cell currently clears the 2-SE bar. The system declines to trade.")
    else:
        best = survivors.loc[gate_df.loc[survivors.index, "cushion_se"].idxmax()]
        st.success(
            f"Currently tradable: {best['distance']} distance, {best['width']} width "
            f"-- cushion {best['cushion_se']:.2f} SE, {len(survivors)} cell(s) clear the bar in total."
        )
else:
    st.warning(
        "Evidence gate has not been computed yet. Run `python -m pipeline.backtest.spread_backtest` "
        "then `python -m pipeline.backtest.evidence_gate`."
    )

st.divider()

# ---------------------------------------------------------------------------
# Decision log -- every day, including every day it did nothing.
# ---------------------------------------------------------------------------
st.subheader("Decision log")

log_df = read_log()
if log_df.empty:
    st.write("No decisions logged yet. Every day the agent runs -- including a day it declines to trade -- gets a row here.")
else:
    log_df = log_df.sort_values("timestamp", ascending=False)
    st.dataframe(log_df, width='stretch', hide_index=True)

st.divider()

st.caption(
    "Architecture: a volatility forecast feeds the Picker (fixed rules from the backtest), "
    "every proposal passes through the Guard (14 hard limits, cannot be overridden), and an "
    "LLM Reviewer may only veto or shrink a trade the Guard already approved -- never choose "
    "one, never make one bigger. See `OPTIONS_SYSTEM_PLAN.md` for the full design."
)
