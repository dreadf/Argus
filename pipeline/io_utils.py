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
