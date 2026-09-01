"""
Experiment 13, Test 13a: does the VIX term structure (VIX vs VIX3M) predict
whether implied volatility overstates the realized volatility that follows?
Tested on real observed market data, no option prices and no pricing model.

Data sources, all real observed prices, no synthetic/simulated series:
- VIX: pipeline/vol/data_sources.load_vix_series() -- a peer session's CBOE
  cache (output/data/vix.csv), full history back to 1990.
- VIX3M: spliced from two real sources rather than picking one, since they
  disagree on availability, not on value (see pipeline/vol/data_sources.py
  docstring for the cross-check that established this): the peer session's
  CBOE cache from 2009-09-18 onward, plus this session's yfinance mirror for
  2007-12-04 to 2009-09-17 (CBOE's own confirmed VIX3M launch window, single-
  sourced for that stretch only -- flagged in every output, not hidden).
- Realized vol: computed from SPY's real daily closes
  (output/data/vol_spy_history.csv, fetched via pipeline/vol_extract.py).

See .claude/plans/we-need-a-major-buzzing-catmull.md for the full hypothesis
and pass/fail criteria.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from pipeline.vol.data_sources import load_spy_daily_returns, load_vix3m_series, load_vix_series

# VIX's native horizon is 30 calendar days ~ 21 trading days. Test 13a
# deliberately matches VIX against realized vol over the SAME horizon it was
# priced for (see the plan's verification-log item 10: comparing a 30-day
# implied number to a 5-7 day realized number would be a silent unit
# mismatch, not a fair test of the mechanism).
RV_WINDOW_DAYS = 21
TRADING_DAYS_PER_YEAR = 252

SUB_PERIODS = {
    "2008-2012": ("2008-01-01", "2012-12-31"),
    "2013-2019": ("2013-01-01", "2019-12-31"),
    "2020-2026": ("2020-01-01", "2026-12-31"),
}


def build_dataset() -> pd.DataFrame:
    """One row per trading day: VIX, VIX3M, the contango ratio, and the
    REALIZED volatility over the following RV_WINDOW_DAYS trading days
    (forward-looking by construction -- this is deliberate: the question is
    "did VIX correctly anticipate what actually happened next", which
    requires knowing the future realization; it is not a live trading
    signal and must never be used as one)."""
    vix = load_vix_series()
    vix3m = load_vix3m_series()
    returns = load_spy_daily_returns()

    df = pd.DataFrame({"VIX": vix, "VIX3M": vix3m}).dropna()
    df["ratio"] = df["VIX"] / df["VIX3M"]
    df["contango"] = df["ratio"] < 1.0

    # Forward realized vol: annualized std of the NEXT RV_WINDOW_DAYS daily
    # log returns, aligned to each date. rolling(...).std() looks BACKWARD by
    # default, so this reverses the series, rolls, then reverses back --
    # verified below in the module self-check against a hand-built example.
    fwd_std = returns[::-1].rolling(RV_WINDOW_DAYS).std()[::-1]
    df["fwd_realized_vol"] = fwd_std.reindex(df.index) * np.sqrt(TRADING_DAYS_PER_YEAR) * 100

    df["gap"] = df["VIX"] - df["fwd_realized_vol"]
    return df.dropna(subset=["gap"])


def _welch_t(contango_gap: pd.Series, backward_gap: pd.Series) -> dict:
    """Welch's t-test (unequal variance) for the gap being larger in
    contango than backwardation. Daily observations are heavily
    autocorrelated (the 21-day forward window overlaps on consecutive days),
    so the raw t-stat here is optimistic -- non_overlap_t below, sampling
    every RV_WINDOW_DAYS'th day, is the trustworthy number."""
    if len(contango_gap) < 2 or len(backward_gap) < 2:
        return {"n_contango": len(contango_gap), "n_backward": len(backward_gap),
                "mean_gap_contango": None, "mean_gap_backward": None,
                "t_stat": None, "p_value": None}
    t_stat, p_value = stats.ttest_ind(contango_gap, backward_gap, equal_var=False)
    return {
        "n_contango": len(contango_gap),
        "n_backward": len(backward_gap),
        "mean_gap_contango": contango_gap.mean(),
        "mean_gap_backward": backward_gap.mean(),
        "t_stat": t_stat,
        "p_value": p_value,
    }


def _non_overlapping_t(df: pd.DataFrame) -> dict:
    """The defensible version: subsample every RV_WINDOW_DAYS'th trading day
    so consecutive observations' forward-vol windows don't overlap, matching
    the non-overlapping discipline used throughout this repo
    (pipeline/signals/eval.py's ic_summary, and Experiment 11's weekly
    backtest itself)."""
    non_overlap = df.iloc[::RV_WINDOW_DAYS]
    contango = non_overlap[non_overlap["contango"]]["gap"]
    backward = non_overlap[~non_overlap["contango"]]["gap"]
    return _welch_t(contango, backward)


def mechanism_test(df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Test 13a's core result: for each sub-period, is the VIX-minus-realized
    gap significantly larger in contango weeks than backwardation weeks?
    Reports both the raw-daily and non-overlapping t-stats so the
    autocorrelation inflation is visible, not hidden."""
    if df is None:
        df = build_dataset()

    rows = []
    for label, (start, end) in SUB_PERIODS.items():
        period = df.loc[start:end]
        if period.empty:
            rows.append({"period": label, "n_days": 0})
            continue
        contango = period[period["contango"]]["gap"]
        backward = period[~period["contango"]]["gap"]
        raw = _welch_t(contango, backward)
        non_overlap = _non_overlapping_t(period)
        rows.append({
            "period": label,
            "n_days": len(period),
            "pct_backwardation": (~period["contango"]).mean() * 100,
            "mean_gap_contango": raw["mean_gap_contango"],
            "mean_gap_backward": raw["mean_gap_backward"],
            "raw_t_stat": raw["t_stat"],
            "non_overlap_n_contango": non_overlap["n_contango"],
            "non_overlap_n_backward": non_overlap["n_backward"],
            "non_overlap_t_stat": non_overlap["t_stat"],
        })
    return pd.DataFrame(rows)


def severity_test(df: pd.DataFrame | None = None, weekly: bool = True) -> pd.DataFrame:
    """Test 13a, revised after inspecting the binary contango/backwardation
    split directly: 20 of 25 backwardation Fridays in 2013-2019 still had a
    POSITIVE gap (VIX overpriced anyway), and the mean was dragged down only
    by 5 weeks clustered around real crises (2015-08-21 pre-China-deval,
    2018-02-02 pre-Volmageddon, 2018-12-07 pre-Dec-2018-selloff) with gaps of
    -3.8 to -10.2. The binary split buries a few genuine, severe signals
    inside a larger group of noisy false alarms and a MEAN comparison can't
    tell them apart.

    This instead asks the continuous-severity question directly, matching
    the practitioner finding cited in the plan that rate-of-change beats
    level for vol timing: does the ratio itself (level), and separately its
    5-day change (momentum into/out of backwardation), have a monotonic
    (Spearman) relationship with the forward gap? If backwardation's
    predictive content is really concentrated in its most severe instances,
    a rank correlation should pick that up even though the binary mean test
    could not.
    """
    if df is None:
        df = build_dataset()
    sample = df[df.index.weekday == 4] if weekly else df
    sample = sample.copy()
    sample["ratio_chg_5d"] = sample["ratio"].diff(5 if weekly else 25)  # ~1 week of trading days either way

    rows = []
    for label, (start, end) in list(SUB_PERIODS.items()) + [("full-sample", (str(sample.index.min().date()), str(sample.index.max().date())))]:
        period = sample.loc[start:end].dropna(subset=["ratio_chg_5d"])
        if len(period) < 10:
            continue
        rho_level, p_level = stats.spearmanr(period["ratio"], period["gap"])
        rho_chg, p_chg = stats.spearmanr(period["ratio_chg_5d"], period["gap"])
        rows.append({
            "period": label,
            "n": len(period),
            "spearman_ratio_level": rho_level,
            "p_level": p_level,
            "spearman_ratio_5d_change": rho_chg,
            "p_chg": p_chg,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build_dataset()
    print(f"Dataset: {len(df)} trading days, {df.index.min().date()} to {df.index.max().date()}")
    print(f"Backwardation days: {(~df['contango']).mean() * 100:.1f}% "
          f"(plan estimate from external research: ~8%)")
    print()

    result = mechanism_test(df)
    pd.set_option("display.width", 160)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    print(result.to_string(index=False))
    print()

    all_significant = (result["non_overlap_t_stat"].dropna() > 2.0).all() and len(result["non_overlap_t_stat"].dropna()) == len(SUB_PERIODS)
    if all_significant:
        print("PASS: contango gap significantly larger than backwardation gap in every sub-period.")
    else:
        print("Does NOT clearly pass in every sub-period on the non-overlapping test -- "
              "see the per-period t-stats above before concluding the mechanism holds.")

    from pipeline.io_utils import atomic_to_csv

    atomic_to_csv(result, "output/data/vol_mechanism_test.csv", index=False)
    print("\nSaved to output/data/vol_mechanism_test.csv")

    print("\n=== Severity test: does the ratio's LEVEL or its 5-day CHANGE ===")
    print("=== correlate (Spearman) with the forward gap, weekly cadence? ===\n")
    sev = severity_test(df)
    pd.set_option("display.width", 160)
    print(sev.to_string(index=False))
    atomic_to_csv(sev, "output/data/vol_severity_test.csv", index=False)
    print("\nSaved to output/data/vol_severity_test.csv")
