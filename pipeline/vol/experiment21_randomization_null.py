"""
Experiment 21: randomization null for the week-skip filter finding in
Experiment 20's closing check -- the anti-overfitting protocol's item 9 /
the plan's kill criterion ("17 shows the real result sits inside the noise
distribution"), finally run against the actual final version of H4's signal.

This targets the specific positive-looking number from Experiment 20's
closing check, not the already-null cross-distance adaptive selection:
splitting the 125 traded weeks at the single fixed 3%/$5 cell by the
empirical-breach-probability edge (implied - forecast breach probability)
into a top half and bottom half produced mean net P&L of 0.256 vs 0.136,
nearly double, with a parametric t-test at p=0.30 -- not significant, but
a t-test on n=125 skewed weekly option P&L is a thin tool.

Statistic (fixed in advance): mean_pnl(top-half-edge weeks) -
mean_pnl(bottom-half-edge weeks), at $0.05/share slippage, at the fixed
3%/$5 cell -- exactly Experiment 20's closing-check number.

Null: reruns the same split 2000x with the HAR-X forecast randomly
reshuffled across the 125 entry dates before computing each week's edge.
This severs any real timing relationship between forecast and outcome
while holding every marginal distribution fixed (same forecast values in
circulation, same weeks traded, same market prices) -- the correct null
for "does WHEN the signal fires matter, or would any random schedule of
which weeks look rich produce the same split."
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from pipeline.vol.overlay import BASELINE_DISTANCE, BASELINE_WIDTH, build_weekly_forecasts
from pipeline.vol.skew_breach import build_standardized_return_distribution, empirical_breach_prob
from pipeline.vol.step0_recheck import load_corrected_results

SLIPPAGE = 0.05
N_PERMUTATIONS = 2000
SEED = 20260901


def _split_diff(week_data: pd.DataFrame, edges: pd.Series) -> float:
    median_edge = edges.median()
    top = week_data.loc[edges >= median_edge, "net_pnl_adj"]
    bottom = week_data.loc[edges < median_edge, "net_pnl_adj"]
    return top.mean() - bottom.mean()


def run() -> dict:
    results = load_corrected_results()
    valid = results[~results["missing_data"]].copy()
    baseline = valid[(valid["distance"] == BASELINE_DISTANCE) & (valid["width"] == BASELINE_WIDTH)].copy()
    baseline["net_pnl_adj"] = baseline["credit"] - SLIPPAGE - baseline["payout_owed"]
    baseline = baseline.set_index("entry").sort_index()

    entries = baseline.index
    horizon_days = (
        results[results["entry"].isin(entries)]
        .assign(h=lambda d: (d["expiry"] - d["entry"]).dt.days)
        .drop_duplicates("entry")
        .set_index("entry")["h"]
        .reindex(entries)
    )

    forecast = build_weekly_forecasts(model="harx")
    forecast_by_date = forecast.reindex(pd.to_datetime(entries)).ffill()
    std_returns = build_standardized_return_distribution()
    implied_p = baseline["credit"] / baseline["width"]

    def edges_from_forecast(fc: pd.Series) -> pd.Series:
        forecast_p = pd.Series(
            [
                empirical_breach_prob(std_returns, fc.iloc[i], BASELINE_DISTANCE, int(horizon_days.iloc[i]))
                for i in range(len(entries))
            ],
            index=entries,
        )
        return implied_p - forecast_p

    real_edges = edges_from_forecast(forecast_by_date)
    real_diff = _split_diff(baseline, real_edges)
    real_t, real_p = stats.ttest_ind(
        baseline.loc[real_edges >= real_edges.median(), "net_pnl_adj"],
        baseline.loc[real_edges < real_edges.median(), "net_pnl_adj"],
    )

    rng = np.random.default_rng(SEED)
    fc_values = forecast_by_date.to_numpy()
    null_diffs = np.empty(N_PERMUTATIONS)
    for i in range(N_PERMUTATIONS):
        shuffled = pd.Series(rng.permutation(fc_values), index=forecast_by_date.index)
        null_diffs[i] = _split_diff(baseline, edges_from_forecast(shuffled))

    empirical_p_one_sided = float((null_diffs >= real_diff).mean())
    empirical_p_two_sided = float((np.abs(null_diffs) >= abs(real_diff)).mean())

    return {
        "real_diff": real_diff,
        "real_t": real_t,
        "real_p_parametric": real_p,
        "null_mean": null_diffs.mean(),
        "null_std": null_diffs.std(),
        "empirical_p_one_sided": empirical_p_one_sided,
        "empirical_p_two_sided": empirical_p_two_sided,
        "n_permutations": N_PERMUTATIONS,
    }


if __name__ == "__main__":
    out = run()
    print("=== Experiment 21: randomization null for Experiment 20's week-skip-filter finding ===\n")
    print(f"Real split diff (top-half-edge - bottom-half-edge net P&L): {out['real_diff']:.4f}")
    print(f"Parametric t-test: t={out['real_t']:.2f}, p={out['real_p_parametric']:.3f}")
    print(f"Null distribution ({out['n_permutations']} shuffles): mean={out['null_mean']:.4f}, std={out['null_std']:.4f}")
    print(f"Empirical p-value, one-sided (null >= real): {out['empirical_p_one_sided']:.4f}")
    print(f"Empirical p-value, two-sided (|null| >= |real|): {out['empirical_p_two_sided']:.4f}")
