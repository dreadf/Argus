"""
Experiment 20: re-runs H4 (Experiments 15 and 19) with the SAME HAR-X
forecaster (Experiment 18, the best in the track) but replaces the flat
normal-distribution breach-probability approximation with a filtered
historical simulation built from SPY's real 1993-2026 return distribution
(pipeline/vol/skew_breach.py) -- targeting the specific bottleneck Experiment
19 isolated: not forecast quality, but the probability-conversion step.
"""

from __future__ import annotations

import pandas as pd

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.overlay import run_overlay
from pipeline.vol.skew_breach import build_standardized_return_distribution, empirical_breach_prob

if __name__ == "__main__":
    std_returns = build_standardized_return_distribution()

    def breach_fn(fvol, distance, horizon_days):
        return empirical_breach_prob(std_returns, fvol, distance, horizon_days)

    rows = [run_overlay(slip, model="harx", breach_fn=breach_fn) for slip in (0.0, 0.02, 0.05)]
    result = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print("=== H4 re-tested: HAR-X forecaster + empirical skew-aware breach probability ===\n")
    print(result[["slippage", "n_weeks", "fallback_weeks", "mean_pnl_adaptive",
                   "mean_pnl_baseline", "mean_pnl_diff", "paired_t_stat", "paired_p_value",
                   "baseline_cushion_se"]].to_string(index=False))
    print()
    for row in rows:
        print(f"slippage=${row['slippage']:.2f}  adaptive distance picks: {row['adaptive_distance_dist']}")

    atomic_to_csv(result, "output/data/vol_experiment20_overlay_skew.csv", index=False)
    print("\nSaved to output/data/vol_experiment20_overlay_skew.csv")
