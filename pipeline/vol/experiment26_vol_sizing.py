"""
Experiment 26: does inverse-volatility POSITION SIZING at the fixed 3%/$5
baseline cell -- scaling contract count DOWN in weeks HAR-X forecasts as
high-vol and UP in calm weeks -- improve risk-adjusted P&L, versus constant
sizing?

This is NOT a re-test of Experiments 15/19/20/21/22/23/24. Those all tested
STRIKE SELECTION (which distance to trade, holding size fixed). This tests
literal contract-count SCALING at one fixed strike -- the actual Moreira &
Muir (2017) mechanism ("scale portfolio weight by inverse trailing
variance," SOURCES.md), never directly tested in this track. Experiment 23
came closest (Sortino/drawdown/CVaR of the adaptive-DISTANCE strategy) but
that conflated strike choice with any sizing effect; this isolates sizing
alone at a single, always-traded cell.

Method: multiplier_t = (1 / forecast_vol_t) / mean(1 / forecast_vol) over
the sample -- normalized to mean 1 so average exposure matches the
constant-sizing baseline exactly (the risk-adjusted comparison must not
just be "smaller average size = smaller drawdown," which would be trivial).
Capped at [0.5x, 2.0x], a conventional vol-targeting leverage band. Scaled
P&L = multiplier_t * baseline_net_pnl_t (P&L scales ~linearly with contract
count at this scale, ignoring margin/liquidity constraints the bot's own
guards already handle separately).

Pre-registered statistic: Sortino ratio of the multiplier-scaled series
minus the constant-sizing baseline's, at $0.05 slippage, the 125-126 week
sample. Gated by the SAME randomization null used throughout this track
(HAR-X forecast reshuffled across entry weeks, 2000x) -- this is the
seventh distinct mechanism tested on this sample, stated up front.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.vol.experiment23_tail_risk import cvar, max_drawdown, sortino_ratio
from pipeline.vol.overlay import BASELINE_DISTANCE, BASELINE_WIDTH, build_weekly_forecasts
from pipeline.vol.step0_recheck import load_corrected_results

SLIPPAGE = 0.05
N_PERMUTATIONS = 2000
SEED = 20260901
CAP_LOW, CAP_HIGH = 0.5, 2.0


def _build_multiplier(forecast_vol: pd.Series) -> pd.Series:
    inv = 1.0 / forecast_vol
    mult = inv / inv.mean()
    return mult.clip(CAP_LOW, CAP_HIGH)


def run() -> dict:
    results = load_corrected_results()
    valid = results[~results["missing_data"]].copy()
    baseline = valid[(valid["distance"] == BASELINE_DISTANCE) & (valid["width"] == BASELINE_WIDTH)].copy()
    baseline["net_pnl_adj"] = baseline["credit"] - SLIPPAGE - baseline["payout_owed"]
    baseline = baseline.set_index("entry").sort_index()

    entries = baseline.index
    base_forecast = build_weekly_forecasts(model="harx")
    base_forecast_by_date = base_forecast.reindex(pd.to_datetime(entries)).ffill()

    def scaled_series(forecast_by_date: pd.Series) -> pd.Series:
        mult = _build_multiplier(forecast_by_date)
        mult.index = entries  # align back to date (not Timestamp) index used by baseline
        return baseline["net_pnl_adj"] * mult

    real_scaled = scaled_series(base_forecast_by_date)
    real_sortino_scaled = sortino_ratio(real_scaled)
    real_sortino_baseline = sortino_ratio(baseline["net_pnl_adj"])
    real_diff = real_sortino_scaled - real_sortino_baseline

    rng = np.random.default_rng(SEED)
    fc_values = base_forecast_by_date.to_numpy()
    null_diffs = np.empty(N_PERMUTATIONS)
    for i in range(N_PERMUTATIONS):
        shuffled = pd.Series(rng.permutation(fc_values), index=base_forecast_by_date.index)
        s = scaled_series(shuffled)
        null_diffs[i] = sortino_ratio(s) - real_sortino_baseline

    empirical_p = float((null_diffs >= real_diff).mean())

    return {
        "n_weeks": len(baseline),
        "mean_pnl_scaled": real_scaled.mean(),
        "mean_pnl_baseline": baseline["net_pnl_adj"].mean(),
        "sortino_scaled": real_sortino_scaled,
        "sortino_baseline": real_sortino_baseline,
        "sortino_diff": real_diff,
        "mdd_scaled": max_drawdown(real_scaled),
        "mdd_baseline": max_drawdown(baseline["net_pnl_adj"]),
        "cvar10_scaled": cvar(real_scaled),
        "cvar10_baseline": cvar(baseline["net_pnl_adj"]),
        "null_mean": null_diffs.mean(),
        "null_std": null_diffs.std(),
        "empirical_p_one_sided": empirical_p,
        "n_permutations": N_PERMUTATIONS,
    }


if __name__ == "__main__":
    out = run()
    print("=== Experiment 26: inverse-vol POSITION SIZING (not strike selection) at the fixed 3%/$5 cell ===\n")
    print(f"n = {out['n_weeks']}")
    print(f"Mean P&L, scaled: {out['mean_pnl_scaled']:.4f}   baseline: {out['mean_pnl_baseline']:.4f}")
    print(f"Sortino, scaled: {out['sortino_scaled']:.4f}   baseline: {out['sortino_baseline']:.4f}")
    print(f"Sortino diff (pre-registered statistic): {out['sortino_diff']:+.4f}\n")
    print(f"Max drawdown, scaled: {out['mdd_scaled']:.3f}   baseline: {out['mdd_baseline']:.3f}")
    print(f"CVaR(10%), scaled: {out['cvar10_scaled']:.4f}   baseline: {out['cvar10_baseline']:.4f}\n")
    print(f"Randomization null ({out['n_permutations']} shuffles): mean={out['null_mean']:.4f}, std={out['null_std']:.4f}")
    print(f"Empirical p-value, one-sided (null >= real): {out['empirical_p_one_sided']:.4f}")
