"""
Experiment 24: re-tests H4 on the daily-entry (overlapping) dataset built by
pipeline/vol/daily_entry_backtest.py -- ~640 observations instead of the
~125 non-overlapping weekly entries every prior H4 test (15/19/20/21/23)
used, over the SAME real Feb-2024-onward option history.

This is NOT a seventh look at the 125-week sample -- it is new data (daily
entries the original backtest deliberately never took), so it stands on its
own rather than adding to that multiple-testing count. But every
observation overlaps its neighbors by up to ~6 of 7 days, so a plain t-test
would badly understate the true standard error. Every test here uses
Diebold-Mariano's Newey-West HAC correction (pipeline/vol/forecast_eval.py,
already built and calibrated against known cases in Experiment 14) with
h=5 (the ~5-trading-day holding period), never a plain paired t-test.

Design: identical strategy to Experiment 20 (HAR-X forecaster, empirical/
skew-aware breach probability, $0.05/share slippage, fixed 3%/$5 baseline,
adaptive selection among the four ELIGIBLE_DISTANCES at BASELINE_WIDTH) --
only the entry frequency changes. Gated by the same randomization null used
in Experiments 21/23 (HAR-X forecast reshuffled across entry days, 2000x),
so a positive-looking result here still has to clear the same bar before
being trusted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.vol.forecast_eval import diebold_mariano
from pipeline.vol.overlay import BASELINE_DISTANCE, BASELINE_WIDTH, ELIGIBLE_DISTANCES, build_weekly_forecasts
from pipeline.vol.skew_breach import build_standardized_return_distribution, empirical_breach_prob

SLIPPAGE = 0.05
N_PERMUTATIONS = 2000
SEED = 20260901
HAC_H = 5  # ~5-trading-day holding period -> Newey-West max_lag = 4
DATA_PATH = "output/data/vol_daily_entry_backtest.csv"


def _breach_fn():
    std_returns = build_standardized_return_distribution()

    def fn(fvol, distance, horizon_days):
        return empirical_breach_prob(std_returns, fvol, distance, horizon_days)
    return fn


def _select_adaptive(valid: pd.DataFrame, entries: list, forecast_by_date: pd.Series, breach_fn) -> pd.DataFrame:
    rows = []
    fallback = 0
    for entry in entries:
        entry_ts = pd.Timestamp(entry)
        fvol = forecast_by_date.get(entry_ts)
        day = valid[valid["entry"] == entry]
        baseline_row = day[day["distance"] == BASELINE_DISTANCE]

        if pd.isna(fvol) or day.empty:
            fallback += 1
            chosen = baseline_row
        else:
            horizon_days = (day["expiry"] - day["entry"]).dt.days.iloc[0]
            edges = []
            for _, row in day.iterrows():
                implied_p = row["credit"] / row["width"]
                forecast_p = breach_fn(fvol, row["distance"], horizon_days)
                edges.append(implied_p - forecast_p)
            day = day.assign(edge=edges)
            best = day.loc[day["edge"].idxmax()]
            chosen = day[day.index == best.name]

        if chosen.empty:
            fallback += 1
            chosen = baseline_row
        if chosen.empty:
            continue
        rows.append(chosen.iloc[0])

    out = pd.DataFrame(rows)
    out = out.set_index(pd.to_datetime(out["entry"]))
    return out, fallback


def run() -> dict:
    df = pd.read_csv(DATA_PATH, parse_dates=["entry", "expiry"])
    valid = df[~df["missing_data"]].copy()
    valid = valid[valid["distance"].isin(ELIGIBLE_DISTANCES) & (valid["width"] == BASELINE_WIDTH)]
    valid["net_pnl_adj"] = valid["credit"] - SLIPPAGE - valid["payout_owed"]

    entries = sorted(valid["entry"].unique())
    print(f"Daily-entry dataset: n={len(entries)} entry days with at least one valid cell "
          f"(vs 125 in the weekly-only H4 tests), {valid['entry'].nunique()} unique days total")

    base_forecast = build_weekly_forecasts(model="harx")
    base_forecast_by_date = base_forecast.reindex(pd.to_datetime(entries)).ffill()
    breach_fn = _breach_fn()

    def score(forecast_by_date):
        adaptive, fallback = _select_adaptive(valid, entries, forecast_by_date, breach_fn)
        baseline = valid[valid["distance"] == BASELINE_DISTANCE].set_index(pd.to_datetime(valid[valid["distance"] == BASELINE_DISTANCE]["entry"]))
        common = adaptive.index.intersection(baseline.index)
        return adaptive.loc[common, "net_pnl_adj"].to_numpy(), baseline.loc[common, "net_pnl_adj"].to_numpy(), fallback

    real_adaptive, real_baseline, real_fallback = score(base_forecast_by_date)
    n = len(real_adaptive)
    mean_diff = real_adaptive.mean() - real_baseline.mean()
    dm = diebold_mariano(-real_adaptive, -real_baseline, h=HAC_H)  # sign-flipped: "loss", lower is better

    rng = np.random.default_rng(SEED)
    fc_values = base_forecast_by_date.to_numpy()
    null_diffs = np.empty(N_PERMUTATIONS)
    for i in range(N_PERMUTATIONS):
        shuffled = pd.Series(rng.permutation(fc_values), index=base_forecast_by_date.index)
        a, b, _ = score(shuffled)
        null_diffs[i] = a.mean() - b.mean()

    empirical_p = float((null_diffs >= mean_diff).mean())

    return {
        "n": n,
        "fallback_days": real_fallback,
        "mean_pnl_adaptive": real_adaptive.mean(),
        "mean_pnl_baseline": real_baseline.mean(),
        "mean_pnl_diff": mean_diff,
        "dm_stat": dm["dm_stat"],
        "dm_p_value": dm["p_value"],
        "null_mean": null_diffs.mean(),
        "null_std": null_diffs.std(),
        "empirical_p_one_sided": empirical_p,
        "n_permutations": N_PERMUTATIONS,
    }


if __name__ == "__main__":
    out = run()
    print("\n=== Experiment 24: H4 re-tested on daily-entry (overlapping) data ===\n")
    print(f"n = {out['n']} overlapping daily entries (fallback to baseline on {out['fallback_days']} days)")
    print(f"Mean P&L, adaptive: {out['mean_pnl_adaptive']:.4f}")
    print(f"Mean P&L, baseline: {out['mean_pnl_baseline']:.4f}")
    print(f"Mean diff: {out['mean_pnl_diff']:+.4f}")
    print(f"Diebold-Mariano (Newey-West HAC, h={HAC_H}): t={out['dm_stat']:.2f}, p={out['dm_p_value']:.4f}\n")
    print(f"Randomization null ({out['n_permutations']} shuffles): mean={out['null_mean']:.4f}, std={out['null_std']:.4f}")
    print(f"Empirical p-value, one-sided (null >= real): {out['empirical_p_one_sided']:.4f}")
