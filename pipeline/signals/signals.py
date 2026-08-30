import numpy as np
import pandas as pd
from scipy.stats import norm

# The contract every signal source follows (see TRADING_SYSTEM_PLAN.md, Layer 0):
#   input:  panel_df (must have a 'symbol' column, a 'timestamp' index.
#           For oracle_signal/planted_ic_signal, a 'fwd_5d_return' column)
#   output: a DataFrame with exactly ['timestamp', 'symbol', 'score']
#           one row per (date, symbol) the signal has an opinion about.
#           Higher score = more attractive = more long.
#
# These are calibration tools, not trading signals. Before trusting the IC
# measuring code (pipeline/eval/), we run these three known-answer signals
# to test whether the IC measurment actually works or no


# The zero-information signal. If the IC is not 0, that means the measuring
# tool (IC) is broken.
def random_signal(panel_df, seed=None):
    rng = np.random.default_rng(seed)  # random number generator; same seed = same numbers every run
    df = panel_df.reset_index()[['timestamp', 'symbol']].copy()
    df['score'] = rng.standard_normal(len(df))  # n random numbers from a bell-curve distribution
    return df


# Deliberately leaky: the score IS the answer key (fwd_5d_return itself).
# this proves whether the measuring tool reads ~1 (perfect rank correlation) when
# given a perfect signal or not. If it doesn't, then the measuring tool is broken.
def oracle_signal(panel_df):
    df = panel_df.reset_index()[['timestamp', 'symbol', 'fwd_5d_return']].copy()
    df = df.rename(columns={'fwd_5d_return': 'score'})
    return df


# A signal with a KNOWN, controllable IC, built by blending the true answer
# with independent noise. Lets us check the measuring tool's precision, not
# just its correctness, e.g. "planted 0.03, did it read back ~0.03?"
#
# How the blend works: each day, convert fwd_5d_return's cross-sectional rank
# into a standard-normal score (true_z). Mix it with independent standard-
# normal noise (noise_z) as score = rho*true_z + sqrt(1-rho^2)*noise_z. 
def planted_ic_signal(panel_df, rho, seed=None):
    rng = np.random.default_rng(seed)
    df = panel_df.reset_index()[['timestamp', 'symbol', 'fwd_5d_return']].copy()

    def _plant_one_day(group):
        # rank(pct=True): turn values into "percentile position" (0.0-1.0) instead of the raw number
        true_rank_pct = group['fwd_5d_return'].rank(pct=True)
        true_z = norm.ppf(true_rank_pct.clip(0.001, 0.999))
        noise_z = rng.standard_normal(len(group))
        # rho controls the mix: rho=0.03 means ~3% true signal, rest is noise.
        # sqrt(1-rho^2) is the specific weight that makes the blend's correlation
        # with true_z come out to exactly rho
        blended = rho * true_z + np.sqrt(1 - rho ** 2) * noise_z
        # Must return a Series indexed like `group`, or groupby().apply() can't tell
        # which row each value belongs to
        return pd.Series(blended, index=group.index)

    df['score'] = df.groupby('timestamp', group_keys=False).apply(_plant_one_day)
    return df[['timestamp', 'symbol', 'score']]


# The real signal source: this is the score from the XGB model's predicted
# probabilities, which are stored into [timestamp, symbol, score] shape as the
# so it can be measured.
def model_signal(panel_df, model, feature_columns):
    df = panel_df.reset_index()[['timestamp', 'symbol']].copy()
    # predict_proba returns 2 columns (P(class 0), P(class 1)), [:, 1] means
    # "every row, just column index 1". We only want P(relative_target=1)
    df['score'] = model.predict_proba(panel_df[feature_columns])[:, 1]
    return df
