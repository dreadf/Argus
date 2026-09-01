"""
Experiment 22: is the square-root-of-time scaling used by every H4 test
(Experiments 15, 19, 20, 21) a real, correctable defect?

Every H4 test forecast ONE day of volatility with HAR/HAR-X and then scaled
it to the trade's ~5-trading-day horizon by sqrt(h/252). In annualized
terms that is equivalent to assuming annualized volatility is CONSTANT
across the week. Volatility is mean-reverting, so that assumption is
biased, and biased in a direction that depends on the current vol level.

Measured directly on the real RV series before building anything (no model
involved, just the scaling assumption): the ratio of assumed to actual
5-day average variance runs 0.611 / 0.779 / 1.014 / 1.027 / 1.374 across
current-vol quintiles -- perfectly monotonic, Spearman rho=0.448
(p=2.6e-126). sqrt-scaling understates risk by ~39% in the calmest weeks
and overstates it by ~37% in the wildest ones.

This experiment tests the FIX on the large sample, spending none of the
125-week option sample (which is exhausted for multiple-testing purposes
after Experiments 15/19/20/21):

    Does a HAR-X trained DIRECTLY on the 5-day-average variance target beat
    a 1-day HAR-X scaled by sqrt-of-time, at predicting actual 5-day
    average realized variance?

Multi-horizon HAR targets are Corsi's own construction (2009 uses 1-day,
1-week and 2-week horizons), not something invented here.

Both models see identical features and identical walk-forward windows;
only the training target differs, isolating the horizon effect alone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.experiment18_harx import load_log_rv, load_vix
from pipeline.vol.forecast_eval import diebold_mariano, mincer_zarnowitz_r2, model_confidence_set, qlike
from pipeline.vol.har import HARModel, build_har_features, build_har_x_features
from pipeline.vol.walkforward import run_walk_forward

MIN_TRAIN = 500
TEST_BLOCK = 63
HORIZON = 5   # trading days -- the real holding period of the weekly spread
# The 5-day-ahead target at training row t extends to t+4, so the last 5
# training rows overlap the test block. purge=5 removes exactly that overlap.
PURGE = HORIZON


def build_horizon_target(log_rv: pd.Series, horizon: int = HORIZON) -> pd.Series:
    """log of the annualized volatility implied by the AVERAGE variance over
    days t..t+horizon-1 -- i.e. what the trade is actually exposed to over
    its life, rather than day t alone. Same log-annualized-vol scale as the
    1-day target, so QLIKE numbers are directly comparable and the same
    HARModel/exp(2*pred) conventions carry over unchanged."""
    var = np.exp(2 * log_rv)                                   # annualized variance
    fwd_avg_var = var[::-1].rolling(horizon).mean()[::-1]      # mean of var over t..t+horizon-1
    return np.log(np.sqrt(fwd_avg_var))


def _fit_predict(loss: str = "qlike"):
    def fn(X_train, y_train, X_test):
        return HARModel(loss=loss).fit(X_train, y_train).predict(X_test)
    return fn


def run() -> pd.DataFrame:
    log_rv = load_log_rv()
    vix = load_vix()

    har_feats = build_har_features(log_rv)
    harx_feats = build_har_x_features(log_rv, vix)
    y_1day = log_rv
    y_5day = build_horizon_target(log_rv, HORIZON)

    # "scaled" models train on the 1-DAY target -- exactly what H4 used --
    # and their prediction is then USED as the 5-day forecast, which is what
    # sqrt-of-time scaling amounts to on the annualized scale.
    preds = {
        "harx_scaled_1day": run_walk_forward(harx_feats, y_1day, _fit_predict(), MIN_TRAIN, TEST_BLOCK, PURGE),
        "harx_direct_5day": run_walk_forward(harx_feats, y_5day, _fit_predict(), MIN_TRAIN, TEST_BLOCK, PURGE),
        "har_scaled_1day": run_walk_forward(har_feats, y_1day, _fit_predict(), MIN_TRAIN, TEST_BLOCK, PURGE),
        "har_direct_5day": run_walk_forward(har_feats, y_5day, _fit_predict(), MIN_TRAIN, TEST_BLOCK, PURGE),
    }

    common = None
    for p in preds.values():
        common = p.index if common is None else common.intersection(p.index)
    common = common.intersection(y_5day.dropna().index)

    # Everything is scored against the SAME thing: actual 5-day average
    # realized variance, the quantity the trade is genuinely exposed to.
    realized_var_5d = np.exp(2 * y_5day.loc[common]).to_numpy()

    rows, loss_frames = [], {}
    for name, pred in preds.items():
        forecast_var = np.exp(2 * pred.loc[common]).to_numpy()
        q = qlike(realized_var_5d, forecast_var)
        loss_frames[name] = pd.Series(q, index=common)
        rows.append({
            "model": name,
            "n": len(common),
            "mean_qlike": q.mean(),
            "mz_r2": mincer_zarnowitz_r2(realized_var_5d, forecast_var),
            "bias_ratio": forecast_var.mean() / realized_var_5d.mean(),
        })

    result = pd.DataFrame(rows).sort_values("mean_qlike")
    print(f"Target: actual {HORIZON}-day AVERAGE realized variance (what the weekly spread is exposed to)")
    print(f"Out-of-sample window: {common.min().date()} to {common.max().date()}, n={len(common)}\n")
    print(result.to_string(index=False))

    print(f"\nDiebold-Mariano (Newey-West, h={HORIZON} for the overlapping {HORIZON}-day targets):")
    for direct, scaled in [("harx_direct_5day", "harx_scaled_1day"), ("har_direct_5day", "har_scaled_1day")]:
        dm = diebold_mariano(loss_frames[direct].to_numpy(), loss_frames[scaled].to_numpy(), h=HORIZON)
        winner = direct if dm["better"] == "A" else scaled
        print(f"  {direct} vs {scaled}: mean diff={dm['mean_loss_diff']:+.4f}, "
              f"t={dm['dm_stat']:.2f}, p={dm['p_value']:.4f}, better={winner}")

    mcs = model_confidence_set(pd.DataFrame(loss_frames), alpha=0.10)
    print(f"\n90% Model Confidence Set: {mcs}")

    # Does the direct target actually FIX the level-dependent bias the
    # diagnostic found, or just lower the average loss? Checked explicitly.
    print("\nLevel-dependent bias check (forecast variance / actual 5-day variance, by current-vol quintile):")
    current_vol = np.exp(log_rv.loc[common])
    quintile = pd.qcut(current_vol, 5, labels=["Q1 low", "Q2", "Q3", "Q4", "Q5 high"])
    for name in ["harx_scaled_1day", "harx_direct_5day"]:
        ratios = pd.Series(np.exp(2 * preds[name].loc[common]).to_numpy() / realized_var_5d, index=common)
        by_q = ratios.groupby(quintile, observed=True).median()
        spread = by_q.iloc[-1] - by_q.iloc[0]
        print(f"  {name:<18} " + "  ".join(f"{k}={v:.3f}" for k, v in by_q.items()) +
              f"   | Q5-Q1 spread={spread:+.3f}")

    atomic_to_csv(result, "output/data/vol_experiment22_horizon_results.csv", index=False)
    print("\nSaved to output/data/vol_experiment22_horizon_results.csv")
    return result


if __name__ == "__main__":
    run()
