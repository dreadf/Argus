"""
Experiment 19: re-runs Experiment 15's H4 economic-conversion test with
Experiment 18's HAR-X forecaster (HAR + log VIX, QLIKE-fit, the best
forecaster found in this track) in place of Experiment 14's plain HAR-RV.

Question: was Experiment 15's null result (adaptive strike selection does
not beat the fixed 3%/$5 baseline) about the strategy design, or about
forecast quality specifically? Same strategy, same baseline, same
methodology -- only the forecaster changes, isolating the answer.
"""

from __future__ import annotations

import pandas as pd

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.overlay import run_overlay

if __name__ == "__main__":
    rows = [run_overlay(slip, model="harx") for slip in (0.0, 0.02, 0.05)]
    result = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print("=== H4 re-tested with HAR-X (Experiment 18's proven-better forecaster) ===\n")
    print(result[["slippage", "n_weeks", "fallback_weeks", "mean_pnl_adaptive",
                   "mean_pnl_baseline", "mean_pnl_diff", "paired_t_stat", "paired_p_value",
                   "baseline_cushion_se"]].to_string(index=False))
    print()
    for row in rows:
        print(f"slippage=${row['slippage']:.2f}  adaptive distance picks: {row['adaptive_distance_dist']}")

    atomic_to_csv(result, "output/data/vol_experiment19_overlay_harx.csv", index=False)
    print("\nSaved to output/data/vol_experiment19_overlay_harx.csv")
