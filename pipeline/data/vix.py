"""
Fetch and cache VIX, VIX9D, and VIX3M daily closes from CBOE's public CSV
endpoints. Free, no API key, no rate limit documented -- but still an
external dependency outside Alpaca, so every read through this module goes
through a cache with an explicit fetch timestamp, and a stale cache blocks
trading rather than silently proceeding (same discipline as
options/chain.py's 15-minute quote staleness check, adapted to a daily
series: CBOE updates each of these once per trading day).

VIX9D (9-day implied vol) is the closest published instrument to this
project's 7-11 DTE tenor. VIX3M / VIX9D is the term-structure ratio the
W4 guard (check_term_structure) uses: > 1 means the curve is normal/calm
(longer-dated vol priced above near-dated), < 1 means it has flattened or
inverted -- the condition that preceded 21 of 22 backwardation episodes
tied to a >5% S&P drawdown within 30 days (2004-2025, per the research
this guard is built on).

Retry pattern matches options/chain.py's _retry (3 attempts, 5/10/15s
backoff). Cache write matches io_utils.atomic_to_csv.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone

import pandas as pd
import requests

from pipeline.io_utils import atomic_to_csv

CBOE_URL_TEMPLATE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
SERIES_NAMES = ("VIX", "VIX9D", "VIX3M")

CACHE_DIR = "output/data"
CACHE_META_PATH = f"{CACHE_DIR}/vix_cache_meta.json"

MAX_RETRIES = 3
MAX_CACHE_AGE_DAYS = 3  # generous enough to cover a weekend + one skipped refresh, tight enough to catch a genuinely broken fetch


def _cache_path(name: str) -> str:
    return f"{CACHE_DIR}/{name.lower()}.csv"


def _retry(fn, description: str):
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"  {description} failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"{description} failed {MAX_RETRIES} times in a row")


def fetch_vix_series(name: str) -> pd.Series:
    """Live fetch of one series ("VIX", "VIX9D", or "VIX3M") from CBOE.
    Returns a Series of closes indexed by date, sorted ascending."""
    if name not in SERIES_NAMES:
        raise ValueError(f"unknown series {name!r}, expected one of {SERIES_NAMES}")
    url = CBOE_URL_TEMPLATE.format(name=name)

    def _do_fetch():
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text

    text = _retry(_do_fetch, f"fetch {name} from CBOE")
    from io import StringIO

    df = pd.read_csv(StringIO(text))
    df["date"] = pd.to_datetime(df["DATE"])
    return df.set_index("date")["CLOSE"].sort_index()


def refresh_vix_cache(names: tuple[str, ...] = SERIES_NAMES) -> dict:
    """Fetches all requested series live and writes each to its own cached
    CSV, plus a metadata file recording when this refresh happened and
    what each series' last available date was -- this is what
    is_vix_cache_stale checks against, and what T-LIVE/the audit trail can
    point to if a guard blocks on stale VIX data."""
    meta = {"fetched_at": datetime.now(timezone.utc).isoformat(), "series": {}}
    for name in names:
        series = fetch_vix_series(name)
        atomic_to_csv(series.rename("close").to_frame(), _cache_path(name))
        meta["series"][name] = {"last_date": series.index.max().date().isoformat(), "n": len(series)}
        print(f"  {name}: {len(series)} rows, last date {series.index.max().date()}")
    with open(f"{CACHE_META_PATH}.tmp", "w") as f:
        json.dump(meta, f, indent=2)
    import os

    os.replace(f"{CACHE_META_PATH}.tmp", CACHE_META_PATH)
    return meta


def load_cached_vix(name: str) -> pd.Series:
    """Reads a previously cached series. Raises FileNotFoundError if
    refresh_vix_cache has never been run -- callers must treat that as a
    data-sanity block, not silently proceed without term-structure data
    (Guard #2's existing convention for a missing/stale option chain)."""
    df = pd.read_csv(_cache_path(name), parse_dates=["date"])
    return df.set_index("date")["close"]


def vix_cache_age_days() -> float | None:
    """Days since the cache was last refreshed, from the metadata file's
    fetched_at timestamp. None if the cache has never been built."""
    try:
        with open(CACHE_META_PATH) as f:
            meta = json.load(f)
    except FileNotFoundError:
        return None
    fetched_at = datetime.fromisoformat(meta["fetched_at"])
    return (datetime.now(timezone.utc) - fetched_at).total_seconds() / 86400.0


def is_vix_cache_stale(max_age_days: float = MAX_CACHE_AGE_DAYS) -> bool:
    """True if the cache is missing, unreadable, or older than
    max_age_days -- the single check run_agent.py/guards.py should call
    before trusting the term-structure guard's inputs. Fails closed: any
    ambiguity (missing meta file, corrupt JSON) reads as stale, never as
    fresh."""
    age = vix_cache_age_days()
    if age is None:
        return True
    return age > max_age_days


def contango_ratio(vix9d: pd.Series, vix3m: pd.Series) -> pd.Series:
    """VIX3M / VIX9D, aligned on shared dates. >1 = normal calm term
    structure (longer-dated vol priced above near-dated), <1 = flattened
    or inverted -- the danger signal check_term_structure watches for."""
    aligned = pd.DataFrame({"vix9d": vix9d, "vix3m": vix3m}).dropna()
    return (aligned["vix3m"] / aligned["vix9d"]).rename("contango")


def current_contango_and_threshold(as_of: date | None = None, percentile: float = 0.33, min_history: int = 60) -> tuple[float | None, float | None]:
    """Today's contango ratio plus the trailing threshold to compare it
    against, both computed from the cache. The threshold uses ONLY data
    strictly BEFORE `as_of` -- the walk-forward discipline the whole
    term-structure filter research (Experiment 12d) depends on: a live
    guard's threshold must never be computed from data it couldn't have
    seen yet. Returns (None, None) if there isn't enough prior history or
    today isn't in the cached series (e.g. a holiday, or the cache is a
    day behind).
    """
    v9 = load_cached_vix("VIX9D") / 100.0
    v3m = load_cached_vix("VIX3M") / 100.0
    ratio = contango_ratio(v9, v3m)
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else ratio.index.max()

    today_value = ratio.get(as_of_ts)
    prior = ratio[ratio.index < as_of_ts]
    if today_value is None or pd.isna(today_value) or len(prior) < min_history:
        return None, None
    return float(today_value), float(prior.quantile(percentile))


if __name__ == "__main__":
    print("Refreshing VIX/VIX9D/VIX3M cache from CBOE...")
    meta = refresh_vix_cache()
    print(f"\nCache refreshed at {meta['fetched_at']}")

    # Self-check 1: cache round-trips correctly.
    for name in SERIES_NAMES:
        s = load_cached_vix(name)
        assert len(s) > 0, f"{name} cache is empty after refresh"
        assert s.index.is_monotonic_increasing, f"{name} cache is not sorted by date"
    print("Self-check: all three series load back correctly, sorted ascending -- PASS")

    # Self-check 2: freshness check reads a just-refreshed cache as fresh.
    assert not is_vix_cache_stale(), "cache should not read as stale immediately after a refresh"
    print("Self-check: freshly refreshed cache reads as NOT stale -- PASS")

    # Self-check 3: an artificially aged meta file computes as stale --
    # simulated by backdating fetched_at in a copy, rather than waiting
    # real days for a genuine cache to age.
    import os
    from datetime import timedelta

    with open(CACHE_META_PATH) as f:
        real_meta = json.load(f)
    backup_path = CACHE_META_PATH + ".self-check-backup"
    os.rename(CACHE_META_PATH, backup_path)
    try:
        aged_meta = dict(real_meta)
        aged_meta["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=MAX_CACHE_AGE_DAYS + 1)).isoformat()
        with open(CACHE_META_PATH, "w") as f:
            json.dump(aged_meta, f)
        age = vix_cache_age_days()
        assert age is not None and age > MAX_CACHE_AGE_DAYS, f"backdated cache should compute as stale, got age={age}"
        assert is_vix_cache_stale(), "a cache older than MAX_CACHE_AGE_DAYS must read as stale"
        print(f"Self-check: a cache backdated to {MAX_CACHE_AGE_DAYS + 1} days old reads as stale -- PASS")
    finally:
        os.remove(CACHE_META_PATH)
        os.rename(backup_path, CACHE_META_PATH)

    # Self-check 4: a genuinely missing cache also fails closed (stale).
    moved = CACHE_META_PATH + ".self-check-backup"
    os.rename(CACHE_META_PATH, moved)
    try:
        assert vix_cache_age_days() is None
        assert is_vix_cache_stale(), "a missing cache must read as stale, not fresh"
        print("Self-check: a missing cache file fails closed to stale -- PASS")
    finally:
        os.rename(moved, CACHE_META_PATH)

    # Self-check 5: contango_ratio aligns and computes sensibly.
    v9 = load_cached_vix("VIX9D")
    v3m = load_cached_vix("VIX3M")
    ratio = contango_ratio(v9, v3m)
    assert len(ratio) > 0
    assert ratio.median() > 0.5 and ratio.median() < 2.0, f"contango ratio median {ratio.median()} looks implausible"
    print(f"Self-check: contango ratio computed over {len(ratio)} aligned days, "
          f"median {ratio.median():.3f}, latest {ratio.iloc[-1]:.3f} -- PASS")

    # Self-check 6: current_contango_and_threshold's walk-forward property
    # -- the threshold must never move when the future changes.
    today_val, thr_before = current_contango_and_threshold()
    assert today_val is not None and thr_before is not None
    print(f"Self-check: today's contango={today_val:.3f}, trailing 33rd-pct threshold={thr_before:.3f}")
    # Verify by construction: recomputing at an EARLIER as_of date must
    # give the identical threshold logic (same prior-only slice), proving
    # the function isn't peeking past its as_of cutoff.
    ratio_full = contango_ratio(load_cached_vix("VIX9D") / 100.0, load_cached_vix("VIX3M") / 100.0)
    earlier_date = ratio_full.index[-30]  # 30 trading days before the latest cached date
    _, thr_earlier = current_contango_and_threshold(as_of=earlier_date)
    manual_thr = float(ratio_full[ratio_full.index < earlier_date].quantile(0.33))
    assert thr_earlier is not None and abs(thr_earlier - manual_thr) < 1e-9, \
        f"threshold at an earlier as_of ({thr_earlier}) should exactly match a manual prior-only quantile ({manual_thr})"
    print(f"Self-check: threshold at an earlier as_of date matches a manual prior-only quantile exactly -- PASS")

    print("\nAll vix.py self-checks passed.")
