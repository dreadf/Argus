"""
Experiment 17 (H5): does XGBoost beat HAR-RV, and does it matter whether
it's given HAR components alone versus genuinely exogenous information
(market-wide dispersion across 40 stocks, news volume) HAR structurally
cannot see?

Pre-registered expectation, from the literature ("HARd to Beat", arXiv
2406.08041; the Financial Innovation review): ML should NOT beat HAR on
HAR's own inputs, and should only have a chance once given information
outside HAR's information set. Confirming the null half of this is a real
result, not a failure to find something.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from pipeline.io_utils import atomic_to_csv
from pipeline.vol.exogenous import build_market_dispersion, build_news_count
from pipeline.vol.forecast_eval import diebold_mariano, mincer_zarnowitz_r2, mse_log, model_confidence_set, qlike
from pipeline.vol.har import HARModel, build_har_features
from pipeline.vol.walkforward import run_walk_forward

TEST_BLOCK = 63
# The 40-stock dispersion feature only exists from 2020-02-13 (the panel
# data's own start date) -- 910 of log_rv's 2555 rows precede it. A
# MIN_TRAIN of 500 (used for the HAR-only comparisons in Experiments 14/16)
# would put the FIRST few walk-forward training windows entirely before
# dispersion/news exist, so after dropna() the exogenous model would be fit
# on an EMPTY training set. Caught directly: XGBoost's own warning ("Empty
# dataset at worker") and a nonsensical mean_qlike of 62 (vs ~0.19 for
# every other model) on the first attempt. Fixed by raising MIN_TRAIN so
# the first training window already contains real exogenous data.
MIN_TRAIN = 950


def load_log_rv(path: str = "output/data/vol_spy_intraday_rv.csv") -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date")["realized_vol_annualized_pct"]
    return np.log(df.sort_index())


def build_exogenous_features(log_rv: pd.Series) -> pd.DataFrame:
    """HAR components plus dispersion/news, all as of t-1 (never t, which
    the target needs to predict) -- same shift discipline as build_har_features."""
    har = build_har_features(log_rv)
    dispersion = build_market_dispersion().shift(1)
    news = build_news_count().shift(1)
    exo = pd.DataFrame({"dispersion": dispersion, "news_count": news})
    exo = exo.reindex(log_rv.index)
    return har.join(exo)


def _xgb_fit_predict(X_train, y_train, X_test):
    model = XGBRegressor(n_estimators=100, max_depth=3, subsample=0.8, learning_rate=0.1, reg_lambda=1.0)
    valid = X_train.join(y_train.rename("y")).dropna()
    model.fit(valid.drop(columns="y"), valid["y"])
    return pd.Series(model.predict(X_test), index=X_test.index)


def _har_qlike_fit_predict(X_train, y_train, X_test):
    return HARModel("qlike").fit(X_train, y_train).predict(X_test)


def run() -> pd.DataFrame:
    log_rv = load_log_rv()
    har_feats = build_har_features(log_rv)
    exo_feats = build_exogenous_features(log_rv)

    forecasts = {}
    forecasts["har_qlike"] = run_walk_forward(har_feats, log_rv, _har_qlike_fit_predict, MIN_TRAIN, TEST_BLOCK)
    forecasts["xgb_har_only"] = run_walk_forward(har_feats, log_rv, _xgb_fit_predict, MIN_TRAIN, TEST_BLOCK)
    forecasts["xgb_exogenous"] = run_walk_forward(exo_feats, log_rv, _xgb_fit_predict, MIN_TRAIN, TEST_BLOCK)

    common_idx = forecasts["xgb_exogenous"].index  # shortest window (exogenous data availability), the fair common test set
    for k in forecasts:
        forecasts[k] = forecasts[k].loc[common_idx]
    realized_var = np.exp(2 * log_rv.loc[common_idx])

    rows = []
    loss_frames = {}
    for name, fc in forecasts.items():
        forecast_var = np.exp(2 * fc)
        q = qlike(realized_var.to_numpy(), forecast_var.to_numpy())
        m = mse_log(realized_var.to_numpy(), forecast_var.to_numpy())
        r2 = mincer_zarnowitz_r2(realized_var.to_numpy(), forecast_var.to_numpy())
        loss_frames[name] = pd.Series(q, index=common_idx)
        rows.append({"model": name, "n": len(common_idx), "mean_qlike": q.mean(),
                     "mean_mse_log": m.mean(), "mz_r2": r2})

    result = pd.DataFrame(rows).sort_values("mean_qlike")
    print(f"Common out-of-sample window: {common_idx.min().date()} to {common_idx.max().date()}, n={len(common_idx)}")
    print(result.to_string(index=False))
    print()

    dm1 = diebold_mariano(loss_frames["xgb_har_only"].to_numpy(), loss_frames["har_qlike"].to_numpy())
    print(f"DM: XGB(HAR-only) vs HAR-QLIKE:   diff={dm1['mean_loss_diff']:.4f}, t={dm1['dm_stat']:.2f}, "
          f"p={dm1['p_value']:.4f}, better={'XGB' if dm1['better']=='A' else 'HAR'}")
    dm2 = diebold_mariano(loss_frames["xgb_exogenous"].to_numpy(), loss_frames["har_qlike"].to_numpy())
    print(f"DM: XGB(exogenous) vs HAR-QLIKE:  diff={dm2['mean_loss_diff']:.4f}, t={dm2['dm_stat']:.2f}, "
          f"p={dm2['p_value']:.4f}, better={'XGB' if dm2['better']=='A' else 'HAR'}")
    dm3 = diebold_mariano(loss_frames["xgb_exogenous"].to_numpy(), loss_frames["xgb_har_only"].to_numpy())
    print(f"DM: XGB(exogenous) vs XGB(HAR-only): diff={dm3['mean_loss_diff']:.4f}, t={dm3['dm_stat']:.2f}, "
          f"p={dm3['p_value']:.4f}, better={'exogenous' if dm3['better']=='A' else 'HAR-only'}")
    print()

    loss_matrix = pd.DataFrame(loss_frames)
    mcs = model_confidence_set(loss_matrix, alpha=0.10)
    print(f"90% Model Confidence Set: {mcs}")

    atomic_to_csv(result, "output/data/vol_experiment17_ml_results.csv", index=False)
    print("\nSaved to output/data/vol_experiment17_ml_results.csv")
    return result


if __name__ == "__main__":
    run()
