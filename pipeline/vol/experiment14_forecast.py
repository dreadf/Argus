"""
Experiment 14 (H2 + H3 in .claude/plans/we-need-a-major-buzzing-catmull.md):
does a HAR-family model forecast SPY realized volatility better than a naive
baseline, and does fitting HAR by QLIKE instead of OLS help out-of-sample?

Walk-forward only -- every number here is genuinely out-of-sample, refit on
an expanding window and scored strictly on the following block, never on
data the model has seen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.forecast_eval import diebold_mariano, mincer_zarnowitz_r2, mse_log, model_confidence_set, qlike
from pipeline.vol.har import HARModel, build_har_features, ewma_forecast, naive_forecast
from pipeline.vol.walkforward import run_walk_forward

MIN_TRAIN = 500   # roughly 2 years of trading days before the first out-of-sample forecast
TEST_BLOCK = 63   # refit quarterly


def load_log_rv(path: str = "output/data/vol_spy_intraday_rv.csv") -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")["realized_vol_annualized_pct"]
    return np.log(df.sort_index())


def _har_fit_predict(loss: str):
    def fn(X_train, y_train, X_test):
        return HARModel(loss=loss).fit(X_train, y_train).predict(X_test)
    return fn


def run() -> pd.DataFrame:
    log_rv = load_log_rv()
    feats = build_har_features(log_rv)

    forecasts = {}
    forecasts["naive"] = naive_forecast(log_rv)
    forecasts["ewma"] = ewma_forecast(log_rv)
    forecasts["har_ols"] = run_walk_forward(feats, log_rv, _har_fit_predict("ols"), MIN_TRAIN, TEST_BLOCK)
    forecasts["har_qlike"] = run_walk_forward(feats, log_rv, _har_fit_predict("qlike"), MIN_TRAIN, TEST_BLOCK)

    # Align all forecasts to the walk-forward models' common out-of-sample
    # index (naive/ewma are defined everywhere, HAR only from MIN_TRAIN on --
    # comparing on a shorter common window than naive "sees" is deliberate,
    # a fair fight requires the exact same test dates for every model).
    common_idx = forecasts["har_ols"].index
    realized_log_var = 2 * log_rv.loc[common_idx]  # log(vol^2) = 2*log(vol)
    realized_var = np.exp(realized_log_var)

    rows = []
    loss_frames = {}
    for name, fc in forecasts.items():
        fc = fc.loc[common_idx]
        forecast_var = np.exp(2 * fc)
        q = qlike(realized_var.to_numpy(), forecast_var.to_numpy())
        m = mse_log(realized_var.to_numpy(), forecast_var.to_numpy())
        r2 = mincer_zarnowitz_r2(realized_var.to_numpy(), forecast_var.to_numpy())
        loss_frames[name] = pd.Series(q, index=common_idx)
        rows.append({
            "model": name,
            "n": len(common_idx),
            "mean_qlike": q.mean(),
            "mean_mse_log": m.mean(),
            "mz_r2": r2,
        })

    result = pd.DataFrame(rows).sort_values("mean_qlike")

    print(f"Out-of-sample window: {common_idx.min().date()} to {common_idx.max().date()}, n={len(common_idx)}")
    print(result.to_string(index=False))
    print()

    # Diebold-Mariano: does HAR-OLS beat naive? Does qlikeHAR beat HAR-OLS?
    dm_naive = diebold_mariano(loss_frames["har_ols"].to_numpy(), loss_frames["naive"].to_numpy())
    dm_qlike = diebold_mariano(loss_frames["har_qlike"].to_numpy(), loss_frames["har_ols"].to_numpy())
    print(f"DM test, HAR-OLS vs naive:      mean diff={dm_naive['mean_loss_diff']:.4f}, "
          f"t={dm_naive['dm_stat']:.2f}, p={dm_naive['p_value']:.4f}, better={dm_naive['better']}")
    print(f"DM test, qlikeHAR vs HAR-OLS:   mean diff={dm_qlike['mean_loss_diff']:.4f}, "
          f"t={dm_qlike['dm_stat']:.2f}, p={dm_qlike['p_value']:.4f}, better={dm_qlike['better']}")
    print()

    loss_matrix = pd.DataFrame(loss_frames)
    mcs = model_confidence_set(loss_matrix, alpha=0.10)
    print(f"90% Model Confidence Set: {mcs}")

    atomic_to_csv(result, "output/data/vol_experiment14_results.csv", index=False)
    print("\nSaved to output/data/vol_experiment14_results.csv")
    return result


if __name__ == "__main__":
    run()
