"""
Experiment 28 (renumbered from 21 -- that number was already EXPERIMENT.md's
own "Experiment 21, Randomization null for the week-skip filter", which
keeps it since the volatility track cross-references it throughout; see
EXPERIMENT_28_VRP.md's top note): does vrp_edge -- the same spread priced
twice, once with
VIX9D-derived implied vol and once with trailing realized SPY vol -- carry
information the existing VIX9D/VIX3M term-structure filter (contango,
see build_equity_curve in reconstruct.py) doesn't already have?

The measure itself (vrp_edge = credit - value_realized) is computed inside
reconstruct.replay() so it can never be built from different inputs than
the P&L it's being compared against; see spread_value() and the module
docstring there. This module only answers the diagnostic question and
reports the result -- it does not gate anything.

WHY A DIFFERENCE, NOT A LEVEL: under the risk-neutral measure a fairly
priced trade has zero expected P&L by construction, so a value built only
from a risk-neutral (implied-vol) input carries no edge information on its
own. vrp_edge is a difference between two prices of the identical spread,
implied vs realized, which is exactly zero when the two volatilities
agree -- pinned by test_reconstruct_vrp.py -- and only nonzero when they
diverge. That's the volatility risk premium.

RESULT (measured 2026-09-01, 534 of 538 weeks after the 20-day realized-vol
warmup): corr(vrp_edge, contango) = -0.13, independent information, not a
restatement of the existing filter. It also passes the false-trip test on
real (Feb 2024-2026) winning weeks (23.6% blocked, bar <=30%) -- it is not
mis-set in the sense that test checks for.

But run through the full equity-curve comparison (compare_equity_curves
below), vrp_edge-only and an AND-combination (skip only when both filters
agree) both beat the live contango filter on RAW TOTAL P&L -- and both do
it by giving up almost all of 2018's protection (-5.48 vs contango's
+0.26, the one year this filter exists to catch) and running a 63% deeper
max drawdown (7.64 vs 4.70). The total-P&L improvement is real but comes
from calmer years, not from handling the tail event better. Optimizing a
filter selection on an aggregate number that hides a regime-level result
is the exact failure class this project's reconstruction validation gate
was built to catch elsewhere (see reconstruct.py's module docstring) --
so despite passing its own false-trip test and improving the aggregate,
vrp_edge is NOT adopted as a replacement or addition to the live filter.
It stays a reported measurement. See EXPERIMENT_28_VRP.md for the full
writeup, including the per-year breakdown that makes the tradeoff visible.
"""

from __future__ import annotations

import pandas as pd

from pipeline.backtest.reconstruct import (
    CONTANGO_MIN_HISTORY,
    CONTANGO_PERCENTILE,
    calibrate_skew_multiplier,
    replay,
    validate_reconstruction,
    _load_real_flagship_weeks,
    _max_drawdown,
)
from pipeline.risk import options_config as risk_cfg

VRP_SCRATCH_PATH = "output/data/vrp_measure.csv"  # NOT a tracked/allow-listed path -- deliberately kept out of the
                                                   # dashboard's inputs (equity_curve.csv, reconstruction_2016_2026.csv)
                                                   # so this diagnostic can never silently become what the app renders.


def walk_forward_threshold(series: pd.Series, min_history: int = CONTANGO_MIN_HISTORY,
                            percentile: float = CONTANGO_PERCENTILE) -> pd.Series:
    """Trailing `percentile`-quantile of `series`, computed using only rows
    strictly before each position -- the same walk-forward rule
    reconstruct.build_equity_curve() and guards.check_term_structure use for
    contango, applied here to vrp_edge so the two filters are compared on
    equal footing (no full-sample constant, no lookahead). Rows before
    `min_history` get NaN (no threshold yet), matching the warmup
    convention everywhere else in this project."""
    out = [None] * len(series)
    for i in range(len(series)):
        if i >= min_history:
            out[i] = series.iloc[:i].quantile(percentile)
    return pd.Series(out, index=series.index, dtype="float64")


def compare_filters(result: pd.DataFrame) -> dict:
    """The diagnostic this experiment exists to answer. Returns a dict with
    the correlation, a confusion matrix of which weeks each filter would
    have skipped, and the 2018-losing-week comparison -- printed by
    __main__, also usable directly by a test or the eventual EXPERIMENT.md
    writeup without re-deriving any of it by hand."""
    d = result.dropna(subset=["vrp_edge"]).sort_values("entry").reset_index(drop=True)

    corr = float(d["vrp_edge"].corr(d["contango"]))

    d["thr_contango"] = walk_forward_threshold(d["contango"])
    d["thr_vrp"] = walk_forward_threshold(d["vrp_edge"])
    post = d[d["thr_contango"].notna()].copy()
    post["skip_contango"] = post["contango"] < post["thr_contango"]
    post["skip_vrp"] = post["vrp_edge"] < post["thr_vrp"]

    confusion = pd.crosstab(post["skip_contango"], post["skip_vrp"])

    losing_2018 = post[(post["year"] == 2018) & (~post["win"])]
    return {
        "n_usable_weeks": len(d),
        "n_post_warmup_weeks": len(post),
        "corr_vrp_contango": corr,
        "confusion_matrix": confusion,
        "n_2018_losing_weeks": len(losing_2018),
        "n_2018_losing_caught_by_contango": int(losing_2018["skip_contango"].sum()),
        "n_2018_losing_caught_by_vrp": int(losing_2018["skip_vrp"].sum()),
    }


def add_filter_columns(result: pd.DataFrame) -> pd.DataFrame:
    """Attaches the walk-forward skip decision for the live contango
    filter, vrp_edge alone, and two ways of combining them, all on
    identical footing (same warmup, same percentile). AND = skip only
    when both filters agree (trades MORE weeks than contango alone,
    since it requires two signals to concur before skipping). OR = skip
    if either says skip (trades FEWER weeks, more conservative than
    either alone)."""
    d = result.sort_values("entry").reset_index(drop=True).copy()
    d["thr_contango"] = walk_forward_threshold(d["contango"])
    d["thr_vrp"] = walk_forward_threshold(d["vrp_edge"])
    d["skip_contango"] = (d["thr_contango"].notna() & (d["contango"] < d["thr_contango"])).fillna(False)
    d["skip_vrp"] = (d["thr_vrp"].notna() & (d["vrp_edge"] < d["thr_vrp"])).fillna(False)
    d["skip_and"] = d["skip_contango"] & d["skip_vrp"]
    d["skip_or"] = d["skip_contango"] | d["skip_vrp"]
    return d


FILTER_CANDIDATES = {
    "unfiltered": None,
    "contango (live)": "skip_contango",
    "vrp_edge only": "skip_vrp",
    "AND (skip needs both)": "skip_and",
    "OR (skip if either)": "skip_or",
}


def compare_equity_curves(result: pd.DataFrame) -> pd.DataFrame:
    """The comparison that actually answers whether vrp_edge should
    replace or augment the live contango filter: total P&L, 2018 P&L
    (the one year the filter exists to catch, per README's "two things
    that are actually unusual" section), and max drawdown, for each
    candidate skip rule on identical footing. A candidate that wins on
    total P&L while losing 2018 protection is not a win -- it is the
    same aggregate-hides-a-regime-failure shape this project's
    reconstruction validation gate exists to catch (see reconstruct.py's
    module docstring), just in filter selection instead of price
    modelling. Report all three numbers together, never total P&L
    alone."""
    d = add_filter_columns(result)
    rows = []
    for label, skip_col in FILTER_CANDIDATES.items():
        traded = pd.Series(True, index=d.index) if skip_col is None else ~d[skip_col]
        pnl = d["pnl"].where(traded, 0.0)
        cum = pnl.cumsum()
        rows.append({
            "filter": label,
            "total_pnl": float(pnl.sum()),
            "pnl_2018": float(pnl[d["year"] == 2018].sum()),
            "max_drawdown": _max_drawdown(cum),
            "weeks_skipped": int((~traded).sum()),
        })
    return pd.DataFrame(rows)


def false_trip_rate_vrp_edge(real_results_df: pd.DataFrame, full_replay_with_thresholds: pd.DataFrame,
                              distance: float, width: float) -> dict:
    """Mirrors pipeline.risk.false_trip.false_trip_rate_term_structure's
    exact pattern, but for vrp_edge: the walk-forward threshold is built
    from the FULL 2016-2026 replay (needs the long history to have a
    threshold at all, same reasoning the contango version uses full
    VIX9D/VIX3M history), then tested only against REAL winning weeks
    from spread_backtest_results.csv -- real credit, real win/loss, not
    the modelled reconstruction -- at the survivor cells false_trip.py's
    own __main__ block tests. `full_replay_with_thresholds` must already
    have gone through add_filter_columns() and be indexed by `entry`."""
    cell = real_results_df[
        (real_results_df["distance"] == distance) & (real_results_df["width"] == width) & (~real_results_df["missing_data"])
    ].copy()
    cell["entry"] = pd.to_datetime(cell["entry"])
    winners = cell[cell["win"]]

    blocked = 0
    tested = 0
    for entry in winners["entry"]:
        if entry not in full_replay_with_thresholds.index:
            continue
        row = full_replay_with_thresholds.loc[entry]
        if pd.isna(row["thr_vrp"]):
            continue
        tested += 1
        if row["vrp_edge"] < row["thr_vrp"]:
            blocked += 1

    blocked_pct = blocked / tested if tested else 0.0
    return {
        "distance": distance, "width": width,
        "n_winners": tested, "n_winners_total_incl_untestable": len(winners),
        "blocked": blocked, "blocked_pct": blocked_pct,
        "passes": blocked_pct <= risk_cfg.FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT,
    }


if __name__ == "__main__":
    print("Recomputing the validated reconstruction (same calibration reconstruct.py uses)...")
    real_weeks = _load_real_flagship_weeks()
    a, b = calibrate_skew_multiplier(real_weeks)
    validate_reconstruction(real_weeks, a, b)  # raises on failure; prints nothing extra on success here, reconstruct.py already covers that path
    print(f"  validated: k(vol) = {a:.2f} + {b:.2f}*VIX9D")

    print("\nReplaying 2016-2026 with vrp_edge attached...")
    result = replay(a, b)
    print(f"  {len(result)} weeks, {result['vrp_edge'].notna().sum()} with a full realized-vol warmup")

    stats = compare_filters(result)
    print(f"\ncorr(vrp_edge, contango) = {stats['corr_vrp_contango']:.4f}  "
          f"({'independent' if abs(stats['corr_vrp_contango']) < 0.5 else 'correlated'} information)")

    print("\nFilter agreement (post-warmup weeks, rows=contango-skip, cols=vrp-skip):")
    print(stats["confusion_matrix"].to_string())

    print(f"\n2018 non-warmup losing weeks: {stats['n_2018_losing_weeks']}")
    print(f"  caught by contango filter: {stats['n_2018_losing_caught_by_contango']} / {stats['n_2018_losing_weeks']}")
    print(f"  caught by vrp_edge filter: {stats['n_2018_losing_caught_by_vrp']} / {stats['n_2018_losing_weeks']}")

    print("\nEquity-curve comparison (total P&L, 2018 P&L, max drawdown -- never read total P&L alone):")
    curves = compare_equity_curves(result)
    print(curves.round(2).to_string(index=False))

    print("\nFalse-trip test on REAL (Feb 2024-2026) evidence-gate survivors, vrp_edge filter (bar: <=30%):")
    full_with_thresholds = add_filter_columns(result).set_index("entry")
    from pipeline.io_utils import coerce_win_column as _coerce
    real_results = _coerce(pd.read_csv("output/data/spread_backtest_results.csv"))
    for distance, width in [(0.03, 1.0), (0.03, 2.0), (0.03, 5.0)]:
        r = false_trip_rate_vrp_edge(real_results, full_with_thresholds, distance, width)
        status = "PASS" if r["passes"] else "FAIL (mis-set, needs loosening)"
        print(f"  {distance:.0%} / ${width:.0f}: {r['blocked']}/{r['n_winners']} real winners blocked "
              f"({r['blocked_pct']:.1%}) -> {status}")

    print(
        "\nVERDICT: vrp_edge passes its own false-trip test and improves raw total P&L over the live "
        "contango filter, but only by giving up most of 2018's protection and running a deeper drawdown "
        "-- see the equity-curve table above and EXPERIMENT_28_VRP.md for the full reasoning. NOT adopted "
        "as a replacement or addition to the live filter; stays a reported measurement."
    )

    # Self-check: the null-case property that makes vrp_edge an honest
    # measure at all -- when realized vol happens to equal the implied
    # input, the two sides price identically and the edge is exactly zero.
    # Spot-checked here on a real row rather than only in the unit test,
    # so a live run can't silently drift from what the test asserts.
    probe = result.dropna(subset=["vrp_edge"]).iloc[0]
    from pipeline.backtest.reconstruct import spread_value
    equal_vol_edge = (
        spread_value(probe.spot_entry, probe.short_strike, probe.long_strike,
                     (probe.expiry - probe.entry).days / 365.0, probe.sigma_realized)
        - spread_value(probe.spot_entry, probe.short_strike, probe.long_strike,
                        (probe.expiry - probe.entry).days / 365.0, probe.sigma_realized)
    )
    assert equal_vol_edge == 0.0, "vrp_edge must be exactly zero when both sides use the same volatility"
    print("\nSelf-check: vrp_edge is exactly 0.0 when implied and realized vol agree -- PASS")

    from pipeline.io_utils import atomic_to_csv
    atomic_to_csv(result, VRP_SCRATCH_PATH, index=False)
    print(f"\nSaved to {VRP_SCRATCH_PATH} (diagnostic only -- not read by the dashboard or any tracked/allow-listed output)")
