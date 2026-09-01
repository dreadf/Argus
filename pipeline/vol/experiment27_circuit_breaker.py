"""
Experiment 27: a coarse, binary circuit-breaker -- skip trading the fixed
3%/$5 cell entirely in weeks HAR-X forecasts as extreme, rather than
continuously timing strikes (Exps 15/19/20/21/22/24) or continuously
sizing positions (Exp 26). This is a genuinely weaker, different claim: not
"know which weeks are good," just "recognize the rare weeks that are
unusually dangerous and sit out," the same spirit as the live bot's own
`check_term_structure` guard (blocks when VIX3M/VIX9D falls below its own
trailing 33rd percentile, walk-forward, never a full-sample constant --
PROGRESS.md, Tue Sep 1 entry).

Threshold construction mirrors that guard's own discipline exactly: the
"extreme" cutoff is an EXPANDING (walk-forward) percentile of HAR-X's own
forecast history, never a full-sample constant, so no future information
leaks into what counts as "extreme" at any point in time. Computed on the
long ~2,016-day out-of-sample forecast series (Experiment 14/18), not just
the 125-week option sample, matching this track's "long history first"
discipline (Experiment 13a).

Null design, matched to the actual claim being tested: skipping ANY subset
of weeks trivially shrinks variance/drawdown just by having fewer
observations, so the real skip pattern must be compared against RANDOM
skip patterns of the SAME SIZE, not against the always-trade baseline
directly. This isolates whether WHICH weeks the forecast flags as extreme
carries real information, separate from the mechanical effect of skipping
weeks at all.
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


def _expanding_percentile_rank(series: pd.Series) -> pd.Series:
    """rank of series[t] among series[:t+1] (inclusive), walk-forward safe
    -- no future value ever contributes to today's percentile."""
    out = np.empty(len(series))
    values = series.to_numpy()
    for i in range(len(values)):
        window = values[: i + 1]
        out[i] = (window <= values[i]).mean()
    return pd.Series(out, index=series.index)


def run(threshold_percentile: float = 0.85) -> dict:
    results = load_corrected_results()
    valid = results[~results["missing_data"]].copy()
    baseline = valid[(valid["distance"] == BASELINE_DISTANCE) & (valid["width"] == BASELINE_WIDTH)].copy()
    baseline["net_pnl_adj"] = baseline["credit"] - SLIPPAGE - baseline["payout_owed"]
    baseline = baseline.set_index("entry").sort_index()
    entries = baseline.index

    daily_forecast = build_weekly_forecasts(model="harx")  # long, ~2016 out-of-sample daily series
    pct_rank = _expanding_percentile_rank(daily_forecast)
    entry_pct_rank = pct_rank.reindex(pd.to_datetime(entries)).ffill()

    real_skip_mask = (entry_pct_rank >= threshold_percentile).to_numpy()
    real_skip_count = int(real_skip_mask.sum())

    def gated_series(skip_mask: np.ndarray) -> pd.Series:
        pnl = baseline["net_pnl_adj"].to_numpy().copy()
        pnl[skip_mask] = 0.0
        return pd.Series(pnl, index=baseline.index)

    real_gated = gated_series(real_skip_mask)
    always_trade = baseline["net_pnl_adj"]

    real_sortino = sortino_ratio(real_gated)
    always_sortino = sortino_ratio(always_trade)

    rng = np.random.default_rng(SEED)
    n = len(baseline)
    null_sortinos = np.empty(N_PERMUTATIONS)
    for i in range(N_PERMUTATIONS):
        random_mask = np.zeros(n, dtype=bool)
        skip_idx = rng.choice(n, size=real_skip_count, replace=False)
        random_mask[skip_idx] = True
        null_sortinos[i] = sortino_ratio(gated_series(random_mask))

    empirical_p = float((null_sortinos >= real_sortino).mean())

    return {
        "n_weeks": n,
        "threshold_percentile": threshold_percentile,
        "real_skip_count": real_skip_count,
        "mean_pnl_gated": real_gated.mean(),
        "mean_pnl_always_trade": always_trade.mean(),
        "sortino_gated": real_sortino,
        "sortino_always_trade": always_sortino,
        "mdd_gated": max_drawdown(real_gated),
        "mdd_always_trade": max_drawdown(always_trade),
        "cvar10_gated": cvar(real_gated),
        "cvar10_always_trade": cvar(always_trade),
        "null_sortino_mean": null_sortinos.mean(),
        "null_sortino_std": null_sortinos.std(),
        "empirical_p_one_sided": empirical_p,
        "n_permutations": N_PERMUTATIONS,
    }


if __name__ == "__main__":
    for thr in (0.85, 0.70):
        out = run(thr)
        print(f"=== Experiment 27: binary circuit-breaker, threshold={thr:.0%} expanding percentile ===\n")
        print(f"n = {out['n_weeks']}, real weeks skipped = {out['real_skip_count']} "
              f"({out['real_skip_count']/out['n_weeks']:.1%})\n")
        print(f"Mean P&L, gated: {out['mean_pnl_gated']:.4f}   always-trade: {out['mean_pnl_always_trade']:.4f}")
        print(f"Sortino, gated: {out['sortino_gated']:.4f}   always-trade: {out['sortino_always_trade']:.4f}")
        print(f"Max drawdown, gated: {out['mdd_gated']:.3f}   always-trade: {out['mdd_always_trade']:.3f}")
        print(f"CVaR(10%), gated: {out['cvar10_gated']:.4f}   always-trade: {out['cvar10_always_trade']:.4f}\n")
        print(f"Matched-size random-skip null ({out['n_permutations']} draws): "
              f"mean Sortino={out['null_sortino_mean']:.4f}, std={out['null_sortino_std']:.4f}")
        print(f"Empirical p-value, one-sided (null Sortino >= real gated Sortino): {out['empirical_p_one_sided']:.4f}")
        print()
