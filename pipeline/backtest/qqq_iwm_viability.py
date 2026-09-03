"""
W5, first step: a cheap premium-per-breach-risk proxy for QQQ and IWM,
computed before paying for the expensive work (a live option-chain fetch
to discover real strike increments, plus a full historical option-price
reconstruction/backtest). If this proxy shows QQQ/IWM meaningfully worse
than SPY at the same (distance, width, tenor), "no cell survives" is a
real, legitimate answer and the expensive work doesn't need to happen --
this session's plan says so explicitly.

WHAT THE PROXY IS, stated plainly since nothing this specific existed
before this file: for each symbol, at the strategy's real traded shape
(3% OTM distance, $5 wide, 7 calendar days to expiry), for every trading
day with enough trailing history --

  1. price the spread's fee under Black-Scholes using that day's trailing
     20-day REALIZED volatility as the sigma input (reconstruct.py's
     bs_put/spread_value -- same closed form the reconstruction itself
     uses, only the vol input differs). This is a lower-bound proxy for
     what the fee would actually be: real implied vol typically sits
     above realized (the volatility risk premium this whole project is
     selling), so realized-vol pricing UNDERSTATES the premium a real
     chain would show, in the same direction for all three symbols.
  2. price the breach probability -- P(SPY-shaped weekly move exceeds
     3%) -- via pipeline.vol.skew_breach.empirical_breach_prob(), reusing
     SPY's own real 1993-2026 STANDARDIZED return shape (skew, fat
     tails) at that day's realized-vol LEVEL. This assumes the shape of
     a crash (not just its size) is similar across broad equity index
     ETFs -- a real, stated approximation, not a fact, and the reason
     this is a GATING proxy rather than the final answer: QQQ is
     tech-concentrated and IWM is small-cap, and either could plausibly
     have fatter or thinner tails than SPY's own history.

  proxy = mean(fee) / mean(breach_prob) -- average premium collected per
  unit of average breach risk, both terms in the same units the live
  system actually trades. Higher is more attractive.

Computed for SPY too, on the same method, as the reference point every
comparison is actually against -- there is no pre-existing "SPY = X" this
project has published under this exact definition, so this file
establishes it fresh rather than asserting a number that was never
computed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.backtest.reconstruct import _realized_vol_series, spread_value
from pipeline.vol.skew_breach import build_standardized_return_distribution, empirical_breach_prob

DISTANCE = 0.03
WIDTH = 5.0
TENOR_DAYS = 7          # calendar days to expiry, matching the live system's 7-11 DTE weekly trade
BREACH_HORIZON_DAYS = 5  # trading days, matching skew_breach.RETURN_HORIZON's weekly convention

LONG_HISTORY_PATHS = {
    "SPY": "output/data/raw_SPY_long.csv",
    "QQQ": "output/data/raw_QQQ_long.csv",
    "IWM": "output/data/raw_IWM_long.csv",
}


def _load_closes(path: str) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return df["close"]


def compute_viability_proxy(closes: pd.Series, standardized_returns: np.ndarray,
                             distance: float = DISTANCE, width: float = WIDTH,
                             tenor_days: int = TENOR_DAYS) -> dict:
    """One symbol's proxy, computed over every trading day with a valid
    trailing realized-vol estimate. Returns per-day series too (not just
    the mean) so a caller can check the distribution, not just one number
    -- this project's whole point is not trusting an aggregate that could
    be hiding a regime split (reconstruct.py's own module docstring)."""
    rv = _realized_vol_series(closes).dropna()
    spot = closes.reindex(rv.index)
    short_k = spot * (1 - distance)
    long_k = short_k - width
    tau_years = tenor_days / 365

    fees = pd.Series(
        [spread_value(s, sk, lk, tau_years, sigma) for s, sk, lk, sigma in zip(spot, short_k, long_k, rv)],
        index=rv.index,
    )

    sigma_pct = (rv * 100).to_numpy()
    breach_probs = pd.Series(
        [empirical_breach_prob(standardized_returns, sp, distance, BREACH_HORIZON_DAYS) for sp in sigma_pct],
        index=rv.index,
    )

    mean_fee = float(fees.mean())
    mean_breach = float(breach_probs.mean())
    return {
        "n_days": len(rv),
        "mean_fee": mean_fee,
        "mean_breach_prob": mean_breach,
        "mean_realized_vol": float(rv.mean()),
        "proxy": mean_fee / mean_breach if mean_breach > 0 else float("inf"),
        "fees": fees,
        "breach_probs": breach_probs,
    }


def run_all() -> dict[str, dict]:
    standardized_returns = build_standardized_return_distribution()
    return {
        symbol: compute_viability_proxy(_load_closes(path), standardized_returns)
        for symbol, path in LONG_HISTORY_PATHS.items()
    }


if __name__ == "__main__":
    print(f"Cheap premium-per-breach-risk proxy: {DISTANCE:.0%} OTM, ${WIDTH:.0f} wide, {TENOR_DAYS}d tenor, "
          f"Black-Scholes fee at trailing 20d realized vol, breach prob via SPY's real empirical shape.\n")
    results = run_all()
    for symbol, r in results.items():
        print(f"{symbol}: n={r['n_days']} days, mean realized vol={r['mean_realized_vol']:.1%}, "
              f"mean fee=${r['mean_fee']:.3f}, mean breach prob={r['mean_breach_prob']:.4f}, "
              f"proxy={r['proxy']:.3f}")

    spy_proxy = results["SPY"]["proxy"]
    print(f"\nRelative to SPY (proxy={spy_proxy:.3f}):")
    for symbol in ("QQQ", "IWM"):
        ratio = results[symbol]["proxy"] / spy_proxy
        print(f"  {symbol}: {ratio:.2f}x SPY's proxy "
              f"({'comparable or better -- worth the expensive work' if ratio >= 0.9 else 'meaningfully worse -- gate closed here'})")
