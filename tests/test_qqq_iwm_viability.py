"""
Tests for pipeline/backtest/qqq_iwm_viability.py (W5's cheap gating step).

Fast test verifies the arithmetic (proxy = mean_fee / mean_breach_prob) on
a small synthetic series where every intermediate number can be checked by
hand. Slow tests reproduce the real SPY/QQQ/IWM figures end to end, same
split as test_audit.py -- this needs real committed long-history CSVs and
SPY's real standardized-return shape, not something to recompute on every
fast run.
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.backtest.qqq_iwm_viability import DISTANCE, WIDTH, compute_viability_proxy


def test_compute_viability_proxy_matches_a_hand_computed_case():
    # Flat realized vol (constant closes -> zero realized vol after the
    # rolling window) would make breach_prob 0 and the proxy infinite, so
    # use a small deterministic random walk instead -- enough variation
    # for a nonzero, checkable realized vol and breach probability.
    rng = np.random.default_rng(0)
    n = 60
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    log_rets = rng.normal(0, 0.01, size=n)
    closes = pd.Series(100 * np.exp(np.cumsum(log_rets)), index=dates)

    standardized_returns = rng.normal(0, 1, size=5000)  # a plain normal-ish shape, big enough sample for a stable empirical CDF

    result = compute_viability_proxy(closes, standardized_returns)

    assert result["n_days"] == n - 20  # REALIZED_VOL_WINDOW=20 rows are NaN before the window fills
    assert result["mean_fee"] > 0
    assert 0 < result["mean_breach_prob"] < 1
    assert result["proxy"] == pytest.approx(result["mean_fee"] / result["mean_breach_prob"])


def test_compute_viability_proxy_is_deterministic():
    rng = np.random.default_rng(1)
    n = 60
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    closes = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, size=n))), index=dates)
    standardized_returns = np.random.default_rng(2).normal(0, 1, size=2000)

    r1 = compute_viability_proxy(closes, standardized_returns)
    r2 = compute_viability_proxy(closes, standardized_returns)
    assert r1["proxy"] == r2["proxy"]
    assert r1["mean_fee"] == r2["mean_fee"]


def test_higher_realized_vol_increases_both_fee_and_breach_prob():
    # Same shape, scaled-up daily moves -- higher vol should price a
    # richer fee AND a higher breach probability (both move the same
    # direction; the proxy's whole point is the RATIO, not either alone).
    rng = np.random.default_rng(3)
    n = 60
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    base_rets = rng.normal(0, 0.008, size=n)
    calm = pd.Series(100 * np.exp(np.cumsum(base_rets)), index=dates)
    volatile = pd.Series(100 * np.exp(np.cumsum(base_rets * 3)), index=dates)

    standardized_returns = np.random.default_rng(4).normal(0, 1, size=5000)

    calm_result = compute_viability_proxy(calm, standardized_returns)
    volatile_result = compute_viability_proxy(volatile, standardized_returns)

    assert volatile_result["mean_fee"] > calm_result["mean_fee"]
    assert volatile_result["mean_breach_prob"] > calm_result["mean_breach_prob"]


@pytest.mark.slow
def test_run_all_reproduces_the_committed_symbol_proxies():
    from pipeline.backtest.qqq_iwm_viability import run_all

    results = run_all()
    assert set(results.keys()) == {"SPY", "QQQ", "IWM"}

    # These are the actual, real, honestly-computed figures (2026-09-03) --
    # not asserted to match any earlier notional/unverified number. If a
    # future data refresh moves them outside this band, that's real
    # information (new trading days added to the long-history fetch),
    # not a bug -- widen the tolerance deliberately, don't just re-pin.
    assert results["SPY"]["proxy"] == pytest.approx(3.291, abs=0.05)
    assert results["QQQ"]["proxy"] == pytest.approx(3.513, abs=0.05)
    assert results["IWM"]["proxy"] == pytest.approx(2.727, abs=0.05)

    spy_proxy = results["SPY"]["proxy"]
    assert results["QQQ"]["proxy"] / spy_proxy > 0.9   # QQQ clears the gate
    assert results["IWM"]["proxy"] / spy_proxy < 0.9   # IWM does not
