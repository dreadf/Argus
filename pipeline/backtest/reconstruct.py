"""
W3: reconstruct 3%/$5 put-credit-spread fees back to 2016 using CBOE's
VIX9D (9-day implied vol, the closest published instrument to this
strategy's 7-11 DTE tenor), so the strategy's one genuinely catastrophic
year -- 2018 -- becomes testable at all. Real option prices only go back
to Feb 2024 (Alpaca's expired-contract history), so the fee side before
that has to be modelled; the loss side never does, since it only needs
real SPY closes (available back to 2016 via fetch_spy_history.py).

THE VALIDATION GATE is the point of this file, not a formality. A first
attempt at this reconstruction (trailing realized volatility as the vol
input) had an aggregate correlation of 0.649 against real 2024-2026
credits, which looks acceptable reported as one number -- split by
volatility regime it priced calm weeks at 3% of reality and volatile
weeks at 125% of it, two opposite-signed errors that cancelled into a
falsely respectable average and produced a completely wrong finding
("a guard is destroying 66% of profit") that had to be retracted. This
file's calibrate_skew_multiplier + validate_reconstruction pair exists
specifically so that error class can never pass silently again: the
model is fit once, then checked PER VOLATILITY QUARTILE, and the module
refuses to produce a replay at all if any quartile drifts outside a
tight band.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pipeline.data.vix import contango_ratio, load_cached_vix
from pipeline.io_utils import atomic_to_csv, coerce_win_column

RAW_RESULTS_PATH = "output/data/spread_backtest_results.csv"
SPY_LONG_PATH = "output/data/raw_SPY_long.csv"
OUTPUT_PATH = "output/data/reconstruction_2016_2026.csv"

VALIDATION_QUARTILES = 4
VALIDATION_BAND = (0.95, 1.05)  # model/real ratio must fall inside this per quartile, or the module refuses to proceed

# Grid search range for the level-dependent skew multiplier k(vol) = a + b*vol.
_A_GRID = np.arange(0.80, 1.61, 0.01)
_B_GRID = np.arange(-3.00, 0.51, 0.05)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_put(spot: float, strike: float, tau_years: float, sigma: float, r: float = 0.04) -> float:
    """Black-Scholes European put. tau_years<=0 or sigma<=0 returns
    intrinsic value rather than raising -- both happen legitimately at
    the edges of a real chain (an expiry-day quote, a zero-IV print)."""
    if tau_years <= 0 or sigma <= 0:
        return max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * tau_years) / (sigma * math.sqrt(tau_years))
    d2 = d1 - sigma * math.sqrt(tau_years)
    return strike * math.exp(-r * tau_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _spread_credit(row, a: float, b: float, vix9d_col: str = "v9") -> float:
    k = a + b * row[vix9d_col]
    sigma = k * row[vix9d_col]
    return bs_put(row.spot_entry, row.short_strike, row.tau, sigma) - bs_put(row.spot_entry, row.long_strike, row.tau, sigma)


def _load_real_flagship_weeks(distance: float = 0.03, width: float = 5.0) -> pd.DataFrame:
    """The 126 real weeks (Feb 2024-2026) at the cell the evidence gate
    actually trades, joined to VIX9D at entry. This is both what the
    skew multiplier is fit against and what the validation gate checks
    the fit against -- same weeks, two different uses."""
    results = coerce_win_column(pd.read_csv(RAW_RESULTS_PATH))
    d = results[(~results.missing_data) & (results.distance == distance) & (results.width == width)].copy()
    d["entry"] = pd.to_datetime(d.entry)
    d["expiry"] = pd.to_datetime(d.expiry)
    v9 = load_cached_vix("VIX9D") / 100.0
    d = d.merge(v9.rename("v9"), left_on="entry", right_index=True, how="left").dropna(subset=["v9"])
    d["tau"] = (d.expiry - d.entry).dt.days / 365.0
    return d.reset_index(drop=True)


def calibrate_skew_multiplier(real_weeks: pd.DataFrame) -> tuple[float, float]:
    """Grid search for k(vol) = a + b*vol minimizing squared error against
    real credits. A level-dependent (not constant) multiplier is what
    fixes the regime-split failure described in the module docstring: a
    single constant k averages away exactly the bias the validation gate
    below is built to catch."""
    best = None
    for a in _A_GRID:
        for b in _B_GRID:
            modelled = real_weeks.apply(lambda r: _spread_credit(r, a, b), axis=1)
            err = float(((modelled - real_weeks.credit) ** 2).sum())
            if best is None or err < best[0]:
                best = (err, a, b)
    _, a, b = best
    return a, b


def validate_reconstruction(real_weeks: pd.DataFrame, a: float, b: float) -> pd.DataFrame:
    """THE GATE. Splits real_weeks into VALIDATION_QUARTILES volatility
    buckets, computes the model/real credit ratio in each, and raises if
    any bucket falls outside VALIDATION_BAND. Returns the per-bucket
    report for logging even on success, so a passing run still shows its
    work rather than a bare boolean."""
    d = real_weeks.copy()
    d["modelled"] = d.apply(lambda r: _spread_credit(r, a, b), axis=1)
    d["bucket"] = pd.qcut(d.v9, VALIDATION_QUARTILES, labels=[f"q{i+1}" for i in range(VALIDATION_QUARTILES)])
    report = d.groupby("bucket", observed=True).apply(
        lambda c: pd.Series({
            "n": len(c), "vix9d_mean": c.v9.mean(),
            "real_credit": c.credit.mean(), "model_credit": c.modelled.mean(),
            "model_over_real": c.modelled.mean() / c.credit.mean() if c.credit.mean() else np.nan,
        }),
        include_groups=False,
    )
    lo, hi = VALIDATION_BAND
    failures = report[(report.model_over_real < lo) | (report.model_over_real > hi)]
    if not failures.empty:
        raise RuntimeError(
            f"Reconstruction validation FAILED: {len(failures)} of {VALIDATION_QUARTILES} volatility "
            f"quartiles fall outside the [{lo}, {hi}] model/real ratio band:\n{failures.to_string()}\n"
            f"This is the exact failure mode that produced a false finding earlier in this project "
            f"(see module docstring) -- refusing to produce a replay from a model that doesn't pass this check, "
            f"rather than silently reporting an aggregate correlation that could hide the same bias again."
        )
    return report


def replay(a: float, b: float, distance: float = 0.03, width: float = 5.0,
           start: str = "2016-01-01", end: str | None = None) -> pd.DataFrame:
    """Weekly (Friday-to-Friday, non-overlapping) replay of the spread
    from `start` to `end` (default: latest cached data), using real SPY
    closes throughout and the validated k(vol) model only for the fee.
    Every loss in the output is real; only the credit column is modelled
    before Feb 2024."""
    spy = pd.read_csv(SPY_LONG_PATH, parse_dates=["date"]).set_index("date")["close"].sort_index()
    v9 = load_cached_vix("VIX9D") / 100.0
    v3m = load_cached_vix("VIX3M") / 100.0
    if end is not None:
        spy = spy.loc[:end]

    fridays = [d for d in spy.index if d.weekday() == 4]
    rows = []
    for entry in fridays:
        if entry < pd.Timestamp(start):
            continue
        later = [d for d in spy.index if entry < d <= entry + pd.Timedelta(days=7)]
        if not later or entry not in v9.index or entry not in v3m.index:
            continue
        expiry = max(later)
        spot = float(spy.loc[entry])
        sigma_input = float(v9.loc[entry])
        tau = (expiry - entry).days / 365.0
        short_k = math.floor(spot * (1 - distance) / 5) * 5  # matches T0's live $5-increment rule
        long_k = short_k - width
        k = a + b * sigma_input
        sigma = k * sigma_input
        credit = bs_put(spot, short_k, tau, sigma) - bs_put(spot, long_k, tau, sigma)
        payout = max(0.0, short_k - float(spy.loc[expiry])) - max(0.0, long_k - float(spy.loc[expiry]))
        rows.append({
            "entry": entry, "expiry": expiry, "year": entry.year,
            "spot_entry": spot, "vix9d": sigma_input, "vix3m": float(v3m.loc[entry]),
            "contango": float(v3m.loc[entry]) / sigma_input,
            "short_strike": short_k, "long_strike": long_k,
            "credit": credit, "payout": payout, "pnl": credit - payout,
            "win": payout <= 1e-9,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print("Loading the 126 real (2024-2026) weeks at 3%/$5 to calibrate against...")
    real_weeks = _load_real_flagship_weeks()
    print(f"  {len(real_weeks)} weeks loaded")

    print("\nFitting k(vol) = a + b*VIX9D by grid search...")
    a, b = calibrate_skew_multiplier(real_weeks)
    print(f"  fitted: k(vol) = {a:.2f} + {b:.2f}*VIX9D")

    print(f"\nVALIDATING: model/real credit ratio must fall in {VALIDATION_BAND} in every volatility quartile...")
    report = validate_reconstruction(real_weeks, a, b)
    print(report.round(4).to_string())
    print("Validation PASSED -- every quartile inside the band.")

    print("\nReplaying 2016-2026 at 3%/$5...")
    result = replay(a, b)
    print(f"  {len(result)} weeks, {result.entry.min().date()} to {result.entry.max().date()}")

    by_year = result.groupby("year").agg(weeks=("pnl", "size"), win_rate=("win", "mean"), total_pnl=("pnl", "sum"))
    print(by_year.round(3).to_string())

    # Self-checks: reproduce the headline figures under THIS module's own
    # strike rule (T0's $5-increment rounding, matching what the live
    # system actually trades). An earlier scratch version of this
    # reconstruction used the OLD $1-increment rule and got total=+38.28,
    # 2018=-16.40 -- confirmed (isolated in a side-by-side comparison)
    # that difference is caused entirely by the strike rule, not a bug:
    # rounding to $5 moves the short strike further from spot on every
    # week where the raw target wasn't already a multiple of 5, which
    # trims premium collected everywhere and reduces realized losses in
    # most (not all -- 2020 gets WORSE, see EXPERIMENT.md) years. The
    # scratch numbers described a strategy variant that no longer exists
    # once T0 shipped; these are the correct ones for what's actually live.
    total_pnl = result.pnl.sum()
    pnl_2018 = result.loc[result.year == 2018, "pnl"].sum()
    print(f"\nSelf-check: full-period total P&L = {total_pnl:+.2f} (expect roughly +24, tolerance +-3)")
    assert 21 <= total_pnl <= 27, f"full-period total {total_pnl:.2f} drifted further than expected from the known +24.03"
    print(f"Self-check: 2018 total P&L = {pnl_2018:+.2f} (expect roughly -9.9, tolerance +-2)")
    assert -11.9 <= pnl_2018 <= -7.9, f"2018 total {pnl_2018:.2f} drifted further than expected from the known -9.89"
    print("Both headline figures reproduced within tolerance -- PASS")

    atomic_to_csv(result, OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")
