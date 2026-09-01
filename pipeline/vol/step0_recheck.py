"""
Step 0 of the volatility research track (see the plan at
.claude/plans/we-need-a-major-buzzing-catmull.md).

Two things, both read-only against pipeline/backtest/spread_backtest.py's
output and reusing pipeline/backtest/evidence_gate.py's cushion math rather
than reimplementing it:

1. Defect A: output/data/spread_backtest_results.csv's last entry Friday
   (2026-08-21) settles only 3 calendar days later against raw_SPY.csv's
   final bar (2026-08-24), instead of the usual 7 -- a truncation artifact
   of the data's own end date, not a real short week. SPY barely moved in
   that window, so every one of that week's 24 cells records a win. Verified
   below (impact is immaterial to the headline, real but small -- see the
   plan's verification log item 12), then dropped for hygiene.

2. Defect A aside: re-run the full width sweep (not just the $1/$2/$5 the
   prior audit tested) across the same slippage grid, and check whether the
   $5-width finding is stable across sub-periods rather than an artifact of
   the full-sample average (protocol item 7 -- an in-sample pick across 24
   cells needs its own stability check before being adopted as a baseline).
"""

from __future__ import annotations

import pandas as pd

from pipeline.backtest.evidence_gate import _cushion_for_cell
from pipeline.io_utils import coerce_win_column

RESULTS_PATH = "output/data/spread_backtest_results.csv"
TRUNCATED_ENTRY = pd.Timestamp("2026-08-21")


def load_corrected_results() -> pd.DataFrame:
    """The backtest's raw output with Defect A's truncated week removed."""
    df = coerce_win_column(pd.read_csv(RESULTS_PATH, parse_dates=["entry", "expiry"]))
    before = df["entry"].nunique()
    df = df[df["entry"] != TRUNCATED_ENTRY].copy()
    after = df["entry"].nunique()
    assert after == before - 1, f"expected to drop exactly 1 week, dropped {before - after}"
    return df


def _measure_defect_a_impact(raw: pd.DataFrame, corrected: pd.DataFrame) -> None:
    """Confirms the plan's claim that Defect A is real but immaterial to the
    headline (3.28->3.30 at $0.00, -0.40->-0.36 at $0.05), before trusting
    any number built on the corrected data."""
    print("=== Defect A impact check (3% distance, $1 width) ===")
    for label, df, slip in [
        ("raw,       $0.00 slip", raw, 0.0),
        ("corrected, $0.00 slip", corrected, 0.0),
        ("raw,       $0.05 slip", raw, 0.05),
        ("corrected, $0.05 slip", corrected, 0.05),
    ]:
        valid = df[~df["missing_data"]]
        cell = valid[(valid["distance"] == 0.03) & (valid["width"] == 1)]
        row = _cushion_for_cell(cell, slippage_per_share=slip)
        print(f"  {label}: n={row['n']:3d}  cushion_se={row['cushion_se']:.2f}")
    print()


def _full_width_sweep(df: pd.DataFrame) -> pd.DataFrame:
    """Cushion in SE at 3% distance, every width the backtest actually
    swept (1/2/5/10), across the slippage grid -- the prior audit table
    only ever showed 1/2/5."""
    valid = df[~df["missing_data"]]
    widths = sorted(valid["width"].unique())
    slippages = [0.0, 0.02, 0.05, 0.10]
    rows = []
    for slip in slippages:
        row = {"slippage": slip}
        for w in widths:
            cell = valid[(valid["distance"] == 0.03) & (valid["width"] == w)]
            r = _cushion_for_cell(cell, slippage_per_share=slip)
            row[f"${w}"] = round(r["cushion_se"], 2) if r else None
        rows.append(row)
    return pd.DataFrame(rows)


def _width_stability_by_subperiod(df: pd.DataFrame) -> pd.DataFrame:
    """Is $5 width really the cost-robust choice, or just the full-sample
    average? Split into three roughly-equal chunks by entry date and redo
    the $0.05-slippage cushion for every width in each chunk. A finding that
    only holds in one chunk is not a finding (protocol item 7)."""
    valid = df[~df["missing_data"]].copy()
    entries = sorted(valid["entry"].unique())
    n = len(entries)
    third = n // 3
    chunks = {
        "early": entries[:third],
        "mid": entries[third : 2 * third],
        "late": entries[2 * third :],
    }
    widths = sorted(valid["width"].unique())
    rows = []
    for label, dates in chunks.items():
        chunk = valid[valid["entry"].isin(dates)]
        row = {"period": label, "n_weeks": len(dates),
               "date_range": f"{min(dates).date()} to {max(dates).date()}"}
        for w in widths:
            cell = chunk[(chunk["distance"] == 0.03) & (chunk["width"] == w)]
            r = _cushion_for_cell(cell, slippage_per_share=0.05)
            row[f"${w}"] = round(r["cushion_se"], 2) if r and r["n"] > 0 else None
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    raw = coerce_win_column(pd.read_csv(RESULTS_PATH, parse_dates=["entry", "expiry"]))
    corrected = load_corrected_results()

    _measure_defect_a_impact(raw, corrected)

    print("=== Full width sweep, 3% distance, corrected data ===")
    print(_full_width_sweep(corrected).to_string(index=False))
    print()

    print("=== Is $5 width stable across sub-periods at $0.05 slippage? ===")
    stability = _width_stability_by_subperiod(corrected)
    print(stability.to_string(index=False))
    print()

    best_per_period = stability.set_index("period")[["$1", "$2", "$5", "$10"]].idxmax(axis=1)
    print("Best width per sub-period:")
    print(best_per_period.to_string())
    if best_per_period.nunique() == 1:
        print(f"\n-> STABLE: {best_per_period.iloc[0]} wins in every sub-period.")
    else:
        print(f"\n-> NOT STABLE: best width changes across sub-periods "
              f"({best_per_period.nunique()} different winners). "
              f"The full-sample '$5 is cost-robust' claim needs qualification.")
