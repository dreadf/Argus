"""
The Manipulation-Proof Performance Measure (Goetzmann, Ingersoll, Spiegel &
Welch, "Portfolio Performance Manipulation and Manipulation-Proof
Performance Measures", Review of Financial Studies 2007 -- see SOURCES.md).

WHY THIS EXISTS: this session's H-C hypothesis test (see EXPERIMENT_29_
SHARPE_AUDIT.md and PROGRESS.md) asked whether a measure NOT gameable by
option-selling payoffs would still call this strategy's edge real. Sharpe
ratio can be gamed by option-like strategies almost by construction (GISW's
own result: a static option overlay can be built to maximize Sharpe with no
real skill, exactly the shape of payoff a short-vol credit spread produces).
MPPM is derived as the unique (up to an affine transform) performance
measure that CANNOT be inflated this way, under a power-utility investor
with constant relative risk aversion `rho`.

THE FORMULA (per-period returns `r`, per-period risk-free `rf`, `rho` != 1,
`dt` = the period length as a fraction of a year, e.g. 1/52 for weekly):

    MPPM(rho) = 1 / ((1 - rho) * dt) * ln( mean( ((1+r)/(1+rf))^(1-rho) ) )

This is the annualized certainty-equivalent EXCESS return a power-utility
investor with risk aversion `rho` would need, applied at a riskless rate, to
be indifferent to holding this return stream. rho=1 (log utility) is a
removable singularity, not implemented here -- report rho in [2, 5], the
GISW-recommended practical range, and its STABILITY across that range is
itself part of the evidence: a result that only looks good at one specific
rho is closer to being gamed than measured.

DOMAIN GUARD: if (1+r)/(1+rf) <= 0 for any observation (the account is wiped
out or worse that period), the ratio raised to a non-integer power (1-rho)
is undefined over the reals. This must RAISE, not silently produce NaN or
be dropped -- a wipeout is exactly the outcome MPPM exists to penalize, and
silently discarding it would erase the tail risk from the number meant to
price it. See H-C3 in the audit: at high leverage this genuinely fires.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def mppm(returns: pd.Series, risk_free_per_period: float, rho: float, dt: float) -> float:
    """Returns the annualized MPPM as a fraction (0.0087, not 0.87)."""
    if rho == 1:
        raise ValueError("rho=1 (log utility) is a removable singularity, not implemented")
    if dt <= 0:
        raise ValueError(f"dt must be > 0, got {dt}")
    if len(returns) < 1:
        raise ValueError("need at least 1 return observation")

    ratio = (1.0 + returns) / (1.0 + risk_free_per_period)
    if (ratio <= 0).any():
        bad = ratio[ratio <= 0]
        raise ValueError(
            f"{len(bad)} period(s) have (1+r)/(1+rf) <= 0 (a wipeout or worse) -- "
            f"MPPM is undefined here, not silently droppable. Worst: {ratio.min():.4f} "
            f"at index {ratio.idxmin()!r}."
        )

    mean_pow = float(np.mean(ratio.to_numpy(dtype="float64") ** (1.0 - rho)))
    return (1.0 / ((1.0 - rho) * dt)) * math.log(mean_pow)


def mppm_sweep(returns: pd.Series, risk_free_per_period: float, dt: float,
                rhos: tuple[float, ...] = (2.0, 3.0, 4.0, 5.0)) -> dict[float, float]:
    """MPPM at each rho in `rhos` -- stability across rho is itself part of
    the evidence (see module docstring)."""
    return {r: mppm(returns, risk_free_per_period, r, dt) for r in rhos}


def lever_returns(returns: pd.Series, risk_free_per_period: float, leverage: float) -> pd.Series:
    """r_levered = risk_free + leverage * (r - risk_free) -- the standard
    "borrow/lend at the riskless rate to hit a target risk level" construction
    used for the risk-matched comparison (H-C3): does the strategy beat
    buy-and-hold once both are scaled to the same volatility? Unlike a
    Sharpe-based comparison, MPPM of a levered series is NOT simply the
    unlevered MPPM times leverage (the geometric/CRRA math is nonlinear in
    leverage), which is exactly why this is a real test and not algebra."""
    return risk_free_per_period + leverage * (returns - risk_free_per_period)
