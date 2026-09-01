"""
Exports the volatility track's live forecast to `public/data/vol_forecast.json`
for the static Vercel dashboard.

Why a precomputed file rather than a serverless function: `.vercelignore`
excludes `pipeline/`, `output/`, and `scripts/`, so the Python pipeline is
NOT deployed to Vercel at all -- only `public/` and the one `api/account.py`
function are. The HAR-X model, its 2,555-day realized-volatility input, and
its VIX series therefore cannot be evaluated at request time there. The same
pattern the rest of that dashboard already uses (`public/data/*.json`, read
by `public/app.js` via fetchJSON) is the correct home for this.

Run this whenever the underlying RV/VIX data is refreshed, then commit the
regenerated JSON, exactly as the other `public/data/*.json` files work.

The number exported is the LIVE forecast (`deliverable.live_forecast()`:
refit on all available history, projected one step past the last observed
day), not the walk-forward series -- the walk-forward series necessarily
lags real data by up to one 63-day test block and was showing a 55-day-stale
number on the Streamlit dashboard before this distinction was made explicit.
Every validated claim in EXPERIMENT.md still comes from the walk-forward
series; this file is display-only and is scored nowhere.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.vol.deliverable import live_forecast
from pipeline.vol.overlay import BASELINE_DISTANCE
from pipeline.vol.skew_breach import build_standardized_return_distribution, empirical_breach_prob

OUTPUT_PATH = Path("public/data/vol_forecast.json")
HORIZON_DAYS = 7


def build_payload() -> dict:
    lf = live_forecast(model="harx")
    std_returns = build_standardized_return_distribution()
    breach_prob = empirical_breach_prob(
        std_returns, lf["forecast_vol_annualized_pct"], BASELINE_DISTANCE, HORIZON_DAYS
    )
    return {
        "forecast_vol_annualized_pct": round(lf["forecast_vol_annualized_pct"], 2),
        "breach_prob": round(breach_prob, 4),
        "breach_distance_pct": round(BASELINE_DISTANCE * 100, 1),
        "data_through": str(lf["data_through"]),
        "n_train": lf["n_train"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "note": (
            "Informational only. Not used by the Picker, Guard, or Reviewer. Eight independent "
            "tests (strike timing, position sizing, a skip filter) failed to convert this forecast "
            "into a validated trading edge."
        ),
    }


if __name__ == "__main__":
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {OUTPUT_PATH}")
    for k, v in payload.items():
        print(f"  {k}: {v}")
