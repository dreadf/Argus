import numpy as np
import pandas as pd
from pipeline.config import SYMBOLS

# Build panel data in which combines all of the stocks into one DataFrame
def build_panel_data(symbols):
    panel_data = []
    for s in symbols:
        temporal = pd.read_csv(f'output/data/engineered_{s}.csv', index_col='timestamp', parse_dates=True)
        temporal['symbol'] = s
        panel_data.append(temporal)

    return (pd.concat(panel_data))

# Split the data into train and test
def split_by_date(panel_df, train_percentage):
    # Calculates the cutoff date
    unique_dates = sorted(panel_df.index.unique())
    cutoff_index = int(len(unique_dates) * train_percentage)
    cutoff_date = unique_dates[cutoff_index]

    cutoff_date = pd.Timestamp(cutoff_date)
    train = []
    test= []
    for s in panel_df['symbol'].unique():
        tmp_train = panel_df[panel_df['symbol'] == s].loc[:cutoff_date - pd.Timedelta(days=7)]
        tmp_test = panel_df[panel_df['symbol'] == s].loc[cutoff_date + pd.Timedelta(days=1):]
        train.append(tmp_train)
        test.append(tmp_test)

    train_df = pd.concat(train)
    test_df = pd.concat(test)

    return train_df, test_df

# Get the X and Y
def get_x_y (df, feature, target):
    x = df[feature]
    y = df[target]

    return x, y

# Calculates the relative performance of a stock compared to the market median performance
# The function is written here because it needs the panel_df not the raw_data where each stock is a different file
def add_relative_target(panel_df):
   panel_df['market_median_return'] = panel_df.groupby(panel_df.index)['fwd_5d_return'].transform('median')
   panel_df['relative_target'] = np.where(panel_df['fwd_5d_return'] > panel_df['market_median_return'], 1, 0)
   return panel_df

# Adds broad-market (e.g. SPY) features to every stock's row on matching dates,
# then derives residual momentum (stock momentum minus market momentum) and rolling beta.
def add_market_features(panel_df, market_symbol, beta_window=60):
    market_df = pd.read_csv(f'output/data/engineered_{market_symbol}.csv', index_col='timestamp', parse_dates=True)

    market_cols = ['daily_return', 'momentum_5', 'momentum_10', 'momentum_20', 'volatility_5', 'volatility_10', 'RSI']
    market_df = market_df[market_cols].add_suffix('_mkt')

    panel_df = panel_df.join(market_df, how='left')

    # Residual momentum: how much of the stock's own move is NOT explained by the market's move
    for t in [5, 10, 20]:
        panel_df[f'residual_momentum_{t}'] = panel_df[f'momentum_{t}'] - panel_df[f'momentum_{t}_mkt']

    # Rolling beta: cov(stock return, market return) / var(market return), per symbol.
    # This function answers "How sensitive is this stock compare to the market in a 60 day window"
    def _rolling_beta(group):
        # Covariance(cov): Measures whether these two things actually moves together (correlates or no)
        cov = group['daily_return'].rolling(beta_window).cov(group['daily_return_mkt'])
        # Variance(var): Measures how fluctuative is the market in a 60 day window
        var = group['daily_return_mkt'].rolling(beta_window).var()
        # Use rumus: beta = cov(return saham, return market) / var(return market)
        return cov / var

    panel_df = panel_df.reset_index()
    panel_df[f'beta_{beta_window}'] = panel_df.groupby('symbol', group_keys=False).apply(_rolling_beta)
    panel_df = panel_df.set_index('timestamp')

    # Drop the warm-up rows the rolling beta introduces (same pattern as transform.py's dropna)
    panel_df = panel_df.dropna()

    return panel_df

if __name__ == '__main__':
    panel = build_panel_data(SYMBOLS)
    print(split_by_date(panel, 0.8))
