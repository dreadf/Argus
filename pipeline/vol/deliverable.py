"""
Volatility track deliverable, per the plan's own definition: given a date,
return the forecasted volatility (HAR-X, Experiment 18 -- the one
unconditionally positive result of this track) plus an explicit, honest
verdict on whether it should be used to pick a strike.

This does NOT return an adaptive strike recommendation, a sizing rule, or a
skip filter as if any were a proven edge. Eight experiments
(15/19/20/21/22/23/24/26/27) tested that question from independent angles
-- a better forecaster, a fixed breach-probability conversion, a pure-noise
check, horizon-scaling, risk-adjusted strike selection, 4.5x more data,
inverse-vol position sizing, and a binary circuit-breaker -- and all eight
came back negative (see EXPERIMENT.md's "Volatility Track -- Final
Synthesis"). A function that quietly returned an adaptive pick anyway would
misrepresent a null result as a working signal.

What this DOES return: the forecasted annualized volatility for the coming
week (real, out-of-sample, DM-confirmed better than naive/EWMA/plain HAR),
for use as CONTEXT -- e.g. a risk-sizing input, matching Moreira & Muir
(2017)'s "volatility forecasts are for sizing, not timing" (see
SOURCES.md) -- plus the fixed 3%/$5 baseline cell this track's own Step 0
established as the cost-robust choice, since that is what the evidence
actually supports trading.
"""

from __future__ import annotations

from datetime import date as date_type

import pandas as pd

import numpy as np
import pandas as pd

from pipeline.vol.overlay import BASELINE_DISTANCE, BASELINE_WIDTH, build_weekly_forecasts
from pipeline.vol.skew_breach import build_standardized_return_distribution, empirical_breach_prob


def live_forecast(model: str = "harx") -> dict:
    """The CURRENT forecast, for live/display use: refit on ALL available
    history and projected one step past the last observed day.

    Why this exists separately from the walk-forward series below.
    `expanding_walk_forward` only emits predictions for COMPLETE test blocks
    (`start + test_block <= n`), so the final partial block never gets one --
    correct for honest scoring, since every scored block is then the same
    size, but it means the walk-forward series ends up to `test_block` days
    (63) behind the real data. Reading a live number off it showed a
    55-day-stale forecast on the dashboard.

    The distinction that matters, and it must not be blurred: the
    walk-forward series is what VALIDATES the model (Experiment 18's DM
    t=-3.22, p=0.0013, MCS -- every number in EXPERIMENT.md comes from it,
    fit only on data preceding each scored point). This function is what
    DEPLOYS it, and its output is deliberately not scored anywhere. There is
    still no lookahead: every input is an observed past value, and the
    prediction is for a day after all of them.
    """
    from pipeline.vol.experiment18_harx import load_log_rv, load_vix
    from pipeline.vol.har import HARModel, build_har_features, build_har_x_features

    log_rv = load_log_rv()
    if model == "harx":
        vix = load_vix()
        feats = build_har_x_features(log_rv, vix)
    elif model == "har":
        vix = None
        feats = build_har_features(log_rv)
    else:
        raise ValueError(f"unknown model {model!r}")

    fitted = HARModel("qlike").fit(feats, log_rv)

    # Feature row for the NEXT day: same construction as
    # build_har_*_features' shift(1), but evaluated one step past the data
    # end -- so the daily/weekly/monthly terms are the last 1/5/22 OBSERVED
    # days, and VIX is its own latest observed close.
    next_row = {
        "har_daily": log_rv.iloc[-1],
        "har_weekly": log_rv.iloc[-5:].mean(),
        "har_monthly": log_rv.iloc[-22:].mean(),
    }
    if model == "harx":
        vix_aligned = vix.reindex(log_rv.index).ffill()
        next_row["har_x_vix"] = float(np.log(vix_aligned.iloc[-1]))

    X_next = pd.DataFrame([next_row], columns=feats.columns)
    forecast_log_vol = float(fitted.predict(X_next).iloc[0])

    return {
        "forecast_vol_annualized_pct": float(np.exp(forecast_log_vol)),
        "data_through": log_rv.index[-1].date(),
        "n_train": int(len(feats.dropna())),
    }


def forecast_for_date(target_date: date_type, model: str = "harx") -> dict:
    """The WALK-FORWARD forecast available at or before target_date -- the
    validated series (Experiment 18), fit only on data preceding each point.
    Use this for backtesting and for reproducing any number in
    EXPERIMENT.md; use `live_forecast()` for a current, display-facing
    number, since this series necessarily lags the data by up to one test
    block (63 days). Raises if target_date precedes the forecaster's first
    out-of-sample prediction (min_train=500 days)."""
    forecast = build_weekly_forecasts(model=model)
    ts = pd.Timestamp(target_date)
    available = forecast.loc[:ts]
    if available.empty:
        raise ValueError(
            f"{target_date} is before the HAR-X forecaster's first out-of-sample prediction "
            f"({forecast.index.min().date()})"
        )
    return {
        "date": target_date,
        "forecast_vol_annualized_pct": float(available.iloc[-1]),
        "forecast_as_of": available.index[-1].date(),
    }


def decide(target_date: date_type, distance: float = BASELINE_DISTANCE, width: int = BASELINE_WIDTH,
           horizon_days: int = 7, live: bool = False) -> dict:
    """The plan's deliverable shape: trade/skip + recommended cell + the
    forecast that informed it. The recommendation is ALWAYS the fixed
    baseline cell (Step 0's cost-robust choice, 1.55 SE at $0.05/share) --
    this track never found a forecast-driven cell choice that beats it after
    correcting for the randomization null (EXPERIMENT.md, Experiments
    15-27). `forecast_breach_prob` is returned as CONTEXT for a risk-sizing
    decision upstream (e.g. a term-structure-style guard), not as a basis
    for picking a different cell -- doing that was tried exhaustively and
    did not survive verification.

    `live=False` (the default) uses the walk-forward series, which is fit
    only on data preceding `target_date` and is therefore safe to call for
    any historical date. `live=True` refits on ALL available history for a
    current display number (see `live_forecast`) -- it must never be used to
    score a historical date, since the fit would then include data from
    after that date. The lookahead-capable path is opt-in and named, so it
    cannot be selected by accident."""
    if live:
        lf = live_forecast(model="harx")
        fc = {
            "forecast_vol_annualized_pct": lf["forecast_vol_annualized_pct"],
            "forecast_as_of": lf["data_through"],
        }
    else:
        fc = forecast_for_date(target_date)
    std_returns = build_standardized_return_distribution()
    breach_prob = empirical_breach_prob(std_returns, fc["forecast_vol_annualized_pct"], distance, horizon_days)

    return {
        "date": target_date,
        "trade": True,  # this track never found a validated reason to skip a specific week
        "distance": distance,
        "width": width,
        "forecast_vol_annualized_pct": fc["forecast_vol_annualized_pct"],
        "forecast_as_of": fc["forecast_as_of"],
        "forecast_breach_prob": breach_prob,
        "note": (
            "Cell is the fixed cost-robust baseline (Step 0), not a forecast-driven pick -- "
            "using this forecast to pick strikes, size positions, or skip weeks was tested eight "
            "independent ways (Experiments 15/19/20/21/22/23/24/26/27) and never beat this baseline "
            "after correction for the randomization null. forecast_breach_prob is informational only."
        ),
    }


if __name__ == "__main__":
    from datetime import date

    result = decide(date(2026, 8, 21))
    for k, v in result.items():
        print(f"{k}: {v}")
