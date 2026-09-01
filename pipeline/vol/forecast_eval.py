"""
Forecast evaluation for the volatility track (Experiments 14+): QLIKE, MSE,
Mincer-Zarnowitz R-squared, and Diebold-Mariano significance testing.

QLIKE is the field-standard loss for variance forecasts (Patton 2011) and the
one this project cares about economically: it penalizes UNDER-forecasting
variance harder than over-forecasting, which matches the actual risk of
selling puts (a forecast that's too low leads to under-hedged/over-sized
positions; one that's too high just leaves money on the table).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def qlike(realized_var: np.ndarray, forecast_var: np.ndarray) -> np.ndarray:
    """Per-observation QLIKE loss (Patton 2011 canonical form):
    realized/forecast - ln(realized/forecast) - 1. Always >= 0, exactly 0
    at a perfect forecast, and asymmetric: under-forecasting (forecast <<
    realized) is penalized more severely than over-forecasting by the same
    ratio, because the loss is convex in realized/forecast."""
    realized_var = np.asarray(realized_var, dtype=float)
    forecast_var = np.asarray(forecast_var, dtype=float)
    ratio = realized_var / forecast_var
    return ratio - np.log(ratio) - 1.0


def mse_log(realized_var: np.ndarray, forecast_var: np.ndarray) -> np.ndarray:
    """Per-observation squared error on LOG variance -- the standard
    variance-stabilizing transform for a right-skewed quantity like
    volatility, so large-vol days don't dominate the loss by scale alone."""
    return (np.log(np.asarray(realized_var, dtype=float)) - np.log(np.asarray(forecast_var, dtype=float))) ** 2


def mincer_zarnowitz_r2(realized_var: np.ndarray, forecast_var: np.ndarray) -> float:
    """R-squared of regressing realized on forecast (Mincer-Zarnowitz 1969):
    how much of the actual variation the forecast explains, on top of just
    being unbiased. A forecast that's a constant scales to R^2=0."""
    realized_var = np.asarray(realized_var, dtype=float)
    forecast_var = np.asarray(forecast_var, dtype=float)
    slope, intercept, r, _, _ = stats.linregress(forecast_var, realized_var)
    return r ** 2


def diebold_mariano(loss_a: np.ndarray, loss_b: np.ndarray, h: int = 1) -> dict:
    """Diebold-Mariano test: is model A's loss series significantly
    different from model B's, using a Newey-West HAC standard error to
    account for the forecast-error autocorrelation that overlapping/
    persistent volatility series induce. `h` = forecast horizon in periods
    (used for the Newey-West lag truncation, h-1 per the standard DM
    convention). Negative t-stat means A has lower (better) loss than B.
    """
    d = np.asarray(loss_a, dtype=float) - np.asarray(loss_b, dtype=float)
    n = len(d)
    d_mean = d.mean()

    # Newey-West HAC variance of the mean, lag truncation h-1 (standard DM choice).
    max_lag = max(h - 1, 0)
    gamma_0 = np.var(d, ddof=0)
    var_d = gamma_0
    for lag in range(1, max_lag + 1):
        cov = np.cov(d[lag:], d[:-lag])[0, 1] if n > lag else 0.0
        weight = 1 - lag / (max_lag + 1)
        var_d += 2 * weight * cov
    se = np.sqrt(var_d / n)

    dm_stat = d_mean / se if se > 0 else 0.0
    p_value = 2 * (1 - stats.norm.cdf(abs(dm_stat)))
    return {"mean_loss_diff": d_mean, "dm_stat": dm_stat, "p_value": p_value, "n": n,
            "better": "A" if d_mean < 0 else "B"}


def model_confidence_set(loss_matrix: pd.DataFrame, alpha: float = 0.10, n_bootstrap: int = 1000, seed: int = 0) -> list[str]:
    """Simplified Hansen-Lunde-Nason (2011) Model Confidence Set via a
    stationary bootstrap on the loss differentials: iteratively eliminate
    the worst-performing model while a max-t elimination statistic exceeds
    its bootstrap-derived critical value, stopping when no model can be
    rejected at `alpha`. `loss_matrix`: rows = observations, columns =
    model names, values = per-observation loss (e.g. from qlike()).
    Returns the surviving model names -- the 90%-confidence "cannot rule
    out best" set the plan's protocol requires for comparing model variants
    without inflating false-positive risk from testing many at once."""
    rng = np.random.default_rng(seed)
    models = list(loss_matrix.columns)
    losses = loss_matrix.to_numpy()
    n = losses.shape[0]

    while len(models) > 1:
        idx = [loss_matrix.columns.get_loc(m) for m in models]
        sub = losses[:, idx]
        mean_losses = sub.mean(axis=0)
        # Relative loss of each model vs the average of the remaining set.
        d_ij = sub - sub.mean(axis=1, keepdims=True)
        d_i = d_ij.mean(axis=0)
        var_i = d_ij.var(axis=0, ddof=1)
        t_i = d_i / np.sqrt(np.maximum(var_i, 1e-12) / n)
        t_max_obs = t_i.max()
        worst = int(np.argmax(t_i))

        # Block bootstrap the null distribution of the max-t statistic.
        block = max(int(n ** (1 / 3)), 2)
        boot_max = np.empty(n_bootstrap)
        for b in range(n_bootstrap):
            starts = rng.integers(0, n - block, size=n // block + 1)
            sample_idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
            d_boot = d_ij[sample_idx] - d_ij[sample_idx].mean(axis=0)
            t_boot = d_boot.mean(axis=0) / np.sqrt(np.maximum(d_boot.var(axis=0, ddof=1), 1e-12) / n)
            boot_max[b] = t_boot.max()

        crit = np.quantile(boot_max, 1 - alpha)
        if t_max_obs <= crit:
            break
        models.pop(worst)

    return models
