"""
Experiment 30 -- re-verifies Experiments 7-10's null-signal conclusion
against split-adjusted data. `output/data/raw_*.csv` was found (2026-09-02,
PROGRESS.md) to be un-split-adjusted: every price-derived feature and the
5-day forward-return target were contaminated around NVDA/GOOGL/AMZN/AAPL's
real stock splits. `pipeline/extract.py` was fixed and all 40 symbols were
refetched, but `output/data/engineered_*.csv` (generated from the OLD
contaminated raw data) and every model trained on it were not re-run until
this file.

Reuses Experiment 8/9/10's exact methodology (pipeline/panel.py's feature
functions, pipeline/signals/ IC measurement) unchanged -- this is a
re-verification, not a new experiment design. The one addition is a fixed
XGBoost `random_state` (Experiment 8/9's original runs used none), needed
so this file's own numbers are reproducible; it does not change what's
being tested.

Run: python -m pipeline.model.rerun_after_split_fix (~10s, no network)
"""

from __future__ import annotations

from sklearn import metrics
from xgboost import XGBClassifier

from pipeline.config import MARKET_SYMBOL, SYMBOLS
from pipeline.panel import add_market_features, add_news_features, add_relative_target, build_panel_data, get_x_y, split_by_date
from pipeline.signals.eval import daily_ic, ic_summary
from pipeline.signals.signals import model_signal
from pipeline.transform import engineer_features

# Same exclusion list pooled_xgb_model.py uses -- see its comment for why
# raw market columns (*_mkt) are excluded (near-constant per date, collinear
# with the residual_momentum_* features derived from them).
_EXCLUDE = [
    "market_median_return", "relative_target", "symbol", "target_5d", "fwd_5d_return",
    "close", "high", "open", "low", "timestamp", "volume", "vwap", "SMA_10", "SMA_30",
    "daily_return_mkt", "momentum_5_mkt", "momentum_10_mkt", "momentum_20_mkt",
    "volatility_5_mkt", "volatility_10_mkt", "RSI_mkt",
]
_RANDOM_STATE = 42


def _train_and_measure(train_df, test_df, feature_columns: list[str], label: str) -> dict:
    x_train, y_train = get_x_y(train_df, feature_columns, "relative_target")
    x_test, y_test = get_x_y(test_df, feature_columns, "relative_target")

    model = XGBClassifier(n_estimators=100, max_depth=3, subsample=0.8, learning_rate=0.1, random_state=_RANDOM_STATE)
    model.fit(x_train, y_train)
    pred_prob = model.predict_proba(x_test)[:, 1]
    auc = metrics.roc_auc_score(y_test, pred_prob)

    scores = model_signal(test_df, model, feature_columns)
    fwd_returns = test_df.reset_index()[["timestamp", "symbol", "fwd_5d_return"]]
    summary = ic_summary(daily_ic(scores, fwd_returns))

    print(f"\n{label}: AUC={auc:.4f}, features={len(feature_columns)}")
    print(f"  mean_ic={summary['mean_ic']:+.4f}  t_stat_non_overlap={summary['t_stat_non_overlap']:+.3f}  n_eff={summary['n_eff_non_overlap']}")
    return {"auc": auc, **summary}


def run() -> dict:
    for s in SYMBOLS:
        engineer_features(s)  # re-reads the corrected output/data/raw_{s}.csv

    panel_no_news = add_relative_target(add_market_features(build_panel_data(SYMBOLS), MARKET_SYMBOL))
    panel_with_news = add_relative_target(add_news_features(add_market_features(build_panel_data(SYMBOLS), MARKET_SYMBOL)))

    train8, test8 = split_by_date(panel_no_news, 0.8)
    train9, test9 = split_by_date(panel_with_news, 0.8)

    features8 = [c for c in panel_no_news.columns if c not in _EXCLUDE]
    features9 = [c for c in panel_with_news.columns if c not in _EXCLUDE]

    result8 = _train_and_measure(train8, test8, features8, "Experiment 8 re-run (market features, no news), corrected data")
    result9 = _train_and_measure(train9, test9, features9, "Experiment 9 re-run (+ news_count), corrected data")
    return {"experiment_8": result8, "experiment_9": result9}


if __name__ == "__main__":
    results = run()

    for label, r in results.items():
        assert abs(r["t_stat_non_overlap"]) < 2.0, (
            f"{label}: |t_stat_non_overlap|={abs(r['t_stat_non_overlap']):.3f} >= 2.0 -- "
            "this would mean the split-adjustment fix RECOVERED a significant signal, "
            "which contradicts this file's own docstring claim and needs write-up before trusting it, not just an assert."
        )
    print("\nBoth re-run variants remain statistically indistinguishable from zero IC "
          "(|t| < 2.0) after the split-adjustment fix -- the project's null-signal "
          "conclusion is not an artifact of the data contamination.")
