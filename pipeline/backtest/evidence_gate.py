"""
Turn the backtest's per-cell outcomes into a decision: which (distance,
width) combinations clear a 2-standard-error win-rate cushion over their own
breakeven rate, computed from n_eff non-overlapping weeks (Part 2B).

Deliberately does NOT pick "the distance" -- it reports every cell that
clears the bar (or none), and a separate, later selection step (out of scope
for this file) is responsible for choosing among survivors, e.g. by P&L.
"""

from __future__ import annotations

import math

import pandas as pd

SE_THRESHOLD = 2.0

# A cell needs at least this many non-overlapping weeks to be gate-eligible
# at all, regardless of its cushion. Without this floor, a thin, zero-loss
# corner cell (win_rate == 1.0, raw SE == 0) could win choose_distance_width's
# idxmax() purely on an infinite cushion_se, ahead of every real, well-tested
# cell -- not yet triggered in the current sweep (closest is 0.9917 at
# 5%/$1, n=120) but one re-run or one added distance away.
MIN_N_FOR_GATE = 30


def _cushion_for_cell(cell: pd.DataFrame) -> dict:
    n = len(cell)
    if n == 0:
        return None
    win_rate = cell["win"].mean()
    avg_credit = cell["credit"].mean()
    # net_credit (credit minus any per-share slippage haircut, see
    # spread_backtest.py's slippage_per_share) may not exist on older CSVs;
    # fall back to gross credit, matching the pre-cost-model behavior.
    avg_net_credit = cell["net_credit"].mean() if "net_credit" in cell else avg_credit
    width = cell["width"].iloc[0]
    # Breakeven win rate assuming every loss is a max loss (conservative --
    # Part 2B notes the real backtest P&L, used below via mean_net_pnl, is
    # the less conservative and more trustworthy number). Uses net_credit so
    # a nonzero slippage haircut raises the bar a real trade would have to
    # clear, not just the theoretical gross-quote one (Headline finding 1).
    required_win_rate = 1 - (avg_net_credit / width)
    if 0 < win_rate < 1:
        se = math.sqrt(win_rate * (1 - win_rate) / n)
    else:
        # Continuity-corrected estimate (as if one extra observation went
        # the other way) instead of the raw formula's se=0 at a perfect
        # win rate -- se=0 previously forced cushion_se to a hardcoded
        # +/-inf, which is not a real statistic and would always win (or
        # lose) a comparison against every finite, genuinely measured cell.
        p_adj = (cell["win"].sum() + 0.5) / (n + 1)
        se = math.sqrt(p_adj * (1 - p_adj) / n)
    cushion_pp = win_rate - required_win_rate
    cushion_se = cushion_pp / se if se > 0 else 0.0
    eligible = n >= MIN_N_FOR_GATE
    return {
        "distance": cell["distance"].iloc[0],
        "width": width,
        "n": n,
        "win_rate": win_rate,
        "avg_credit": avg_credit,
        "required_win_rate": required_win_rate,
        "se": se,
        "cushion_pp": cushion_pp,
        "cushion_se": cushion_se,
        "eligible": eligible,
        "passes_gate": eligible and cushion_se >= SE_THRESHOLD,
    }


def compute_gate(results_df: pd.DataFrame) -> pd.DataFrame:
    valid = results_df[~results_df["missing_data"]]
    rows = []
    for (distance, width), cell in valid.groupby(["distance", "width"]):
        row = _cushion_for_cell(cell)
        if row is not None:
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["distance", "width"]).reset_index(drop=True)


def tradable_distances(gate_df: pd.DataFrame) -> pd.DataFrame:
    """Cells clearing the 2-SE bar. Empty means: nothing clears it, and per
    Part 0's contingency the system should decline to trade rather than
    quietly lowering the bar."""
    return gate_df[gate_df["passes_gate"]].copy()


if __name__ == "__main__":
    results = pd.read_csv("output/data/spread_backtest_results.csv")
    results["win"] = results["win"].map({"True": True, "False": False, True: True, False: False})

    gate = compute_gate(results)
    pd.set_option("display.width", 160)
    print(gate.to_string(index=False))

    survivors = tradable_distances(gate)
    print()
    if survivors.empty:
        print("No (distance, width) cell clears the 2-SE bar. The system declines to trade.")
    else:
        print(f"{len(survivors)} cell(s) clear the 2-SE bar:")
        print(survivors.to_string(index=False))

    from pipeline.io_utils import atomic_to_csv

    atomic_to_csv(gate, "output/data/evidence_gate_results.csv", index=False)
    print("\nSaved to output/data/evidence_gate_results.csv")
