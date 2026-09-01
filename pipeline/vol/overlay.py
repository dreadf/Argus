"""
Experiment 15 (H4): does the Experiment 14 volatility forecast convert into
money by choosing WHICH (distance, width) cell to sell each week, rather
than trading the same fixed cell every week?

Design, per the plan (.claude/plans/we-need-a-major-buzzing-catmull.md):
the naive "only trade the richest 40% of weeks" design cuts n from 126 to
~50 and inflates every SE by ~1.58x -- close to unfalsifiable. Instead,
since spread_backtest.py already replayed all 24 (distance, width) cells
every week, the signal picks WHICH cell to sell, keeping n near 126 intact.
Skip-the-week is tested too, as the secondary variant.

The edge each week, for each candidate cell:
    edge = implied_breach_prob - forecast_breach_prob
where implied_breach_prob = credit / width (the market's price for the
short leg breaching, already in spread_backtest_results.csv, no Black-
Scholes needed) and forecast_breach_prob is this session's own walk-forward
HAR-QLIKE volatility forecast (Experiment 14) converted to a breach
probability via a normal approximation over the trade's real horizon. The
adaptive strategy sells the cell with the largest edge each week -- the
most literal implementation of "sell where the market is overcharging
relative to what the forecaster actually expects to happen."

Baseline is the best FIXED cell (3% distance, $5 width -- established in
Step 0 as the realistic-cost-robust choice, 1.55 SE at $0.05/share), not
the $1-width cell that Experiment 11's original table happened to lead
with and that Step 0 showed fails outright under cost. Comparing against
the cell that already fails would be a strawman.

Defect B mitigation (Step 0): missing option-price data is not missing at
random -- it clusters in volatile weeks, worst at deep-OTM distances.
Adaptive selection is restricted to distances with <=3.9% missing data
(1% through 4%), and a missing cell falls back to the fixed baseline
rather than being silently skipped.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from pipeline.backtest.evidence_gate import _cushion_for_cell
from pipeline.io_utils import coerce_win_column
from pipeline.vol.step0_recheck import load_corrected_results

BASELINE_DISTANCE = 0.03
BASELINE_WIDTH = 5
# Defect B: missing rate <=3.9% at these distances (1-4%); 5%/6% run 8-14%
# missing and cluster in exactly the volatile weeks an adaptive strategy
# would most want to select -- excluded from the adaptive candidate set.
ELIGIBLE_DISTANCES = (0.01, 0.02, 0.03, 0.04)
TRADING_DAYS_PER_YEAR = 252


def _forecast_breach_prob(forecast_vol_annualized_pct: float, distance: float, horizon_days: int) -> float:
    """Normal approximation: P(weekly log return <= -distance), using the
    forecaster's annualized volatility scaled to the trade's real horizon
    (3, 6, or 7 calendar days per Step 0's finding that not every week is a
    plain 7-day cycle -- horizon is read from the actual entry/expiry gap
    in the backtest data, not assumed constant)."""
    sigma_horizon = (forecast_vol_annualized_pct / 100) * np.sqrt(horizon_days / TRADING_DAYS_PER_YEAR)
    if sigma_horizon <= 0:
        return 0.0
    z = -np.log(1 - distance) / sigma_horizon
    return float(stats.norm.cdf(-z))


def build_weekly_forecasts(model: str = "har") -> pd.Series:
    """Friday-aligned walk-forward forecasts, reused rather than refit for
    this overlay -- same model(s), same out-of-sample discipline as their
    origin experiments. `model="har"`: Experiment 14's HAR-RV (QLIKE-fit).
    `model="harx"`: Experiment 18's HAR-X (HAR + log VIX, QLIKE-fit,
    Diebold-Mariano t=-3.22 p=0.0013 better than plain HAR-RV) -- re-testing
    H4 with the proven-better forecaster, per Experiment 18's own suggested
    next step, to check whether Experiment 15's null result was about the
    strategy or about forecast quality specifically."""
    from pipeline.vol.experiment14_forecast import load_log_rv
    from pipeline.vol.har import HARModel, build_har_features, build_har_x_features
    from pipeline.vol.walkforward import run_walk_forward

    log_rv = load_log_rv()
    if model == "har":
        feats = build_har_features(log_rv)
    elif model == "harx":
        from pipeline.vol.experiment18_harx import load_vix
        feats = build_har_x_features(log_rv, load_vix())
    else:
        raise ValueError(f"unknown model {model!r}")

    def fp(Xtr, ytr, Xte):
        return HARModel("qlike").fit(Xtr, ytr).predict(Xte)

    forecast_log_vol = run_walk_forward(feats, log_rv, fp, min_train=500, test_block=63)
    forecast_vol_pct = np.exp(forecast_log_vol)  # back from log to annualized vol %
    return forecast_vol_pct


def run_overlay(slippage_per_share: float, model: str = "har", breach_fn=None,
                 forecast_by_date: pd.Series | None = None, rng: np.random.Generator | None = None,
                 return_paired: bool = False):
    """`breach_fn(forecast_vol_pct, distance, horizon_days) -> probability`
    defaults to the normal approximation (`_forecast_breach_prob`); pass
    Experiment 20's empirical/skew-aware version to replace it without
    duplicating the rest of this function.

    `forecast_by_date`: pass a pre-built (or, for Experiment 21's
    randomization null, pre-SHUFFLED) date-indexed forecast series to skip
    rebuilding it from scratch every call -- `rng` shuffles its VALUES
    across the same dates when given, which severs any real timing
    relationship between the forecast and that week's outcome while
    leaving both marginal distributions (which forecast values occur, which
    weeks are traded) exactly as they were."""
    if breach_fn is None:
        breach_fn = _forecast_breach_prob

    results = load_corrected_results()
    valid = results[~results["missing_data"]].copy()

    entries = sorted(valid["entry"].unique())
    if forecast_by_date is None:
        forecast = build_weekly_forecasts(model=model)
        forecast_by_date = forecast.reindex(pd.to_datetime(entries)).ffill()  # last available forecast at/before entry
    if rng is not None:
        shuffled_values = rng.permutation(forecast_by_date.to_numpy())
        forecast_by_date = pd.Series(shuffled_values, index=forecast_by_date.index)

    adaptive_rows = []
    fallback_count = 0
    for entry in entries:
        entry_ts = pd.Timestamp(entry)
        fvol = forecast_by_date.get(entry_ts)
        week = valid[valid["entry"] == entry]
        baseline_row = week[(week["distance"] == BASELINE_DISTANCE) & (week["width"] == BASELINE_WIDTH)]

        # Width is held FIXED at the established cost-robust choice
        # (BASELINE_WIDTH). Two earlier attempts at also letting the signal
        # choose width both failed for the same underlying reason: a raw
        # probability edge is not comparable across different widths (a 2pp
        # edge means far less in dollar terms on a $1-wide cell than a
        # $10-wide one, so raw-probability comparison collapsed onto $1
        # every time), and multiplying by width to "dollar-weight" it just
        # inverted the bias (collapsed onto $10 every time, since expected
        # value scales linearly with width while risk does too -- an
        # unconstrained size-maximization problem, not a genuine read of
        # the forecast's information). Holding width fixed sidesteps this
        # entirely: at the SAME width, probability edges represent the SAME
        # dollar stakes, so comparing them across distances is valid. This
        # also matches the plan's original, narrower design intent -- the
        # signal chooses distance, not width.
        eligible = week[(week["distance"].isin(ELIGIBLE_DISTANCES)) & (week["width"] == BASELINE_WIDTH)]
        if pd.isna(fvol) or eligible.empty:
            fallback_count += 1
            chosen = baseline_row
        else:
            horizon_days = (eligible["expiry"] - eligible["entry"]).dt.days.iloc[0]
            edges = []
            for _, row in eligible.iterrows():
                implied_p = row["credit"] / row["width"]
                forecast_p = breach_fn(fvol, row["distance"], horizon_days)
                edges.append(implied_p - forecast_p)
            eligible = eligible.assign(edge=edges)
            best = eligible.loc[eligible["edge"].idxmax()]
            chosen = eligible[eligible.index == best.name]

        if chosen.empty:
            fallback_count += 1
            chosen = baseline_row
        adaptive_rows.append(chosen.iloc[0])

    adaptive = pd.DataFrame(adaptive_rows).reset_index(drop=True)
    adaptive["net_pnl_adj"] = adaptive["credit"] - slippage_per_share - adaptive["payout_owed"]

    baseline = valid[(valid["distance"] == BASELINE_DISTANCE) & (valid["width"] == BASELINE_WIDTH)].copy()
    baseline["net_pnl_adj"] = baseline["credit"] - slippage_per_share - baseline["payout_owed"]
    baseline = baseline.set_index("entry").reindex(pd.to_datetime(entries))

    adaptive = adaptive.set_index(pd.to_datetime(entries))
    paired = pd.DataFrame({
        "adaptive": adaptive["net_pnl_adj"],
        "baseline": baseline["net_pnl_adj"],
    }).dropna()
    diff = paired["adaptive"] - paired["baseline"]

    t_stat, p_value = stats.ttest_1samp(diff, 0.0)
    baseline_cushion = _cushion_for_cell(
        valid[(valid["distance"] == BASELINE_DISTANCE) & (valid["width"] == BASELINE_WIDTH)],
        slippage_per_share,
    )

    out = {
        "slippage": slippage_per_share,
        "n_weeks": len(paired),
        "fallback_weeks": fallback_count,
        "mean_pnl_adaptive": paired["adaptive"].mean(),
        "mean_pnl_baseline": paired["baseline"].mean(),
        "mean_pnl_diff": diff.mean(),
        "paired_t_stat": t_stat,
        "paired_p_value": p_value,
        "baseline_cushion_se": baseline_cushion["cushion_se"] if baseline_cushion else None,
        "adaptive_distance_dist": adaptive["distance"].value_counts().to_dict(),
        "adaptive_width_dist": adaptive["width"].value_counts().to_dict(),
    }
    if return_paired:
        return out, paired
    return out


if __name__ == "__main__":
    from pipeline.io_utils import atomic_to_csv

    rows = [run_overlay(slip) for slip in (0.0, 0.02, 0.05)]
    result = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print(result[["slippage", "n_weeks", "fallback_weeks", "mean_pnl_adaptive",
                   "mean_pnl_baseline", "mean_pnl_diff", "paired_t_stat", "paired_p_value",
                   "baseline_cushion_se"]].to_string(index=False))
    print()
    for row in rows:
        print(f"slippage=${row['slippage']:.2f}  adaptive distance picks: {row['adaptive_distance_dist']}")
        print(f"slippage=${row['slippage']:.2f}  adaptive width picks:    {row['adaptive_width_dist']}")

    atomic_to_csv(result, "output/data/vol_experiment15_overlay.csv", index=False)
    print("\nSaved to output/data/vol_experiment15_overlay.csv")
