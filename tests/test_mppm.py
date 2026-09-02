"""
Tests for pipeline/falsify/mppm.py -- no network, no credentials, literal
fixtures only, matching this project's established test-file convention.

Run: unset ALPACA_API_KEY ALPACA_SECRET_KEY GEMINI_API_KEY && \
     python -m pytest tests/test_mppm.py -v
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from pipeline.falsify.mppm import lever_returns, mppm, mppm_sweep


def test_mppm_known_answer_hand_computed():
    """A small, exactly-specified series, with MPPM recomputed here directly
    from the raw formula (not by calling internal helpers) as an independent
    cross-check -- the same discipline test_deflated_sharpe.py's toy case
    used."""
    returns = pd.Series([0.01, -0.02, 0.015, 0.005, -0.01])
    rf = 0.03 / 52
    rho = 3.0
    dt = 1 / 52

    ratio = (1 + returns) / (1 + rf)
    expected = (1 / ((1 - rho) * dt)) * math.log(float((ratio ** (1 - rho)).mean()))

    assert mppm(returns, rf, rho, dt) == pytest.approx(expected, abs=1e-12)


def test_mppm_of_constant_series_equals_continuously_compounded_excess_return():
    """C1: when every period has the SAME return r0, there is no risk to
    penalize, so MPPM must equal ln((1+r0)/(1+rf))/dt EXACTLY, independent
    of rho -- risk aversion cannot matter when there is nothing risky.
    A version of MPPM that depends on rho even for a riskless series would
    be measuring something other than a certainty-equivalent."""
    r0 = 0.001
    rf = 0.03 / 52
    dt = 1 / 52
    returns = pd.Series([r0] * 40)
    expected = math.log((1 + r0) / (1 + rf)) / dt

    for rho in (2.0, 3.0, 4.0, 5.0, 10.0):
        assert mppm(returns, rf, rho, dt) == pytest.approx(expected, abs=1e-10), f"failed at rho={rho}"


def test_mppm_rho_equals_1_raises_cleanly():
    """rho=1 (log utility) is a removable singularity (division by
    1-rho=0) -- must raise a clear error, not divide by zero silently."""
    returns = pd.Series([0.01, -0.01, 0.02])
    with pytest.raises(ValueError, match="rho"):
        mppm(returns, 0.03 / 52, rho=1.0, dt=1 / 52)


def test_mppm_wipeout_raises_not_nan():
    """H-C3's real finding: at high enough leverage the account can be
    wiped out (a period return <= -100%), which makes (1+r)/(1+rf) <= 0 --
    MPPM must RAISE here, since silently returning NaN would erase the tail
    risk from the exact number meant to price it."""
    returns = pd.Series([0.01, -1.5, 0.02])  # -150% one period: genuinely wiped out and negative
    with pytest.raises(ValueError, match="wipeout"):
        mppm(returns, 0.03 / 52, rho=3.0, dt=1 / 52)


def test_mppm_sweep_returns_one_value_per_rho():
    returns = pd.Series(np.random.RandomState(5).normal(0.001, 0.01, 50))
    rf = 0.03 / 52
    dt = 1 / 52
    out = mppm_sweep(returns, rf, dt, rhos=(2.0, 3.0, 4.0))
    assert set(out.keys()) == {2.0, 3.0, 4.0}
    for rho, val in out.items():
        assert val == pytest.approx(mppm(returns, rf, rho, dt), abs=1e-12)


def test_lever_returns_formula_and_leverage_one_is_identity():
    returns = pd.Series([0.01, -0.02, 0.03])
    rf = 0.03 / 52

    identity = lever_returns(returns, rf, leverage=1.0)
    pd.testing.assert_series_equal(identity, returns, check_exact=False, atol=1e-12)

    levered = lever_returns(returns, rf, leverage=2.0)
    expected = rf + 2.0 * (returns - rf)
    pd.testing.assert_series_equal(levered, expected, check_exact=False, atol=1e-12)


def test_lever_returns_amplifies_volatility_monotonically():
    """Sanity check underlying H-C3's leverage sweep: higher leverage must
    strictly increase the return series' volatility."""
    returns = pd.Series(np.random.RandomState(3).normal(0.0005, 0.01, 100))
    rf = 0.03 / 52
    vols = [float(lever_returns(returns, rf, L).std()) for L in (1, 2, 4, 8)]
    assert all(b > a for a, b in zip(vols, vols[1:])), vols
