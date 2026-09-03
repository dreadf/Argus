"""
The falsification gauntlet, extracted into a reusable engine (W4).

Previously the randomization-null logic was hand-written once per
hypothesis, across pipeline/vol/experiment21_randomization_null.py,
experiment23_tail_risk.py, experiment24_daily_overlay.py, and
pipeline/backtest/vrp_measure.py's own false_trip_rate_vrp_edge. That was
fine when a human wrote each hypothesis by hand. W3's propose.py needs this
as a callable function instead: an LLM proposing a new hypothesis every
iteration cannot each get a hand-written experiment file.

This module does not replace or edit any of those existing scripts (they
remain historical, already-published records of what was actually run and
found at the time -- pipeline/vol/ is also outside this session's claimed
territory). It generalizes the same method they all used by hand into a
function any new hypothesis can call.

Two hypothesis shapes are supported, matching the two kinds of claim this
project has actually tested end to end:

  - CROSS-SECTIONAL (pipeline/signals/eval.py's shape): "does this score
    rank symbols correctly" -- a [timestamp, symbol, score] DataFrame plus
    a [timestamp, symbol, fwd_5d_return] DataFrame. The ML track's shape.
  - SKIP-FILTER (pipeline/backtest/vrp_measure.py's shape): "does
    thresholding this signal, walk-forward, and skipping weeks below it,
    actually improve realized P&L." A date-indexed signal series plus a
    date-indexed realized P&L series. The options-filter track's shape.

A Hypothesis carries exactly one of the two shapes -- falsify() dispatches
on which fields are populated and raises if both or neither are, rather
than guessing.

The gauntlet, per shape (each stage can kill the hypothesis outright and
falsify() stops there rather than running the remaining stages):

  CROSS-SECTIONAL: information-coefficient t-stat (eval.py's ic_summary,
  the same bar Experiments 8/9/10/30 used for "statistically
  distinguishable from zero") -> randomization null (permute the score
  within each day, N times -- severs any real cross-sectional ranking
  information while leaving every marginal distribution untouched, same
  method as Experiment 21). No return series exists for this shape, so DSR
  does not apply and the gauntlet ends at the null.

  SKIP-FILTER: false-trip rate (only if a results_df of real per-week
  outcomes is supplied -- mirrors risk/false_trip.py's and
  vrp_measure.false_trip_rate_vrp_edge's exact method) -> randomization
  null (shuffle the signal across weeks, N times, exactly Experiment 21's
  method: shuffling only the signal severs any real timing relationship
  while leaving every marginal distribution untouched) -> Deflated Sharpe
  Ratio, at the project's current trial count (pipeline.falsify.trial_count
  .total_trial_count(), computed fresh, never hardcoded here -- same
  discipline audit.py's own headline_n uses), on the filtered P&L series.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.falsify.deflated_sharpe import deflated_sharpe_ratio
from pipeline.falsify.trial_count import total_trial_count
from pipeline.signals.eval import daily_ic, ic_summary

DEFAULT_N_PERMUTATIONS = 2000
DEFAULT_SEED = 42
IC_T_STAT_THRESHOLD = 2.0  # matches the bar Experiments 8/9/10/30 used for "statistically distinguishable from zero"
CONTANGO_MIN_HISTORY = 60  # matches reconstruct.py / guards.check_term_structure / vrp_measure's walk-forward warmup
CONTANGO_PERCENTILE = 0.33
DEFAULT_FALSE_TRIP_BAR = 0.30  # matches risk/options_config.py's FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT


@dataclass
class Hypothesis:
    name: str
    description: str = ""

    # Cross-sectional shape (signals/eval.py)
    scores: Optional[pd.DataFrame] = None       # columns: timestamp, symbol, score
    fwd_returns: Optional[pd.DataFrame] = None  # columns: timestamp, symbol, fwd_5d_return

    # Skip-filter shape (vrp_measure.py)
    signal: Optional[pd.Series] = None  # date-indexed candidate filter value
    pnl: Optional[pd.Series] = None     # date-indexed realized P&L, same index as `signal`
    results_df: Optional[pd.DataFrame] = None  # optional: real per-week outcomes for the false-trip stage
                                                # (columns: entry, distance, width, win, missing_data)
    distance: Optional[float] = None
    width: Optional[float] = None

    def shape(self) -> str:
        cross = self.scores is not None and self.fwd_returns is not None
        skip = self.signal is not None and self.pnl is not None
        if cross and skip:
            raise ValueError(f"Hypothesis {self.name!r} supplies both shapes; supply exactly one")
        if cross:
            return "cross_sectional"
        if skip:
            return "skip_filter"
        raise ValueError(f"Hypothesis {self.name!r} supplies neither shape (need scores+fwd_returns, or signal+pnl)")


@dataclass
class Verdict:
    hypothesis_name: str
    survived: bool
    killed_at: Optional[str]  # None if survived, else the stage name that killed it
    reason: str
    detail: dict = field(default_factory=dict)


def _walk_forward_threshold(series: pd.Series, min_history: int = CONTANGO_MIN_HISTORY,
                             percentile: float = CONTANGO_PERCENTILE) -> pd.Series:
    """Trailing `percentile`-quantile of `series`, using only rows strictly
    before each position -- identical rule to reconstruct.py's own
    build_equity_curve() and vrp_measure.walk_forward_threshold(). Not
    imported from vrp_measure.py directly to keep this module free of a
    dependency on pipeline/backtest/ internals it doesn't otherwise need;
    tested for equivalence in test_engine.py instead."""
    out = [None] * len(series)
    for i in range(len(series)):
        if i >= min_history:
            out[i] = series.iloc[:i].quantile(percentile)
    return pd.Series(out, index=series.index, dtype="float64")


def _skip_filter_total_pnl(signal: pd.Series, pnl: pd.Series, min_history: int, percentile: float) -> float:
    """Total P&L retained when weeks with `signal` below its own
    walk-forward threshold are skipped (set to 0 P&L) -- the same
    economically meaningful statistic vrp_measure.compare_equity_curves
    uses (total_pnl), not a mean, so the statistic isn't distorted by the
    skip rate itself changing across permutations."""
    thr = _walk_forward_threshold(signal, min_history, percentile)
    traded = thr.isna() | (signal >= thr)
    return float(pnl.where(traded, 0.0).sum())


def _randomization_null_cross_sectional(hyp: Hypothesis, real_t: float, rng: np.random.Generator,
                                         n_permutations: int) -> dict:
    dates = hyp.scores["timestamp"].unique()
    null_ts = []
    for _ in range(n_permutations):
        shuffled = hyp.scores.copy()
        for d in dates:
            mask = (shuffled["timestamp"] == d).values
            shuffled.loc[mask, "score"] = rng.permutation(shuffled.loc[mask, "score"].values)
        null_ts.append(ic_summary(daily_ic(shuffled, hyp.fwd_returns))["t_stat_non_overlap"])

    null_ts = np.array([t for t in null_ts if not np.isnan(t)])
    p_value = float((np.abs(null_ts) >= abs(real_t)).mean()) if len(null_ts) else float("nan")
    return {
        "real_t_stat": real_t,
        "null_mean": float(null_ts.mean()) if len(null_ts) else float("nan"),
        "null_std": float(null_ts.std()) if len(null_ts) else float("nan"),
        "p_value": p_value,
        "n_permutations": n_permutations,
    }


def _randomization_null_skip_filter(hyp: Hypothesis, rng: np.random.Generator, n_permutations: int,
                                     min_history: int, percentile: float) -> dict:
    real_stat = _skip_filter_total_pnl(hyp.signal, hyp.pnl, min_history, percentile)
    values = hyp.signal.values.copy()
    null_stats = np.empty(n_permutations)
    for i in range(n_permutations):
        shuffled = pd.Series(rng.permutation(values), index=hyp.signal.index)
        null_stats[i] = _skip_filter_total_pnl(shuffled, hyp.pnl, min_history, percentile)
    p_value = float((null_stats >= real_stat).mean())  # one-sided: does the real signal beat a random schedule of the same skip rate?
    return {
        "real_stat": real_stat,
        "null_mean": float(null_stats.mean()),
        "null_std": float(null_stats.std()),
        "p_value": p_value,
        "n_permutations": n_permutations,
    }


def _false_trip_rate(hyp: Hypothesis, min_history: int, percentile: float, bar: float) -> Optional[dict]:
    """Generalizes vrp_measure.false_trip_rate_vrp_edge to an arbitrary
    signal: among real, historically WINNING weeks at (hyp.distance,
    hyp.width), what fraction would this signal's walk-forward threshold
    have skipped? Returns None (stage not applicable) if hyp.results_df,
    hyp.distance, or hyp.width is missing -- not every hypothesis has a
    matched real-outcomes table to test against."""
    if hyp.results_df is None or hyp.distance is None or hyp.width is None:
        return None

    thr = _walk_forward_threshold(hyp.signal, min_history, percentile)
    entry_index = pd.to_datetime(hyp.signal.index)

    cell = hyp.results_df[
        (hyp.results_df["distance"] == hyp.distance)
        & (hyp.results_df["width"] == hyp.width)
        & (~hyp.results_df["missing_data"])
    ].copy()
    cell["entry"] = pd.to_datetime(cell["entry"])
    winners = cell[cell["win"]]

    blocked = 0
    tested = 0
    for entry in winners["entry"]:
        pos = entry_index.get_indexer([entry])[0]
        if pos == -1 or pd.isna(thr.iloc[pos]):
            continue
        tested += 1
        if hyp.signal.iloc[pos] < thr.iloc[pos]:
            blocked += 1

    blocked_pct = blocked / tested if tested else 0.0
    return {
        "n_winners_tested": tested,
        "n_winners_total": len(winners),
        "blocked": blocked,
        "blocked_pct": blocked_pct,
        "passes": blocked_pct <= bar,
    }


def falsify(hyp: Hypothesis, n_permutations: int = DEFAULT_N_PERMUTATIONS, seed: int = DEFAULT_SEED,
            min_history: int = CONTANGO_MIN_HISTORY, percentile: float = CONTANGO_PERCENTILE,
            false_trip_bar: float = DEFAULT_FALSE_TRIP_BAR, headline_n: Optional[int] = None) -> Verdict:
    """Runs `hyp` through the gauntlet appropriate to its shape and returns
    a Verdict. `headline_n` defaults to the project's live trial count
    (pipeline.falsify.trial_count.total_trial_count()) if not supplied --
    always computed fresh, per the same "never hardcode N" rule
    trial_count.py and audit.py enforce elsewhere."""
    rng = np.random.default_rng(seed)
    shape = hyp.shape()

    if shape == "cross_sectional":
        real_ic = daily_ic(hyp.scores, hyp.fwd_returns)
        real_summary = ic_summary(real_ic)
        real_t = real_summary["t_stat_non_overlap"]
        if np.isnan(real_t) or abs(real_t) < IC_T_STAT_THRESHOLD:
            return Verdict(hyp.name, survived=False, killed_at="ic_significance",
                            reason=f"IC t-stat ({real_t:.3f} or NaN) does not clear the parametric bar "
                                   f"of {IC_T_STAT_THRESHOLD} before even reaching the randomization null",
                            detail={"ic_summary": real_summary})

        null = _randomization_null_cross_sectional(hyp, real_t, rng, n_permutations)
        if null["p_value"] >= 0.05 or np.isnan(null["p_value"]):
            return Verdict(hyp.name, survived=False, killed_at="randomization_null",
                            reason=f"real IC t-stat ({null['real_t_stat']:.3f}) does not clear its own "
                                   f"randomization null (p={null['p_value']:.3f})",
                            detail={"randomization_null": null})
        return Verdict(hyp.name, survived=True, killed_at=None,
                        reason=f"IC t-stat {null['real_t_stat']:.3f} clears its randomization null "
                               f"(p={null['p_value']:.3f})",
                        detail={"randomization_null": null})

    # skip_filter shape
    false_trip = _false_trip_rate(hyp, min_history, percentile, false_trip_bar)
    if false_trip is not None and not false_trip["passes"]:
        return Verdict(hyp.name, survived=False, killed_at="false_trip",
                        reason=f"blocked {false_trip['blocked_pct']:.1%} of real winning weeks "
                               f"(bar {false_trip_bar:.0%})",
                        detail={"false_trip": false_trip})

    null = _randomization_null_skip_filter(hyp, rng, n_permutations, min_history, percentile)
    if null["p_value"] >= 0.05:
        return Verdict(hyp.name, survived=False, killed_at="randomization_null",
                        reason=f"filtered P&L ({null['real_stat']:.4f}) does not beat its own randomization "
                               f"null (p={null['p_value']:.3f})",
                        detail={"false_trip": false_trip, "randomization_null": null})

    thr = _walk_forward_threshold(hyp.signal, min_history, percentile)
    traded = thr.isna() | (hyp.signal >= thr)
    filtered_pnl = hyp.pnl.where(traded, 0.0)
    n_trials = headline_n if headline_n is not None else total_trial_count()
    dsr = deflated_sharpe_ratio(filtered_pnl, n_trials=n_trials)
    if dsr["dsr"] < 0.5:
        return Verdict(hyp.name, survived=False, killed_at="deflated_sharpe",
                        reason=f"DSR={dsr['dsr']:.4f} at N={n_trials} -- not distinguishable from the best "
                               f"of {n_trials} lucky tries",
                        detail={"false_trip": false_trip, "randomization_null": null, "dsr": dsr})

    return Verdict(hyp.name, survived=True, killed_at=None,
                    reason=f"clears false-trip, randomization null (p={null['p_value']:.3f}), and DSR "
                           f"({dsr['dsr']:.4f} at N={n_trials})",
                    detail={"false_trip": false_trip, "randomization_null": null, "dsr": dsr})
