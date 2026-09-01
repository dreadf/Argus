"""
Experiment 25: does HAR-J (Andersen, Bollerslev & Diebold 2007 -- HAR
augmented with the previous day's realized JUMP component) beat plain
HAR-RV? A different, genuine literature extension from SHAR (Experiment
16, killed): SHAR splits the daily term by the SIGN of returns; HAR-J adds
the SIZE of price jumps (RV minus bipower variation, already computed and
sitting unused in output/data/vol_spy_intraday_full.csv since Experiment
14's own data build).

This is a forecasting-quality exercise, not a re-opening of H4. Experiment
19 already showed a forecaster *significantly* better than plain HAR-RV
(HAR-X) made zero difference to whether the forecast converts to money --
H4 stayed closed regardless of forecast quality. This entry exists to round
out the forecasting story honestly (data was on disk, unused, and cited in
the "what other models" discussion), not because it could reopen H4.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.forecast_eval import diebold_mariano, mincer_zarnowitz_r2, model_confidence_set, qlike
from pipeline.vol.har import HARModel, build_har_features, build_har_j_features
from pipeline.vol.walkforward import run_walk_forward

MIN_TRAIN = 500
TEST_BLOCK = 63


def load_log_rv_and_jump(path: str = "output/data/vol_spy_intraday_full.csv"):
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    log_rv = np.log(df["realized_vol_annualized_pct"])
    jump = df["jump_annualized_pct"]
    return log_rv, jump


def _fit_predict(loss: str = "qlike"):
    def fn(X_train, y_train, X_test):
        return HARModel(loss=loss).fit(X_train, y_train).predict(X_test)
    return fn


def run() -> pd.DataFrame:
    log_rv, jump = load_log_rv_and_jump()

    har_feats = build_har_features(log_rv)
    harj_feats = build_har_j_features(log_rv, jump)

    har_pred = run_walk_forward(har_feats, log_rv, _fit_predict(), MIN_TRAIN, TEST_BLOCK)
    harj_pred = run_walk_forward(harj_feats, log_rv, _fit_predict(), MIN_TRAIN, TEST_BLOCK)

    common_idx = har_pred.index.intersection(harj_pred.index)
    realized_var = np.exp(2 * log_rv.loc[common_idx])

    rows, loss_frames = [], {}
    for name, pred in [("har_qlike", har_pred), ("harj_qlike", harj_pred)]:
        pred = pred.loc[common_idx]
        forecast_var = np.exp(2 * pred)
        q = qlike(realized_var.to_numpy(), forecast_var.to_numpy())
        loss_frames[name] = pd.Series(q, index=common_idx)
        rows.append({
            "model": name, "n": len(common_idx), "mean_qlike": q.mean(),
            "mz_r2": mincer_zarnowitz_r2(realized_var.to_numpy(), forecast_var.to_numpy()),
        })

    result = pd.DataFrame(rows).sort_values("mean_qlike")
    print(f"Out-of-sample window: {common_idx.min().date()} to {common_idx.max().date()}, n={len(common_idx)}\n")
    print(result.to_string(index=False))

    dm = diebold_mariano(loss_frames["harj_qlike"].to_numpy(), loss_frames["har_qlike"].to_numpy())
    winner = "HAR-J" if dm["better"] == "A" else "plain HAR-RV"
    print(f"\nDM: HAR-J vs plain HAR-RV (both QLIKE-fit): mean diff={dm['mean_loss_diff']:.4f}, "
          f"t={dm['dm_stat']:.2f}, p={dm['p_value']:.4f}, better={winner}")

    mcs = model_confidence_set(pd.DataFrame(loss_frames), alpha=0.10)
    print(f"90% Model Confidence Set: {mcs}")

    # Same check Experiment 18 ran on HAR-X's VIX coefficient: is the jump
    # coefficient consistently signed across refits, or unstable?
    coefs = []
    n = len(harj_feats)
    from pipeline.vol.walkforward import expanding_walk_forward
    for train_idx, _ in expanding_walk_forward(n, MIN_TRAIN, TEST_BLOCK, purge=1):
        X_train = harj_feats.iloc[list(train_idx)]
        y_train = log_rv.iloc[list(train_idx)]
        m = HARModel("qlike").fit(X_train, y_train)
        coefs.append(dict(zip(harj_feats.columns, m.coef_)))
    coef_df = pd.DataFrame(coefs)
    print("\nHAR-J's jump coefficient across walk-forward refits:")
    print(coef_df["har_j_jump"].describe())

    atomic_to_csv(result, "output/data/vol_experiment25_harj_results.csv", index=False)
    print("\nSaved to output/data/vol_experiment25_harj_results.csv")
    return result


if __name__ == "__main__":
    run()
