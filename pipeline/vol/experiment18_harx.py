"""
Experiment 18: does HAR-X (plain HAR plus log(VIX) as an exogenous term)
beat plain HAR-RV, both QLIKE-fit? Literature-confirmed extension
(Kambouroudis 2021 and others) never tested in this project before this
entry -- surfaced directly from researching why VIX outperforms GARCH as a
standalone predictor, which led to the finding that the best-performing
approach in the literature is neither alone, but HAR augmented with VIX.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.forecast_eval import diebold_mariano, mincer_zarnowitz_r2, mse_log, model_confidence_set, qlike
from pipeline.vol.har import HARModel, build_har_features, build_har_x_features
from pipeline.vol.walkforward import run_walk_forward

MIN_TRAIN = 500
TEST_BLOCK = 63


def load_log_rv(path: str = "output/data/vol_spy_intraday_rv.csv") -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")["realized_vol_annualized_pct"]
    return np.log(df.sort_index())


def load_vix(path: str = "output/data/vix.csv") -> pd.Series:
    """Reuses the peer session's CBOE VIX cache directly -- same series
    already cross-checked in Experiment 13, no reason to re-fetch."""
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")["close"]
    return df.sort_index()


def _fit_predict(loss: str):
    def fn(X_train, y_train, X_test):
        return HARModel(loss=loss).fit(X_train, y_train).predict(X_test)
    return fn


def run() -> pd.DataFrame:
    log_rv = load_log_rv()
    vix = load_vix()

    har_feats = build_har_features(log_rv)
    harx_feats = build_har_x_features(log_rv, vix)

    har_pred = run_walk_forward(har_feats, log_rv, _fit_predict("qlike"), MIN_TRAIN, TEST_BLOCK)
    harx_pred = run_walk_forward(harx_feats, log_rv, _fit_predict("qlike"), MIN_TRAIN, TEST_BLOCK)

    common_idx = har_pred.index.intersection(harx_pred.index)
    realized_var = np.exp(2 * log_rv.loc[common_idx])

    rows = []
    loss_frames = {}
    for name, pred in [("har_qlike", har_pred), ("harx_qlike", harx_pred)]:
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

    dm = diebold_mariano(loss_frames["harx_qlike"].to_numpy(), loss_frames["har_qlike"].to_numpy())
    print(f"DM: HAR-X vs plain HAR-RV (both QLIKE-fit): mean diff={dm['mean_loss_diff']:.4f}, "
          f"t={dm['dm_stat']:.2f}, p={dm['p_value']:.4f}, better={'HAR-X' if dm['better']=='A' else 'plain HAR-RV'}")

    loss_matrix = pd.DataFrame(loss_frames)
    mcs = model_confidence_set(loss_matrix, alpha=0.10)
    print(f"90% Model Confidence Set: {mcs}")

    # Also inspect the fitted VIX coefficient across walk-forward windows --
    # is it consistently positive (higher VIX -> higher forecast, the
    # expected sign) and reasonably stable, or unstable/sign-flipping
    # (which would suggest overfitting rather than genuine information)?
    coefs = []
    n = len(harx_feats)
    from pipeline.vol.walkforward import expanding_walk_forward
    for train_idx, _ in expanding_walk_forward(n, MIN_TRAIN, TEST_BLOCK, purge=1):
        X_train = harx_feats.iloc[list(train_idx)]
        y_train = log_rv.iloc[list(train_idx)]
        m = HARModel("qlike").fit(X_train, y_train)
        coefs.append(dict(zip(harx_feats.columns, m.coef_)))
    coef_df = pd.DataFrame(coefs)
    print("\nHAR-X's VIX coefficient across walk-forward refits (expect consistently positive if genuine):")
    print(coef_df["har_x_vix"].describe())

    atomic_to_csv(result, "output/data/vol_experiment18_harx_results.csv", index=False)
    print("\nSaved to output/data/vol_experiment18_harx_results.csv")
    return result


if __name__ == "__main__":
    run()
