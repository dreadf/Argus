"""
Experiment 16 (H2): does Patton-Sheppard signed semivariance (SHAR) beat
plain HAR-RV out-of-sample? Both fit by QLIKE (Experiment 14's established
winner), so this isolates the effect of the FEATURE split, not the loss
function -- a fair test of H2 specifically, not a re-test of H3.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.forecast_eval import diebold_mariano, mincer_zarnowitz_r2, mse_log, qlike
from pipeline.vol.har import HARModel, build_har_features, build_shar_features
from pipeline.vol.walkforward import run_walk_forward

MIN_TRAIN = 500
TEST_BLOCK = 63


def load_full_intraday(path: str = "output/data/vol_spy_intraday_full.csv") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df


def run() -> pd.DataFrame:
    full = load_full_intraday()
    log_rv = np.log(full["realized_vol_annualized_pct"])
    log_rv_pos = np.log(full["rv_pos_annualized_pct"].clip(lower=1e-6))
    log_rv_neg = np.log(full["rv_neg_annualized_pct"].clip(lower=1e-6))

    har_feats = build_har_features(log_rv)
    shar_feats = build_shar_features(log_rv, log_rv_pos, log_rv_neg)

    def fp_qlike(feats):
        def fn(X_train, y_train, X_test):
            return HARModel("qlike").fit(X_train, y_train).predict(X_test)
        return fn

    har_pred = run_walk_forward(har_feats, log_rv, fp_qlike(har_feats), MIN_TRAIN, TEST_BLOCK)
    shar_pred = run_walk_forward(shar_feats, log_rv, fp_qlike(shar_feats), MIN_TRAIN, TEST_BLOCK)

    common_idx = har_pred.index.intersection(shar_pred.index)
    realized_var = np.exp(2 * log_rv.loc[common_idx])

    rows = []
    loss_frames = {}
    for name, pred in [("har_rv_qlike", har_pred), ("shar_qlike", shar_pred)]:
        pred = pred.loc[common_idx]
        forecast_var = np.exp(2 * pred)
        q = qlike(realized_var.to_numpy(), forecast_var.to_numpy())
        m = mse_log(realized_var.to_numpy(), forecast_var.to_numpy())
        r2 = mincer_zarnowitz_r2(realized_var.to_numpy(), forecast_var.to_numpy())
        loss_frames[name] = pd.Series(q, index=common_idx)
        rows.append({"model": name, "n": len(common_idx), "mean_qlike": q.mean(),
                     "mean_mse_log": m.mean(), "mz_r2": r2})

    result = pd.DataFrame(rows).sort_values("mean_qlike")
    print(f"Out-of-sample window: {common_idx.min().date()} to {common_idx.max().date()}, n={len(common_idx)}")
    print(result.to_string(index=False))
    print()

    dm = diebold_mariano(loss_frames["shar_qlike"].to_numpy(), loss_frames["har_rv_qlike"].to_numpy())
    print(f"DM test, SHAR vs plain HAR-RV (both QLIKE-fit): mean diff={dm['mean_loss_diff']:.4f}, "
          f"t={dm['dm_stat']:.2f}, p={dm['p_value']:.4f}, better={dm['better']} "
          f"({'SHAR' if dm['better']=='A' else 'plain HAR-RV'})")

    atomic_to_csv(result, "output/data/vol_experiment16_shar_results.csv", index=False)
    print("\nSaved to output/data/vol_experiment16_shar_results.csv")
    return result


if __name__ == "__main__":
    run()
