"""
The Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014, "The Deflated
Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and
Non-Normality", Journal of Portfolio Management -- see SOURCES.md).

WHY THIS EXISTS: trying N strategy variants and reporting the best one's
Sharpe ratio inflates that Sharpe mechanically, even with zero real skill --
the maximum of N draws from a null distribution is expected to be higher
than any single draw, purely from selection. The DSR corrects for exactly
this by asking: is the observed Sharpe significantly better than the BEST
Sharpe you'd expect from N independent trials with no real edge? It also
corrects for non-normal (skewed, fat-tailed) returns, which a plain Sharpe
ignores and which weekly options P&L is not exempt from.

Computing this honestly requires N to be a real count of everything tried
against this data, not a flattering guess -- see trial_count.py. This
project can state N truthfully because every attempt is numbered in
EXPERIMENT.md; that is the entire reason this measurement is possible here
and not just theoretically nice.

THE FORMULA (non-annualized, per-period quantities throughout):
  SR_hat      = sample Sharpe ratio of the observed returns
  T           = number of return observations
  gamma3      = sample skewness of returns
  gamma4      = sample kurtosis (Pearson's, not excess) of returns
  sigma_SR    = sqrt((1 - gamma3*SR_hat + (gamma4-1)/4 * SR_hat^2) / (T-1))
                -- the standard error of the Sharpe estimator under
                non-normal returns (Mertens 2002 / Lo 2002)
  SR_0        = the Sharpe expected from the BEST of N independent
                zero-skill trials:
                SR_0 = sigma_trials * [ (1-gamma)*Z^-1(1 - 1/N)
                                         + gamma*Z^-1(1 - 1/(N*e)) ]
                where gamma = Euler-Mascheroni constant (~0.5772),
                Z^-1 is the inverse standard normal CDF, and sigma_trials
                is the cross-trial standard deviation of Sharpe ratios --
                approximated here as sigma_SR itself (the standard,
                practical simplification: assume the untested N-1 trials
                would have had the same estimation variance as the one
                actually measured, since their true variance is
                unobservable by definition).
  DSR         = Phi( (SR_hat - SR_0) / sigma_SR )
                -- the probability the true Sharpe exceeds zero, after
                the multiple-testing and non-normality corrections. NOT
                the same units as SR_hat: DSR is a probability in [0, 1],
                not a Sharpe ratio itself, despite the name.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

EULER_MASCHERONI = 0.5772156649015329


def _skew_kurtosis(returns: pd.Series) -> tuple[float, float]:
    """Sample skewness (gamma3) and Pearson kurtosis (gamma4, NOT excess --
    a normal distribution has gamma4=3, not 0). scipy's default `fisher=True`
    returns excess kurtosis, so it's explicitly disabled here; getting this
    wrong would silently shift every sigma_SR computed downstream by a
    constant 3/4 * SR_hat^2 term."""
    gamma3 = float(stats.skew(returns, bias=False))
    gamma4 = float(stats.kurtosis(returns, fisher=False, bias=False))
    return gamma3, gamma4


def sharpe_se(sr_hat: float, returns: pd.Series) -> float:
    """sigma_SR: the standard error of the Sharpe ratio estimator,
    correcting for skew and kurtosis (Mertens 2002). Falls back to the
    normal-returns formula sqrt((1+SR^2/2)/T) only in the T<=1 degenerate
    case where sample skew/kurtosis are undefined."""
    t = len(returns)
    if t <= 1:
        return float("inf")
    gamma3, gamma4 = _skew_kurtosis(returns)
    variance = (1 - gamma3 * sr_hat + ((gamma4 - 1) / 4) * sr_hat**2) / (t - 1)
    return math.sqrt(max(variance, 0.0))


def expected_max_sharpe_under_null(sigma_trials: float, n_trials: int) -> float:
    """SR_0: the Sharpe ratio expected from the BEST of `n_trials`
    independent, zero-true-skill strategies, each with Sharpe-estimation
    variance `sigma_trials`. This is what makes the DSR a multiple-testing
    correction rather than a plain significance test -- the more trials,
    the higher this bar climbs, purely from selection.

    n_trials=1 is the degenerate no-multiple-testing case and must return
    exactly 0.0: `Z^-1(1 - 1/1) = Z^-1(0) = -inf` is undefined, so it's
    special-cased rather than left to blow up."""
    if n_trials <= 1:
        return 0.0
    z_a = stats.norm.ppf(1 - 1 / n_trials)
    z_b = stats.norm.ppf(1 - 1 / (n_trials * math.e))
    return sigma_trials * ((1 - EULER_MASCHERONI) * z_a + EULER_MASCHERONI * z_b)


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int, risk_free_per_period: float = 0.0) -> dict:
    """Returns a dict with every intermediate quantity, not just the final
    number -- so a reader (or a test) can check the derivation, not just
    trust the output. `returns` must be per-period (e.g. weekly), NOT
    annualized; annualize only the reported sr_hat/sr_0 for human framing
    if needed, never the inputs to this function.

    n_trials=1 reproduces the plain (non-deflated) significance test:
    SR_0=0.0 by construction above, so DSR = Phi(SR_hat / sigma_SR) exactly."""
    if len(returns) < 2:
        raise ValueError(f"need at least 2 return observations, got {len(returns)}")
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1, got {n_trials}")

    excess = returns - risk_free_per_period
    sr_hat = float(excess.mean() / excess.std(ddof=1)) if excess.std(ddof=1) != 0 else 0.0
    sigma_sr = sharpe_se(sr_hat, excess)
    sr_0 = expected_max_sharpe_under_null(sigma_sr, n_trials)
    dsr = float(stats.norm.cdf((sr_hat - sr_0) / sigma_sr)) if sigma_sr > 0 else (1.0 if sr_hat > sr_0 else 0.0)

    return {
        "n_observations": len(returns),
        "n_trials": n_trials,
        "sr_hat": sr_hat,
        "sigma_sr": sigma_sr,
        "sr_0_expected_max_under_null": sr_0,
        "dsr": dsr,
    }


def min_track_record_length(returns: pd.Series, risk_free_per_period: float = 0.0,
                             sr_benchmark: float = 0.0, confidence: float = 0.95) -> float:
    """Minimum Track Record Length (Bailey & Lopez de Prado 2012, cited in
    the DSR paper -- see SOURCES.md): how many periods of data, AT THE
    OBSERVED skew/kurtosis/Sharpe, would be needed to conclude at the given
    confidence that the true Sharpe exceeds `sr_benchmark` (0.0 by default:
    "is the edge real at all"). Derived by inverting the Probabilistic
    Sharpe Ratio (PSR = confidence) for T instead of evaluating it at the
    observed T:

        MinTRL = 1 + (1 - gamma3*SR + (gamma4-1)/4*SR^2) * (Z^-1(confidence)/SR)^2

    Returns periods (e.g. weeks if `returns` is weekly) -- divide by 52 (or
    the relevant periods-per-year) for years, same annualize-for-humans-only
    convention as the rest of this module.

    Returns float('inf') if sr_hat <= sr_benchmark: no finite amount of
    data at that skew/kurtosis would ever clear the bar, which is a real,
    reportable answer, not an error."""
    if len(returns) < 2:
        raise ValueError(f"need at least 2 return observations, got {len(returns)}")
    if not (0 < confidence < 1):
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    excess = returns - risk_free_per_period
    sr_hat = float(excess.mean() / excess.std(ddof=1)) if excess.std(ddof=1) != 0 else 0.0
    if sr_hat <= sr_benchmark:
        return float("inf")

    gamma3, gamma4 = _skew_kurtosis(excess)
    z = stats.norm.ppf(confidence)
    non_normality_term = 1 - gamma3 * sr_hat + ((gamma4 - 1) / 4) * sr_hat**2
    return 1 + non_normality_term * (z / (sr_hat - sr_benchmark)) ** 2


def deflated_sharpe_curve(returns: pd.Series, n_trials_values: tuple[int, ...],
                           risk_free_per_period: float = 0.0) -> dict[int, float]:
    """DSR at each N in `n_trials_values` -- ONE call, not N separate calls
    with the caller free to quote whichever N flatters them. This session's
    standing rule ("always quote DSR = x at N = y, never a bare number")
    is enforced by this function's shape: publishing a single cherry-picked
    N is a choice the caller has to actively make against this API, not the
    path of least resistance."""
    return {n: deflated_sharpe_ratio(returns, n_trials=n, risk_free_per_period=risk_free_per_period)["dsr"]
            for n in n_trials_values}


def bootstrap_sharpe_se(returns: pd.Series, risk_free_per_period: float = 0.0,
                         n_resamples: int = 5000, block_size: int | None = None,
                         seed: int = 42) -> dict:
    """Empirical standard error of the Sharpe estimator, by resampling --
    a model-free cross-check on `sharpe_se`'s analytic (Mertens 2002)
    formula, which assumes the skew/kurtosis correction it applies is
    itself estimated without error. Two resampling schemes:

    - `block_size=None`: IID (ordinary) bootstrap -- resamples individual
      periods with replacement, assuming no autocorrelation.
    - `block_size=k`: moving-block bootstrap (Kunsch 1989) -- resamples
      contiguous blocks of length k, preserving any short-range dependence
      weekly option P&L may carry (a position's payout this week is not
      independent of last week's realized vol regime).

    WHY THIS EXISTS: this session's H-A hypothesis test found the analytic
    sigma_SR is 1.7-1.8x ANTI-CONSERVATIVE (too small, not too large) at
    this strategy's measured skew/kurtosis -- the opposite of the initial
    hypothesis that bootstrapping would show the DSR was being too harsh.
    Publishing this number beside the analytic one makes that finding
    checkable rather than asserted.

    Returns per-period (NOT annualized) quantities: `se` (bootstrap std of
    the resampled Sharpe estimates), `ci_low`/`ci_high` (2.5/97.5
    percentiles of the resampled Sharpe distribution), `p_sr_le_zero`
    (fraction of resamples with Sharpe <= 0), and `n_resamples_used` (may be
    < n_resamples if some resamples had zero variance and were skipped)."""
    if len(returns) < 2:
        raise ValueError(f"need at least 2 return observations, got {len(returns)}")
    if n_resamples < 1:
        raise ValueError(f"n_resamples must be >= 1, got {n_resamples}")
    if block_size is not None and block_size < 1:
        raise ValueError(f"block_size must be >= 1 or None, got {block_size}")

    excess = (returns - risk_free_per_period).to_numpy(dtype="float64")
    t = len(excess)
    rng = np.random.RandomState(seed)
    draws = []

    for _ in range(n_resamples):
        if block_size is None:
            sample = rng.choice(excess, size=t, replace=True)
        else:
            n_blocks = int(math.ceil(t / block_size))
            starts = rng.randint(0, max(t - block_size, 0) + 1, size=n_blocks)
            sample = np.concatenate([excess[s:s + block_size] for s in starts])[:t]
        sd = sample.std(ddof=1)
        if sd > 0:
            draws.append(sample.mean() / sd)

    if not draws:
        raise ValueError("every resample had zero variance -- returns series is degenerate")

    draws = np.array(draws)
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return {
        "se": float(draws.std(ddof=1)),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "p_sr_le_zero": float((draws <= 0).mean()),
        "n_resamples_used": len(draws),
        "block_size": block_size,
        "seed": seed,
    }
