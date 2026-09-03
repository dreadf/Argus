"""
Tests for pipeline/falsify/engine.py (W4): the generic falsify() gauntlet.

Uses small, synthetic data with a low n_permutations so these stay in the
fast (<10s) default suite -- the slow suite (test_audit.py) is reserved for
reproducing published figures end to end, not for exercising this engine's
logic, which has no published figures of its own yet (W3 will generate
those).
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.falsify.engine import Hypothesis, Verdict, falsify, _walk_forward_threshold


def _cross_sectional_data(seed, signal_strength, n_days=60, n_symbols=8):
    rng = np.random.default_rng(seed)
    rows_scores = []
    rows_fwd = []
    for day in range(n_days):
        ts = pd.Timestamp("2024-01-01") + pd.Timedelta(days=day)
        fwd = rng.normal(size=n_symbols)
        noise = rng.normal(scale=1.0, size=n_symbols)
        score = signal_strength * fwd + (1 - signal_strength) * noise
        for sym_i in range(n_symbols):
            sym = f"SYM{sym_i}"
            rows_scores.append({"timestamp": ts, "symbol": sym, "score": score[sym_i]})
            rows_fwd.append({"timestamp": ts, "symbol": sym, "fwd_5d_return": fwd[sym_i]})
    return pd.DataFrame(rows_scores), pd.DataFrame(rows_fwd)


def _skip_filter_data(seed, signal_helps, n_weeks=200):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-03", periods=n_weeks, freq="W-FRI")
    if signal_helps:
        # weeks with low signal are genuinely bad (large negative pnl tail);
        # skipping them (signal below its own walk-forward threshold) should
        # retain more total P&L than a random schedule of the same skip rate.
        signal = rng.uniform(0, 1, size=n_weeks)
        pnl = np.where(signal < 0.33, rng.normal(-2.0, 0.5, size=n_weeks), rng.normal(0.1, 0.2, size=n_weeks))
    else:
        signal = rng.uniform(0, 1, size=n_weeks)
        pnl = rng.normal(0.05, 0.3, size=n_weeks)  # independent of signal
    return pd.Series(signal, index=dates), pd.Series(pnl, index=dates)


def test_hypothesis_shape_requires_exactly_one():
    scores, fwd = _cross_sectional_data(1, 0.8)
    signal, pnl = _skip_filter_data(1, True)

    with pytest.raises(ValueError, match="neither shape"):
        Hypothesis(name="empty").shape()

    with pytest.raises(ValueError, match="both shapes"):
        Hypothesis(name="both", scores=scores, fwd_returns=fwd, signal=signal, pnl=pnl).shape()

    assert Hypothesis(name="cs", scores=scores, fwd_returns=fwd).shape() == "cross_sectional"
    assert Hypothesis(name="sf", signal=signal, pnl=pnl).shape() == "skip_filter"


def test_walk_forward_threshold_matches_vrp_measure_convention():
    # Same rule vrp_measure.walk_forward_threshold() and reconstruct.py use:
    # NaN before min_history, trailing quantile strictly before each row after.
    s = pd.Series(range(100), index=pd.date_range("2020-01-01", periods=100))
    thr = _walk_forward_threshold(s, min_history=10, percentile=0.5)
    assert thr.iloc[:10].isna().all()
    assert thr.iloc[10] == pytest.approx(s.iloc[:10].quantile(0.5))
    assert thr.iloc[50] == pytest.approx(s.iloc[:50].quantile(0.5))


# n_permutations=50 (not W3/Experiment 21's usual 2000) is deliberate here:
# these are planted, extreme-effect-size synthetic cases (real signal vs.
# pure noise), so 50 shuffles already separates them cleanly and keeps this
# file inside the fast (<10s) default suite -- G1. 2000 is exercised for
# real once W3's propose.py runs against real data, not duplicated here.

def test_cross_sectional_real_signal_survives():
    scores, fwd = _cross_sectional_data(seed=7, signal_strength=0.85)
    hyp = Hypothesis(name="strong_signal", scores=scores, fwd_returns=fwd)
    verdict = falsify(hyp, n_permutations=50, seed=42)
    assert isinstance(verdict, Verdict)
    assert verdict.survived is True
    assert verdict.killed_at is None
    assert "randomization_null" in verdict.detail


def test_cross_sectional_noise_is_killed():
    scores, fwd = _cross_sectional_data(seed=3, signal_strength=0.0)
    hyp = Hypothesis(name="pure_noise", scores=scores, fwd_returns=fwd)
    verdict = falsify(hyp, n_permutations=50, seed=42)
    assert verdict.survived is False
    assert verdict.killed_at in ("ic_significance", "randomization_null")


def test_cross_sectional_verdict_is_deterministic_at_fixed_seed():
    scores, fwd = _cross_sectional_data(seed=7, signal_strength=0.85)
    hyp = Hypothesis(name="strong_signal", scores=scores, fwd_returns=fwd)
    v1 = falsify(hyp, n_permutations=50, seed=42)
    v2 = falsify(hyp, n_permutations=50, seed=42)
    assert v1.detail["randomization_null"]["p_value"] == v2.detail["randomization_null"]["p_value"]


def test_skip_filter_real_signal_survives():
    signal, pnl = _skip_filter_data(seed=4, signal_helps=True)
    hyp = Hypothesis(name="good_filter", signal=signal, pnl=pnl)
    verdict = falsify(hyp, n_permutations=50, seed=42, min_history=20, headline_n=1)
    assert verdict.survived is True
    assert verdict.killed_at is None
    assert verdict.detail["randomization_null"]["p_value"] < 0.05
    assert verdict.detail["dsr"]["dsr"] >= 0.5


def test_skip_filter_useless_signal_is_killed():
    signal, pnl = _skip_filter_data(seed=13, signal_helps=False)
    hyp = Hypothesis(name="useless_filter", signal=signal, pnl=pnl)
    verdict = falsify(hyp, n_permutations=50, seed=42, min_history=20, headline_n=31)
    assert verdict.survived is False
    assert verdict.killed_at in ("randomization_null", "deflated_sharpe")


def test_skip_filter_false_trip_stage_kills_a_signal_that_blocks_real_winners():
    # A signal deliberately anti-correlated with the winning weeks it will
    # be tested against: it drops right before every real winner, so its
    # walk-forward threshold blocks them almost every time.
    n_weeks = 80
    dates = pd.date_range("2020-01-03", periods=n_weeks, freq="W-FRI")
    rng = np.random.default_rng(5)
    signal = pd.Series(rng.uniform(0.4, 1.0, size=n_weeks), index=dates)
    pnl = pd.Series(rng.normal(0.05, 0.2, size=n_weeks), index=dates)

    winner_dates = dates[30:60]
    signal.loc[winner_dates] = 0.0  # forces these weeks below any reasonable walk-forward threshold

    results_df = pd.DataFrame({
        "entry": dates,
        "distance": 0.03,
        "width": 5.0,
        "win": dates.isin(winner_dates),
        "missing_data": False,
    })

    hyp = Hypothesis(name="anti_correlated", signal=signal, pnl=pnl,
                      results_df=results_df, distance=0.03, width=5.0)
    verdict = falsify(hyp, n_permutations=50, seed=42, min_history=20)
    assert verdict.survived is False
    assert verdict.killed_at == "false_trip"
    assert verdict.detail["false_trip"]["blocked_pct"] > 0.30


def test_false_trip_stage_is_skipped_without_a_results_df():
    signal, pnl = _skip_filter_data(seed=4, signal_helps=True)
    hyp = Hypothesis(name="no_results_df", signal=signal, pnl=pnl)
    verdict = falsify(hyp, n_permutations=50, seed=42, min_history=20, headline_n=1)
    # no false_trip stage ran, but the hypothesis still gets a verdict via the other stages
    assert verdict.detail["false_trip"] is None


def test_deflated_sharpe_stage_uses_live_trial_count_when_not_supplied():
    from pipeline.falsify.trial_count import total_trial_count
    signal, pnl = _skip_filter_data(seed=4, signal_helps=True)
    hyp = Hypothesis(name="good_filter", signal=signal, pnl=pnl)
    verdict = falsify(hyp, n_permutations=50, seed=42, min_history=20)  # headline_n omitted
    assert verdict.detail["dsr"]["n_trials"] == total_trial_count()
