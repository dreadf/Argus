"""Small shared I/O helpers used across the pipeline."""

from __future__ import annotations

import os

import pandas as pd


def atomic_to_csv(df: pd.DataFrame, path: str, **kwargs) -> None:
    """Write a temp file in the same directory then os.replace() it into
    place, so a write interrupted by a concurrent re-run or a killed
    process can never leave a truncated/malformed CSV for a reader (e.g.
    the dashboard's pd.read_csv) to trip over."""
    tmp_path = f"{path}.tmp"
    df.to_csv(tmp_path, **kwargs)
    os.replace(tmp_path, path)


def coerce_win_column(results_df: pd.DataFrame) -> pd.DataFrame:
    """spread_backtest_results.csv's "win" column round-trips through
    pd.read_csv as the strings "True"/"False" (plus real bools for a
    DataFrame that was never written to disk) -- this normalizes either
    shape to real Python bools. Shared by evidence_gate.py and
    false_trip.py, which both used to carry their own copy of this map."""
    results_df = results_df.copy()
    results_df["win"] = results_df["win"].map({"True": True, "False": False, True: True, False: False})
    return results_df
