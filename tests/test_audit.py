"""
V8 (the anti-bullshit gate): every number published in EXPERIMENT_29_
SHARPE_AUDIT.md must be reproducible by `python -m pipeline.falsify.audit`,
and this file is what fails loudly if the writeup and the code ever
disagree.

Marked `slow` and excluded from the default `pytest tests/` run (see
pyproject.toml's [tool.pytest.ini_options]) because run_audit() calls
reconstruct.calibrate_skew_multiplier's grid search (~13s, pre-existing,
not this test's doing) plus two 5000-resample bootstraps (~4s). That is
G1's <10s budget blown by a single test, so it runs on its own:

    unset ALPACA_API_KEY ALPACA_SECRET_KEY GEMINI_API_KEY && \
        python -m pytest tests/test_audit.py -m slow -v

Every figure below was read directly off a real run of `python -m
pipeline.falsify.audit` on 2026-09-02, then re-verified 2026-09-03 after
Experiment 30 landed and changed the trial count N from 30 to 31 (see
trial_count.py's docstring for why Experiment 30 counts as a trial and
Experiment 29's own collateral-bug fix does not) -- confirmed
byte-identical across two consecutive runs first, both times. If this
test ever fails, the writeup is wrong (update it) or the code changed
(figure out why and update both deliberately) -- it must never be "fixed"
by loosening the tolerance to match whatever the code happens to produce
that day.
"""

from __future__ import annotations

import pytest

from pipeline.falsify.audit import run_audit
from pipeline.falsify.trial_count import total_trial_count

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def audit_report():
    return run_audit()


def test_headline_n_is_computed_not_hardcoded(audit_report):
    """The exact staleness this test exists to prevent already happened
    once: audit.py used to have its own N_TRIALS_HEADLINE = 30 module
    constant, which silently went stale the moment Experiment 30 landed
    and changed the true count to 31. Fixed by computing headline_n from
    trial_count.total_trial_count() at call time instead -- this asserts
    the audit's own headline_n always matches that live source, and a
    source-level check (mirroring deflated_sharpe.py's own C1 test) that
    audit.py never reintroduces a second hardcoded copy."""
    assert audit_report["headline_n"] == total_trial_count()

    import pipeline.falsify.audit as mod
    src = open(mod.__file__).read()
    assert "N_TRIALS_HEADLINE" not in src, "a hardcoded headline N constant was reintroduced into audit.py"


def test_variant_b_single_position(audit_report):
    b = audit_report["variant_b"]
    assert b["weeks"] == 538
    assert b["annualized_return"] == pytest.approx(0.038931, abs=5e-5)
    assert b["annualized_vol"] == pytest.approx(0.015555, abs=5e-5)
    assert b["sharpe"] == pytest.approx(0.574, abs=2e-3)
    assert b["max_drawdown"] == pytest.approx(0.0289, abs=5e-4)
    assert b["psr_n1"] == pytest.approx(0.8942, abs=5e-4)
    assert b["dsr_curve"][30] == pytest.approx(0.2049, abs=5e-4)  # illustrative curve point, NOT the current headline N
    assert b["dsr_headline_n"] == 31
    assert b["dsr_headline"] == pytest.approx(0.2011, abs=5e-4)


def test_variant_c_two_concurrent_reproduces_repo_published_figures(audit_report):
    """V4: variant C (n_concurrent=2, 6% effective cap = CRASH_DAY_BUDGET_PCT)
    must reproduce EXPERIMENT.md 12d's vol (3.27%) within noise -- this was
    the corroboration that justified using this convention at all. (README's
    max drawdown used to be an independent cross-check at 5.8%; README has
    since been updated to state THIS number directly as "5.9%", so the
    tight tolerance below is now checking self-consistency with the doc
    that quotes it, not an independent corroboration.)"""
    c = audit_report["variant_c"]
    assert c["weeks"] == 538
    assert c["annualized_vol"] == pytest.approx(0.0327, abs=5e-4)  # EXPERIMENT.md 12d
    assert c["max_drawdown"] == pytest.approx(0.059, abs=5e-4)  # README.md (post-correction)
    assert c["sharpe"] == pytest.approx(0.563, abs=2e-3)
    assert c["dsr_curve"][30] == pytest.approx(0.2004, abs=5e-4)  # illustrative curve point, NOT the current headline N
    assert c["dsr_headline_n"] == 31
    assert c["dsr_headline"] == pytest.approx(0.1966, abs=5e-4)


def test_mintrl(audit_report):
    assert audit_report["mintrl_weeks"] == pytest.approx(932, abs=5)
    assert audit_report["years_available"] == pytest.approx(10.3, abs=0.1)


def test_bootstrap_se_matches_the_headline_anti_conservatism_finding(audit_report):
    """H-A's headline: the analytic sigma_SR is ~1.7-1.8x anti-conservative
    versus the bootstrap at this strategy's skew/kurtosis."""
    from pipeline.falsify.deflated_sharpe import sharpe_se
    b = audit_report["variant_b"]
    wr = b["weekly_returns"]
    from pipeline.falsify.audit import CASH_WEEKLY
    excess = wr - CASH_WEEKLY
    sr_hat = float(excess.mean() / excess.std(ddof=1))
    analytic = sharpe_se(sr_hat, excess)

    iid_se = audit_report["bootstrap_iid"]["se"]
    block_se = audit_report["bootstrap_block"]["se"]
    assert iid_se == pytest.approx(0.1148, abs=5e-3)
    assert block_se == pytest.approx(0.1076, abs=5e-3)
    ratio = iid_se / analytic
    assert 1.5 < ratio < 2.1, f"expected the ~1.7-1.8x anti-conservatism finding, got {ratio:.2f}x"


def test_distribution_shape_matches_headline_skew_kurtosis(audit_report):
    """H-A/H-B both cite skew=-11.80/kurtosis=154.2 in prose without this
    number ever having been in run_audit()'s output before -- gated here
    for the same reason as the other additions on this date."""
    ds = audit_report["distribution_shape"]
    assert ds["skew"] == pytest.approx(-11.80, abs=0.05)
    assert ds["kurtosis"] == pytest.approx(154.2, abs=0.5)


def test_bootstrap_ci_matches_the_right_skewed_finding(audit_report):
    """H-A's other headline claim ('95% CI roughly [-0.08, +3.9]') --
    previously computed once ad hoc and never re-verified against a
    permanent source."""
    import math
    from pipeline.falsify.equity_sim import WEEKS_PER_YEAR
    iid = audit_report["bootstrap_iid"]
    ci_low_ann = iid["ci_low"] * math.sqrt(WEEKS_PER_YEAR)
    ci_high_ann = iid["ci_high"] * math.sqrt(WEEKS_PER_YEAR)
    assert ci_low_ann == pytest.approx(-0.077, abs=0.01)
    assert ci_high_ann == pytest.approx(3.92, abs=0.1)
    assert ci_low_ann < 0 < ci_high_ann, "the CI should straddle zero, which is the whole point of the finding"


def test_monthly_quarterly_aggregation_h_b(audit_report):
    """H-B: aggregating to monthly/quarterly should visibly tame skew and
    kurtosis (the CLT working as expected) while the headline DSR stays
    roughly flat, because the loss of observations offsets the
    non-normality gain. This whole comparison previously existed only as
    prose, never as a reproducible section -- exactly the gap that let the
    0.49 error happen on a DIFFERENT number in this same document.

    Values are at N=31 (post-Experiment-30); field renamed from the
    N-specific `dsr_n30` to `dsr_headline` for the same reason
    test_headline_n_is_computed_not_hardcoded exists -- a field name that
    bakes in a specific N is the same staleness risk as a hardcoded
    constant, just moved one level up."""
    levels = audit_report["aggregation_levels"]
    assert levels["weekly"]["n_periods"] == 538
    assert levels["monthly"]["n_periods"] == 128
    assert levels["quarterly"]["n_periods"] == 43

    # non-normality must fall monotonically as the period lengthens
    kurts = [levels[l]["kurtosis"] for l in ("weekly", "monthly", "quarterly")]
    assert kurts[0] > kurts[1] > kurts[2], f"kurtosis should fall as periods lengthen, got {kurts}"
    skews = [abs(levels[l]["skew"]) for l in ("weekly", "monthly", "quarterly")]
    assert skews[0] > skews[1] > skews[2], f"|skew| should fall as periods lengthen, got {skews}"

    assert levels["weekly"]["dsr_headline"] == pytest.approx(0.2011, abs=5e-4)
    assert levels["monthly"]["dsr_headline"] == pytest.approx(0.1967, abs=5e-4)
    assert levels["quarterly"]["dsr_headline"] == pytest.approx(0.2227, abs=5e-4)
    # the whole point of H-B: DSR must NOT meaningfully improve at any horizon
    assert max(levels[l]["dsr_headline"] for l in levels) - min(levels[l]["dsr_headline"] for l in levels) < 0.05, \
        "H-B claims no material gain at any aggregation horizon -- this checks that claim, not just the numbers"


def test_mppm_filtered_reproduces_the_published_headline(audit_report):
    """V5: MPPM +0.868% (rho=2) and +0.855% (rho=3), tight tolerance since
    this has no resampling randomness -- it is deterministic given the
    replay, so it should match almost exactly."""
    m = audit_report["mppm_filtered"]
    assert m[2] == pytest.approx(0.008677, abs=2e-5)
    assert m[3] == pytest.approx(0.008550, abs=2e-5)


def test_mppm_filter_costs_return_vs_unfiltered(audit_report):
    """V7: the writeup must state this unflattering finding -- the filter
    costs MPPM relative to trading every week, corroborating EXPERIMENT.md
    12d's 'insurance, not an edge' via an independent, non-gameable measure."""
    delta = audit_report["mppm_delta"]
    assert delta[2] < 0
    assert delta[2] == pytest.approx(-0.002187, abs=2e-5)


def test_filtered_vs_unfiltered_raw_sharpe_variant_c(audit_report):
    """Added after a real error: this exact comparison (filtered vs
    unfiltered raw Sharpe, variant C basis) was drafted from memory into
    README replacement text instead of being computed, stating 0.49 for the
    unfiltered Sharpe when the true value is 0.350 -- caught and corrected
    2026-09-02. Gated here so it can never again be quoted without being
    run."""
    fu = audit_report["filtered_vs_unfiltered_c"]
    assert fu["filtered_sharpe"] == pytest.approx(0.563, abs=2e-3)
    assert fu["unfiltered_sharpe"] == pytest.approx(0.350, abs=2e-3)
    assert fu["unfiltered_max_drawdown"] == pytest.approx(0.1759, abs=5e-4)
    dd_ratio = fu["unfiltered_max_drawdown"] / fu["filtered_max_drawdown"]
    assert dd_ratio == pytest.approx(2.98, abs=0.1), "the '4x smaller drawdown' claim was also wrong -- true ratio is ~3x"


def test_ex_2018_filtered_and_unfiltered_are_nearly_identical(audit_report):
    """The stale README line ('take 2018 out and the filter underperforms,
    0.38 Sharpe against 0.63') was computed under the pre-collateral-fix
    methodology. Under the corrected one, ex-2018 the two are a wash --
    a materially different finding, not just a different number, so this
    is gated rather than left as prose someone has to trust."""
    ex = audit_report["ex2018"]
    assert ex["n_weeks"] == 487
    assert ex["filtered"]["sharpe"] == pytest.approx(0.594, abs=5e-3)
    assert ex["unfiltered"]["sharpe"] == pytest.approx(0.603, abs=5e-3)
    assert abs(ex["filtered"]["sharpe"] - ex["unfiltered"]["sharpe"]) < 0.05, \
        "ex-2018 filtered and unfiltered should be nearly identical (a wash), not a big gap"


def test_risk_matched_leverage_loses_to_spy_buy_and_hold(audit_report):
    """V7 (the other unflattering finding): at SPY-matched volatility, the
    levered strategy's MPPM must be BELOW SPY buy-and-hold's at every rho
    tested -- if this ever flips, the writeup's headline claim is wrong."""
    r = audit_report
    assert r["risk_match_leverage"] == pytest.approx(11.2, abs=0.5)
    levered = r["mppm_levered_at_risk_match"]
    spy = r["mppm_spy_buy_and_hold"]
    assert "error" not in levered, "strategy wiped out at risk-matched leverage -- writeup's leverage figure is stale"
    for rho in (2, 3):
        assert levered[rho] < spy[rho], f"rho={rho}: levered strategy should lose to SPY buy-and-hold"

    # the writeup's specific claim: by rho=4 the levered strategy's MPPM
    # goes negative while SPY's stays comfortably positive -- pinned exactly
    # rather than left as a description of a run nobody re-checked.
    assert levered[4] < 0, "writeup claims the levered strategy's MPPM goes negative by rho=4"
    assert spy[4] > 0.03, "writeup claims SPY stays 'comfortably positive' at rho=4"
