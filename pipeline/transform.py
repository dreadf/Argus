import pandas as pd
import numpy as np
from pipeline.config import SYMBOLS

pd.set_option('display.max_column', None)
pd.set_option('display.width', 1000)

def engineer_features(symbol):
    # Load the extracted raw data
    stock_df = pd.read_csv(f'output/data/raw_{symbol}.csv', index_col = 'timestamp', parse_dates=True)

    # 10-Day Simple Moving Average Calculations
    stock_df['SMA_10'] = stock_df['close'].rolling(window=10).mean()

    # 30-Day Simple Moving Average Calculations
    stock_df['SMA_30'] = stock_df['close'].rolling(window=30).mean()

    # Calculate the Daily Returns, automatically calculates with (Today - Yesterday) / Yesterday
    stock_df['daily_return'] = stock_df['close'].pct_change()

    # Volume Momentum on Distributions
    # It tells the model "Trading volume is 300% higher than normal today"
    # We'll compare today's volume to the average volume on the apst 20 days
    stock_df['volume_spike'] = stock_df['volume']/stock_df['volume'].rolling(window=20).mean()

    # Relative Strength Index (RSI)
    # Moving Average tells you the direction, but RSI tells you the strength of the trend
    # If RSI > 70 then the stock is overbought (too expensive, expected to crash)
    # If RSI < 30 then the stock is oversold (too cheap, expected to bounce)
    stock_df['diff'] = stock_df['close'].diff()
    stock_df['gains'] = stock_df['diff'].clip(lower=0)
    stock_df['losses'] = stock_df['diff'].clip(upper=0).abs()
    stock_df['gains'] = stock_df['gains'].rolling(window=14).mean()
    stock_df['losses'] = stock_df['losses'].rolling(window=14).mean()
    # Then we calculate the RS
    stock_df['RS'] = stock_df['gains']/stock_df['losses']
    stock_df['RSI'] = 100 - (100/(1+stock_df['RS']))

    # Forward 5D Return
    # This is what the model is trying to predict, so we're basically making the target feature
    stock_df['fwd_5d_return'] = (stock_df['close'].shift(-5) / stock_df['close'] - 1)
    # To categorize whether there is a return or not
    stock_df['target_5d'] = np.where(stock_df['fwd_5d_return'] > 0, 1, 0)

    # Lagged / Multi Day Returns (Momentum)
    # A 1-day return are mostly noise.
    # Whether a stock has been performing over the last 5 or 20 days, it can tell you the overall trend
    for t in [5, 10, 20]:
        stock_df[f'momentum_{t}'] = stock_df['close'].pct_change(periods=t)

    # Distance from Moving Average
    # The raw SMA valuae doesn't really capture the range, it could mean different for a $50 stock and a $500 stock.
    # What matters is the relationship between today's price and its recent averages
    # Is it overbought (way above the trend) or oversold (below the trend)?
    for t in [10, 30]:
        stock_df[f'distance_SMA{t}'] = (stock_df['close'] - stock_df[f'SMA_{t}']) / stock_df[f'SMA_{t}']

    # Rolling Volatility
    # Stocks may have similar average return, but they might have different risks.
    # Volatility shows us how much the stocks fluctuate.
    # So if we apply SD into daily returns, we can see how much this stock has been swinging
    for t in [5, 10]:
        stock_df[f'volatility_{t}'] = stock_df['daily_return'].rolling(window=t).std()

    # Average True Range (ATR)
    # We're trying to capture the volatility during a one day period
    # We take yesterday's close price
    prev = stock_df['close'].shift(1)
    # Built 3 Ranges according to the formula
    r1 = stock_df['high'] - stock_df['low']
    r2 = stock_df['high'] - prev
    r3 = (stock_df['low'] - prev).abs()
    # We find the one with the highest value amongst the ranges
    stock_df['true_range'] = pd.concat([r1, r2, r3], axis=1).max(axis=1)
    # We can add a window
    for t in [5, 10]:
        stock_df[f'ATR_{t}'] = stock_df['true_range'].rolling(window=t).mean()

    # Drop columns that aren't needed
    stock_df = stock_df.drop(columns=['diff', 'gains', 'losses', 'RS', 'true_range'])
    stock_df = stock_df.dropna()
    # Test print last 15 row to see the column
    #print(stock_df[['close', 'SMA_10','SMA_30','distance_SMA10', 'distance_SMA30','daily_return', 'volatility_5', 'volatility_10', 'ATR_5','ATR_10', 'volume_spike','RSI', 'target_5d', 'momentum_5', 'momentum_10', 'momentum_20']].tail(10))

    # Export the dataset
    stock_df.to_csv(f"output/data/engineered_{symbol}.csv")

if __name__ == '__main__':
    for s in SYMBOLS:
        engineer_features(s)
