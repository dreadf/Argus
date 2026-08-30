import numpy as np
import pandas as pd

# Layer 1 (see TRADING_SYSTEM_PLAN.md): answers "does this signal rank stocks
# correctly, and is it stable?"
#
# Both functions take/return the same [timestamp, symbol, score] shape used
# by pipeline/signals/signals.py, so any signal source (synthetic or real)
# can be measured the same way.


# For each date, the cross-sectional rank correlation between `score` and
# `fwd_5d_return` across all symbols that day. Returns one IC value per date.
def daily_ic(scores, fwd_returns, method='spearman'):
    # how='inner': keep only rows that match in BOTH tables (need both score
    # and the real outcome to correlate them)
    merged = scores.merge(fwd_returns, on=['timestamp', 'symbol'], how='inner')

    def _corr_one_day(day):
        # .corr(): pandas' built-in correlation between two columns.
        # method='spearman' = rank correlation (cares about ordering, not raw values)
        return day['score'].corr(day['fwd_5d_return'], method=method)

    # include_groups=False: don't pass the 'timestamp' column itself into
    # _corr_one_day. It's only needed to split into groups, not for the math
    return merged.groupby('timestamp').apply(_corr_one_day, include_groups=False)


# Summarizes a daily_ic() series into headline numbers.
#
# The critical detail: 5-day forward-return labels overlap, so consecutive 
# daily IC values are NOT independent observations. A t-stat computed on every 
# row is inflated by roughly sqrt(5). `overlap` controls the subsampling (every Nth date) used
# for the t-stat, so that number is computed on close-to-independent samples.
def ic_summary(ic_series, overlap=5):
    ic_series = ic_series.dropna().sort_index()
    non_overlap = ic_series.iloc[::overlap]  # step-slice: take every Nth date (0, 5, 10, ...)

    n_eff = len(non_overlap)
    if n_eff > 1 and non_overlap.std(ddof=1) > 0:
        # ddof=1: standard "sample" std formula (divides by n-1, not n)
        # t-stat = mean / standard_error; bigger n_eff -> smaller standard error -> more confident
        t_stat = non_overlap.mean() / (non_overlap.std(ddof=1) / np.sqrt(n_eff))
    else:
        t_stat = float('nan')

    mean_ic = ic_series.mean()
    std_ic = ic_series.std()

    return {
        'mean_ic': mean_ic,
        'std_ic': std_ic,
        'information_ratio': mean_ic / std_ic if std_ic else float('nan'),
        'n_days': len(ic_series),
        'n_eff_non_overlap': n_eff,
        't_stat_non_overlap': t_stat,
    }
