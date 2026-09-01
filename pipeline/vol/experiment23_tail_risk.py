"""
Experiment 23: does the volatility forecast improve RISK-ADJUSTED weekly
P&L, rather than the MEAN weekly P&L every H4 test (Experiments 15, 19, 20,
21) measured?

Motivation, from the literature (see SOURCES.md): Moreira & Muir (2017) and
the volatility-managed-portfolios literature use a volatility forecast to
SIZE risk, not to TIME which asset to pick -- a vol forecast's canonical use
is shrinking the tail, not raising the mean. Independently, Wade (2026)
found that the model with the best forecast accuracy, the best ranking
accuracy, and the best portfolio Sharpe ratio can be three different models
-- exactly what Experiment 19 found here (a significantly better forecaster
produced no better mean P&L). Every H4 test so far only ever compared
means. This experiment asks the question none of them asked.

Concretely: Experiment 19 showed the HAR-X-driven adaptive strategy
concentrating its picks at the 4% distance (the safest, most defensive
choice) 68/125 weeks -- consistent with a strategy that trades defensively
without necessarily changing its average outcome. If so, its risk profile
(downside deviation, drawdown, tail losses) should differ from the fixed
baseline even where its mean does not.

Design, pre-registered before running:
  - Reuses Experiment 20's exact setup: HAR-X forecaster, empirical/
    skew-aware breach probability, $0.05/share slippage (the realistic
    cost case), the same 125-126 weeks.
  - Statistic (fixed in advance): Sortino ratio of the adaptive weekly
    net P&L series minus the Sortino ratio of the fixed-baseline series
    (MAR = 0, since net_pnl is already a dollar P&L per week, not a
    return needing a risk-free subtraction).
  - Also reports, descriptively: max drawdown of the cumulative P&L curve,
    and CVaR at the 10% tail -- not gated on, since only the pre-registered
    Sortino diff decides the outcome, but informative for interpreting it.
  - Gate: the SAME randomization null used in Experiment 21 (forecast
    values reshuffled across the 125 entry dates, 2000x), applied to this
    new statistic. This is the sixth look at the same 125-week sample
    (after Experiments 15, 19, 20, 20's closing check, and 21) -- stated
    up front, not glossed over.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.vol.overlay import build_weekly_forecasts, run_overlay
from pipeline.vol.skew_breach import build_standardized_return_distribution, empirical_breach_prob
from pipeline.vol.step0_recheck import load_corrected_results

SLIPPAGE = 0.05
N_PERMUTATIONS = 2000
SEED = 20260901
CVAR_TAIL = 0.10


def sortino_ratio(pnl: pd.Series, mar: float = 0.0) -> float:
    excess = pnl - mar
    downside = excess.clip(upper=0.0)
    downside_dev = np.sqrt((downside ** 2).mean())
    if downside_dev == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float(excess.mean() / downside_dev)


def max_drawdown(pnl: pd.Series) -> float:
    cum = pnl.cumsum()
    running_peak = cum.cummax()
    drawdown = cum - running_peak
    return float(drawdown.min())  # most negative point, i.e. the worst drawdown


def cvar(pnl: pd.Series, tail: float = CVAR_TAIL) -> float:
    n_tail = max(1, int(np.ceil(len(pnl) * tail)))
    return float(pnl.sort_values().iloc[:n_tail].mean())


def _breach_fn():
    std_returns = build_standardized_return_distribution()

    def fn(fvol, distance, horizon_days):
        return empirical_breach_prob(std_returns, fvol, distance, horizon_days)
    return fn


def run() -> dict:
    breach_fn = _breach_fn()

    # Base forecast built ONCE and reused for every permutation (per
    # Experiment 21's precedent) -- rebuilding the HAR-X walk-forward fit
    # 2000x would be wasteful and is not what's being tested here; only the
    # forecast-to-week ALIGNMENT is being permuted, not the forecast itself.
    results = load_corrected_results()
    valid = results[~results["missing_data"]].copy()
    entries = sorted(valid["entry"].unique())  # matches run_overlay's own entries construction exactly
    base_forecast = build_weekly_forecasts(model="harx")
    base_forecast_by_date = base_forecast.reindex(pd.to_datetime(entries)).ffill()

    real_summary, real_paired = run_overlay(
        SLIPPAGE, model="harx", breach_fn=breach_fn,
        forecast_by_date=base_forecast_by_date, return_paired=True,
    )

    real_sortino_adaptive = sortino_ratio(real_paired["adaptive"])
    real_sortino_baseline = sortino_ratio(real_paired["baseline"])
    real_diff = real_sortino_adaptive - real_sortino_baseline

    real_mdd_adaptive = max_drawdown(real_paired["adaptive"])
    real_mdd_baseline = max_drawdown(real_paired["baseline"])
    real_cvar_adaptive = cvar(real_paired["adaptive"])
    real_cvar_baseline = cvar(real_paired["baseline"])

    rng = np.random.default_rng(SEED)
    null_diffs = np.empty(N_PERMUTATIONS)
    for i in range(N_PERMUTATIONS):
        _, paired = run_overlay(
            SLIPPAGE, model="harx", breach_fn=breach_fn,
            forecast_by_date=base_forecast_by_date, rng=rng, return_paired=True,
        )
        null_diffs[i] = sortino_ratio(paired["adaptive"]) - sortino_ratio(paired["baseline"])

    empirical_p_one_sided = float((null_diffs >= real_diff).mean())

    return {
        "n_weeks": real_summary["n_weeks"],
        "real_sortino_adaptive": real_sortino_adaptive,
        "real_sortino_baseline": real_sortino_baseline,
        "real_sortino_diff": real_diff,
        "real_mdd_adaptive": real_mdd_adaptive,
        "real_mdd_baseline": real_mdd_baseline,
        "real_cvar10_adaptive": real_cvar_adaptive,
        "real_cvar10_baseline": real_cvar_baseline,
        "mean_pnl_diff_for_reference": real_summary["mean_pnl_diff"],
        "null_mean": null_diffs.mean(),
        "null_std": null_diffs.std(),
        "empirical_p_one_sided": empirical_p_one_sided,
        "n_permutations": N_PERMUTATIONS,
    }


if __name__ == "__main__":
    out = run()
    print("=== Experiment 23: risk-adjusted (Sortino/drawdown/CVaR) re-test of H4, HAR-X + empirical breach prob ===\n")
    print(f"n weeks: {out['n_weeks']}\n")
    print(f"Sortino ratio, adaptive: {out['real_sortino_adaptive']:.4f}")
    print(f"Sortino ratio, baseline: {out['real_sortino_baseline']:.4f}")
    print(f"Sortino diff (pre-registered statistic): {out['real_sortino_diff']:+.4f}\n")
    print(f"Max drawdown, adaptive: {out['real_mdd_adaptive']:.3f}")
    print(f"Max drawdown, baseline: {out['real_mdd_baseline']:.3f}")
    print(f"CVaR(10%), adaptive: {out['real_cvar10_adaptive']:.4f}")
    print(f"CVaR(10%), baseline: {out['real_cvar10_baseline']:.4f}")
    print(f"(for reference, mean P&L diff was: {out['mean_pnl_diff_for_reference']:+.4f})\n")
    print(f"Randomization null ({out['n_permutations']} shuffles): mean={out['null_mean']:.4f}, std={out['null_std']:.4f}")
    print(f"Empirical p-value, one-sided (null >= real): {out['empirical_p_one_sided']:.4f}")
