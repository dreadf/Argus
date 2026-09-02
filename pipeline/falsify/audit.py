"""
The Sharpe audit -- Experiment 29. ONE command reproduces EVERY figure in
EXPERIMENT_29_SHARPE_AUDIT.md:

    unset ALPACA_API_KEY ALPACA_SECRET_KEY GEMINI_API_KEY && \
        python -m pipeline.falsify.audit

WHY THIS FILE EXISTS: every other experiment in this repo has a runnable
`__main__` (pipeline/vol/experiment14_forecast.py through
experiment27_circuit_breaker.py; reconstruct.py; vrp_measure.py;
evidence_gate.py; spread_backtest.py; false_trip.py; step0_recheck.py --
`grep -rl "if __name__" pipeline/` confirms this). `pipeline/falsify/` was
the one part of this repo missing that convention: every number in W2 and
the four hypothesis tests (H-A through H-D) was first produced by an
unsaved `python3 -c` one-liner, which made them unverifiable by anyone,
including this session tomorrow -- exactly the failure mode this whole
submission claims to be immune to. This file closes that gap.

No network, no credentials needed -- reads only the already-fetched
output/data/raw_SPY_long.csv, output/data/vix9d.csv, output/data/vix3m.csv
(same inputs pipeline.backtest.reconstruct.replay() already uses).

REPRODUCIBILITY CAVEAT (found and fixed in .gitignore, but the fix still
needs a commit -- see EXPERIMENT_29_SHARPE_AUDIT.md): those three files
were NOT committed to git as of 2026-09-02 (`.gitignore`'s blanket
`output/data/*.csv` rule caught them silently). This command only runs
clean on a machine where they'd already been fetched; a fresh clone gets
FileNotFoundError instead. `.gitignore` now allow-lists them, but they
still need `git add` + a commit before this file's "no network, no
credentials" claim is true for anyone else. This affects reconstruct.py's
and vrp_measure.py's own __main__s identically -- not unique to this file.

Every random component is SEEDED so output is byte-stable across runs:
seed 42 for the Sharpe bootstrap (IID and block), matching the seed this
session's exploratory H-A run used; seed 7 is NOT used here (that seed
was this session's exploratory MPPM bootstrap CI, which is diagnostic only
and not one of the published headline figures -- omitted to keep this file
focused on what the writeup actually cites).
"""

from __future__ import annotations

import math

from pipeline.backtest.reconstruct import (
    _load_real_flagship_weeks,
    build_equity_curve,
    calibrate_skew_multiplier,
    replay,
)
from pipeline.falsify.deflated_sharpe import (
    bootstrap_sharpe_se,
    deflated_sharpe_curve,
    deflated_sharpe_ratio,
    min_track_record_length,
)
from pipeline.falsify.equity_sim import (
    CASH_ANNUAL_RATE,
    DEFAULT_SLIPPAGE_PER_SHARE,
    WEEKS_PER_YEAR,
    annualized_return_vol,
    sharpe_ratio,
    simulate_weekly_returns,
)
from pipeline.falsify.mppm import lever_returns, mppm_sweep

CASH_WEEKLY = CASH_ANNUAL_RATE / WEEKS_PER_YEAR
N_TRIALS_CURVE = (1, 5, 10, 30, 100)
N_TRIALS_HEADLINE = 30  # EXPERIMENT_MD_BASE_COUNT (29) + Experiment 28 -- see trial_count.py
BOOTSTRAP_SEED = 42
BOOTSTRAP_BLOCK_SIZE = 8
BOOTSTRAP_N_RESAMPLES = 5000


def _build_result_and_traded():
    """Shared setup: the calibrated replay and the walk-forward
    term-structure filter mask, identical to what reconstruct.py's own
    __main__ and vrp_measure.py already validate against tracked CSVs
    (gates G4/G5) -- this file adds no new backtest, only a new lens on
    the same one."""
    real_weeks = _load_real_flagship_weeks()
    a, b = calibrate_skew_multiplier(real_weeks)
    result = replay(a, b)
    curve = build_equity_curve(result)
    result = result.sort_values("entry").reset_index(drop=True)
    traded = curve["traded"].reset_index(drop=True)
    return result, traded


def compute_variant(result, traded, n_concurrent: int, label: str) -> dict:
    wr = simulate_weekly_returns(
        result, traded, per_trade_cap_pct=0.03,
        slippage_per_share=DEFAULT_SLIPPAGE_PER_SHARE, n_concurrent=n_concurrent,
    )
    ann_return, ann_vol = annualized_return_vol(wr)
    sr = sharpe_ratio(wr)
    # Fractional (%-of-running-peak) drawdown on the equity index -- NOT
    # reconstruct.py's `_max_drawdown`, which returns an ABSOLUTE dollar
    # drawdown on a raw $ P&L series (a different unit for a different use).
    # This is the same formula README's "5.8% worst drawdown" and
    # EXPERIMENT.md 12d's "5.63%/21.24%" figures describe.
    cum = (1 + wr).cumprod()
    running_peak = cum.cummax()
    max_dd = float(((running_peak - cum) / running_peak).max())

    dsr_n1 = deflated_sharpe_ratio(wr, n_trials=1, risk_free_per_period=CASH_WEEKLY)
    dsr_curve = deflated_sharpe_curve(wr, N_TRIALS_CURVE, risk_free_per_period=CASH_WEEKLY)

    return {
        "label": label,
        "n_concurrent": n_concurrent,
        "weeks": len(wr),
        "annualized_return": ann_return,
        "annualized_vol": ann_vol,
        "sharpe": sr,
        "max_drawdown": max_dd,
        "psr_n1": dsr_n1["dsr"],
        "dsr_curve": dsr_curve,
        "weekly_returns": wr,
    }


def run_audit() -> dict:
    result, traded = _build_result_and_traded()

    variant_b = compute_variant(result, traded, n_concurrent=1, label="B (single position, 3% cap)")
    variant_c = compute_variant(result, traded, n_concurrent=2, label="C (2 concurrent, 6% cap)")

    wr = variant_b["weekly_returns"]
    excess = wr - CASH_WEEKLY
    mintrl_weeks = min_track_record_length(wr, risk_free_per_period=CASH_WEEKLY)

    boot_iid = bootstrap_sharpe_se(wr, risk_free_per_period=CASH_WEEKLY,
                                    n_resamples=BOOTSTRAP_N_RESAMPLES, block_size=None, seed=BOOTSTRAP_SEED)
    boot_block = bootstrap_sharpe_se(wr, risk_free_per_period=CASH_WEEKLY,
                                      n_resamples=BOOTSTRAP_N_RESAMPLES, block_size=BOOTSTRAP_BLOCK_SIZE, seed=BOOTSTRAP_SEED)

    mppm_filtered = mppm_sweep(wr, CASH_WEEKLY, dt=1 / WEEKS_PER_YEAR)
    unfiltered_traded = traded.copy()
    unfiltered_traded[:] = True
    wr_unfiltered = simulate_weekly_returns(
        result, unfiltered_traded, per_trade_cap_pct=0.03,
        slippage_per_share=DEFAULT_SLIPPAGE_PER_SHARE, n_concurrent=1,
    )
    mppm_unfiltered = mppm_sweep(wr_unfiltered, CASH_WEEKLY, dt=1 / WEEKS_PER_YEAR)
    mppm_delta = {rho: mppm_filtered[rho] - mppm_unfiltered[rho] for rho in mppm_filtered}

    spy_returns = result["spot_entry"].pct_change().dropna()
    spy_vol = float(spy_returns.std(ddof=1) * math.sqrt(WEEKS_PER_YEAR))
    strat_vol = float(wr.std(ddof=1) * math.sqrt(WEEKS_PER_YEAR))
    risk_match_leverage = spy_vol / strat_vol
    levered = lever_returns(wr, CASH_WEEKLY, risk_match_leverage)
    try:
        mppm_levered = mppm_sweep(levered, CASH_WEEKLY, dt=1 / WEEKS_PER_YEAR)
    except ValueError as e:
        mppm_levered = {"error": str(e)}
    mppm_spy = mppm_sweep(spy_returns, CASH_WEEKLY, dt=1 / WEEKS_PER_YEAR)

    return {
        "variant_b": variant_b,
        "variant_c": variant_c,
        "mintrl_weeks": mintrl_weeks,
        "mintrl_years": mintrl_weeks / WEEKS_PER_YEAR if math.isfinite(mintrl_weeks) else float("inf"),
        "years_available": len(wr) / WEEKS_PER_YEAR,
        "bootstrap_iid": boot_iid,
        "bootstrap_block": boot_block,
        "mppm_filtered": mppm_filtered,
        "mppm_unfiltered": mppm_unfiltered,
        "mppm_delta": mppm_delta,
        "risk_match_leverage": risk_match_leverage,
        "mppm_levered_at_risk_match": mppm_levered,
        "mppm_spy_buy_and_hold": mppm_spy,
    }


def _print_report(r: dict) -> None:
    b, c = r["variant_b"], r["variant_c"]
    print("=== Experiment 29: Sharpe audit (reproducible via `python -m pipeline.falsify.audit`) ===\n")
    for v in (b, c):
        print(f"{v['label']}: weeks={v['weeks']}  ann_return={v['annualized_return']:.4%}  "
              f"ann_vol={v['annualized_vol']:.4%}  Sharpe={v['sharpe']:+.3f}  "
              f"max_DD={v['max_drawdown']:.2%}  PSR(N=1)={v['psr_n1']:.4f}")
        for n, dsr in v["dsr_curve"].items():
            print(f"    DSR(N={n:>3}) = {dsr:.4f}")
    print()
    print(f"MinTRL: {r['mintrl_weeks']:.0f} weeks ({r['mintrl_years']:.1f} years) needed "
          f"vs {r['years_available']:.1f} years available")
    print()
    print(f"Bootstrap SE (variant B, seed={BOOTSTRAP_SEED}, n={BOOTSTRAP_N_RESAMPLES}):")
    print(f"    IID:   se={r['bootstrap_iid']['se']:.5f}  P(SR<=0)={r['bootstrap_iid']['p_sr_le_zero']:.4f}")
    print(f"    block: se={r['bootstrap_block']['se']:.5f}  P(SR<=0)={r['bootstrap_block']['p_sr_le_zero']:.4f}")
    print()
    print("MPPM (variant B, annualized certainty-equivalent excess return):")
    for rho in r["mppm_filtered"]:
        print(f"    rho={rho:.0f}  filtered={r['mppm_filtered'][rho]:+.4%}  "
              f"unfiltered={r['mppm_unfiltered'][rho]:+.4%}  delta={r['mppm_delta'][rho]:+.4%}")
    print()
    print(f"Risk-matched leverage ({r['risk_match_leverage']:.1f}x, to SPY's volatility):")
    if "error" in r["mppm_levered_at_risk_match"]:
        print(f"    levered strategy: WIPED OUT -- {r['mppm_levered_at_risk_match']['error']}")
    else:
        for rho in r["mppm_levered_at_risk_match"]:
            print(f"    rho={rho:.0f}  levered_strategy={r['mppm_levered_at_risk_match'][rho]:+.4%}  "
                  f"SPY_buy_and_hold={r['mppm_spy_buy_and_hold'][rho]:+.4%}")


if __name__ == "__main__":
    report = run_audit()
    _print_report(report)
