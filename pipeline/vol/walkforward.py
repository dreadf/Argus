"""
Expanding-window walk-forward validation with purge, for the volatility
forecasting track. A model is refit on an expanding training window and
scored only on the immediately-following out-of-sample block, repeated
across the whole series -- the discipline this repo has used since the
equity-direction track's Experiment 2b (which caught a single-split result
that did not survive multi-window validation).
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd


def expanding_walk_forward(
    n: int,
    min_train: int,
    test_block: int,
    purge: int = 1,
) -> list[tuple[range, range]]:
    """Yields (train_idx, test_idx) index-position ranges. `purge` positions
    are dropped from the END of the training window so a target that looks
    `purge` days forward (here, HAR's 1-day-ahead target needs purge=1,
    already baked into build_har_features' shift(1); purge exists for
    anything with a longer horizon reused against this same splitter)."""
    splits = []
    start = min_train
    while start + test_block <= n:
        train_idx = range(0, max(start - purge, 0))
        test_idx = range(start, start + test_block)
        splits.append((train_idx, test_idx))
        start += test_block
    return splits


def run_walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    fit_predict_fn: Callable[[pd.DataFrame, pd.Series, pd.DataFrame], pd.Series],
    min_train: int = 500,
    test_block: int = 63,
    purge: int = 1,
) -> pd.Series:
    """`fit_predict_fn(X_train, y_train, X_test) -> y_pred` -- kept generic
    so the same splitter drives HAR, qlikeHAR, and any ML model without
    duplicating the windowing logic per model (a caching trap this repo has
    hit before, e.g. pipeline/backtest and pipeline/audit's evidence_gate
    both used to reimplement the same cushion math independently)."""
    n = len(X)
    splits = expanding_walk_forward(n, min_train, test_block, purge)
    if not splits:
        raise ValueError(f"no walk-forward windows fit: n={n}, min_train={min_train}, test_block={test_block}")

    preds = []
    for train_idx, test_idx in splits:
        X_train, y_train = X.iloc[list(train_idx)], y.iloc[list(train_idx)]
        X_test = X.iloc[list(test_idx)]
        pred = fit_predict_fn(X_train, y_train, X_test)
        preds.append(pred)
    return pd.concat(preds).sort_index()
