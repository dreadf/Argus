# Experiment 28: does a directly-measured volatility risk premium beat the term-structure filter?

*(Renumbered from Experiment 21 to 28 -- that number was already taken in EXPERIMENT.md by
"Experiment 21 -- Randomization null for the week-skip filter," the volatility track's own
Experiment 21, which keeps its number since the track cross-references it throughout. This
file's original numbering collided with it; 28 is the next free number after the track's
Experiment 27.)*

**Status: folded into `EXPERIMENT.md` as "## Experiment 28"** (2026-09-03), which now
carries the same content in that file's numbered log. This file remains the full
standalone writeup (the year-by-year P&L table and interpretation in more detail);
`EXPERIMENT.md` cross-references it rather than duplicating everything here. See the
module docstring atop `pipeline/backtest/vrp_measure.py` for the code-level version of
this writeup.

## Hypothesis

The existing edge, reported since Experiment 12/W4, comes from a VIX curve
(VIX9D/VIX3M contango) threshold: skip a week when the curve flattens or inverts,
because that is when the market expects more turbulence soon than later. That
threshold was fitted -- its 33rd-percentile cutoff was calibrated on the calmest
stretch on record (2016-2017) -- which is a real, disclosed weakness (see README's
"two caveats" section).

A more direct way to state "the market is overpaying for this spread" is to price
the identical spread twice, once with the implied-vol input this system already
uses (VIX9D, skew-adjusted) and once with trailing realized SPY volatility, and
take the difference. Call it `vrp_edge`. It is zero by construction when the two
volatilities agree, and only departs from zero when they diverge -- which is what a
volatility risk premium actually is. If it's a genuinely different signal from
contango, and a better one on the case that matters (2018), it's worth adding.

## Method

`pipeline/backtest/reconstruct.py`'s `replay()` already computes `credit` from
`spread_value(spot, short_k, long_k, tau, sigma)` with `sigma` derived from
VIX9D through the module's validated `k(vol)` skew adjustment. Adding the second
side meant computing `value_realized = spread_value(...)` with `sigma` from a
20-day trailing annualized realized-vol series on SPY closes instead
(`_realized_vol_series`, matching `pipeline/options/vol.py`'s own formula --
log returns, `ddof=1`, `sqrt(252)` annualization -- reimplemented locally rather
than imported, since that module constructs a live Alpaca client at import time
and would have made this module require an API key just to import).
`vrp_edge = credit - value_realized`.

Both filters were then compared on identical footing: the same walk-forward rule
(`walk_forward_threshold` in `vrp_measure.py`, mirroring
`reconstruct.build_equity_curve`'s own contango mask) applied to `vrp_edge`,
with the same 60-week warmup and 33rd-percentile cutoff the live contango filter
uses.

**No lookahead:** the realized-vol series is trailing by construction
(`pandas.rolling`), and `test_realized_vol_series_no_lookahead` in
`tests/test_reconstruct_vrp.py` pins that appending future rows never changes an
already-computed value.

**Sign convention:** this system is a net seller. It collects `credit` (the
implied-vol price) and expects to owe the realized-vol price, so
`vrp_edge = credit - value_realized > 0` means the market is paying more for
this spread than recent realized volatility would justify -- pinned by
`test_vrp_edge_sign_convention`.

## Result

Measured 2026-09-01, on the same 538-week, 2016-2026 replay reconstruct.py already
validates (per-quartile model/real ratio inside [0.95, 1.05], as documented in
that module). 534 of 538 weeks have a full 20-trading-day realized-vol lookback;
the first 4 weeks of the sample are warmup and correctly NaN, not zero.

**`corr(vrp_edge, contango) = -0.13`.** Weak. `vrp_edge` is independent
information, not a restatement of the term-structure filter in dollar units --
the "confirmatory negative result, no new filter needed" outcome this experiment
was set up to detect did not happen.

**It also passes its own false-trip test.** Replayed against the real (Feb
2024-2026) evidence-gate survivor cells -- (3%,$1), (3%,$2), (3%,$5) -- using
the identical walk-forward-threshold, real-winners-only discipline
`pipeline/risk/false_trip.py`'s `false_trip_rate_term_structure` uses for
contango, `vrp_edge` blocks 23.6% of real winning weeks (29/123 at every
survivor cell -- the credit/width cell choice doesn't change which weeks get
blocked), comfortably under the 30% bar (`FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT`
in `pipeline/risk/options_config.py`). By that specific test, it is not
mis-set.

**So the natural next question -- since it's independent and not mis-set, does
combining it with contango actually do better? -- was tested directly, not left
as a hypothesis.** Four candidate skip rules, all on the same walk-forward
footing (60-week warmup, 33rd-percentile threshold), run through the full
538-week equity curve:

| filter | total P&L | 2018 P&L | max drawdown | weeks skipped |
|---|---|---|---|---|
| unfiltered | +24.03 | -9.89 | 18.65 | 0 |
| contango (live) | +19.45 | **+0.26** | **4.70** | 183 |
| vrp_edge only | **+27.66** | -5.48 | 7.95 | 137 |
| AND (skip needs both) | **+34.56** | -5.48 | 7.64 | 46 |
| OR (skip if either) | +12.55 | +0.26 | 5.36 | 274 |

`vrp_edge`-only and the AND-combination both beat the live filter on raw total
P&L, by a wide margin for AND. **That is not the finding it looks like.** Both
get there by giving up almost all of 2018's protection -- the live filter turns
2018 from a -9.89 loss into a +0.26 near-wash; both `vrp_edge`-based rules leave
it at -5.48, worse than doing nothing to over half the unfiltered loss -- and
both run a 63-70% deeper max drawdown than the live filter. The extra total P&L
comes from trading through calmer years the live filter currently sits out, not
from handling 2018 better. OR, the conservative combination, matches the live
filter's exact 2018/drawdown numbers but at a worse total P&L, i.e. it adds
nothing contango doesn't already do alone.

The year-by-year P&L makes the shape explicit (2016 is identical across all
three because it predates any filter's 60-week warmup):

| year | contango | vrp_edge only | AND |
|---|---|---|---|
| 2018 | **+0.26** | -5.48 | -5.48 |
| 2020 | +1.79 | -0.08 | +1.98 |
| 2021 | +4.53 | +7.13 | +8.74 |
| 2022 | -0.05 | -0.10 | +4.41 |
| 2024 | -1.67 | +5.24 | +1.70 |

2020 (the COVID crash) shows the same pattern as 2018 for `vrp_edge`-only
(-0.08, barely better than doing nothing), though the AND combination happens
to recover it (+1.98) -- inconsistent behavior across the two real crash-from-calm
years in the sample is itself a reason for caution, not reassurance.

## Interpretation

`vrp_edge` is a real, honestly-computed measurement -- the null-case property
holds exactly (zero when the two vols agree, pinned by test), the sign
convention is correct, it is not simply re-deriving what contango already
captures, and it is not mis-set by the project's own false-trip standard. All
of that is true, and none of it is enough.

**Decision: `vrp_edge` stays a reported measurement, not a gate, not a
replacement, not an addition.** This is not the "insufficient evidence, didn't
get to test it" outcome the first draft of this experiment reported -- it was
tested, at the level of total P&L, year-by-year P&L, drawdown, and a false-trip
check against real data, and the tested result is a genuine tradeoff, not a
clear win:

1. **Optimizing for total P&L here reproduces the exact failure shape this
   project already caught itself making once.** `reconstruct.py`'s own module
   docstring describes an earlier reconstruction that scored a respectable
   0.649 aggregate correlation while being wrong in opposite directions by
   volatility regime -- a confident, false finding that had to be retracted.
   Picking a filter because its aggregate total P&L is higher, while it quietly
   gives up protection on the two real crash-from-calm years in the sample, is
   the same mistake in a different part of the codebase: a good-looking average
   built on a regime-level failure.
2. **The whole point of the live filter, per README, is protecting against the
   tail, not maximizing return.** "This strategy is not designed to beat the
   market. It is sized so that it cannot blow up, and that same sizing is why
   it earns little." A filter change that trades tail protection for a better
   average return average is optimizing the opposite of what this system is
   for, even when the average genuinely improves.
3. **`credit`, `payout`, `pnl`, and `win`** -- every number this project's
   headline figures depend on -- remain bit-identical before and after this
   experiment (re-verified against the tracked `output/data/reconstruction_2016_2026.csv`
   after adding the equity-curve and false-trip comparison functions). Nothing
   about the existing, validated result changes because this measurement and
   this comparison now exist alongside it.

**What would change this decision:** not a better total-P&L number. Evidence
that a combination protects the tail *at least as well* as contango alone,
tested against a genuinely held-out crash-from-calm period this filter wasn't
built or compared against -- 2018 and 2020 have now both been looked at twice
(once to build contango, once here), so neither can serve as unbiased
out-of-sample evidence for a third filter. Absent a new tail event or a
pre-registered holdout, this line of investigation is exhausted for now.

**Not wired into the live agent.** `select_spread()` in `pipeline/options/selector.py`
is a pure function on plain dicts by design (no network calls inside the Picker);
computing a live `vrp_edge` would need a live realized-vol fetch
(`pipeline/options/vol.py`, which needs Alpaca credentials and a network call)
threaded through `run_agent.py`'s call site. Given the result above -- a
measurement that isn't gating anything -- that wiring wasn't done in this pass.
If a future pass logs it for visibility only (via `pipeline/audit/log.py`'s
`SCHEMA_FIELDS`, which is designed for exactly this kind of deliberate addition),
that's a small, low-risk follow-up.

## Fold-in status

Done (2026-09-03) -- see `EXPERIMENT.md`'s "## Experiment 28" section, inserted
after the Volatility Track's Final Synthesis. `pipeline/falsify/trial_count.py`'s
`EXPERIMENT_MD_BASE_COUNT` was updated from 30 to 31 in the same pass (grep now
counts this experiment directly) and its separate `EXPERIMENT_28_COUNT` constant
was removed rather than left stale -- the fold-in does not change the total trial
count N (still 31), only where Experiment 28 is counted from.
