from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime
from dotenv import load_dotenv # import function to read the .env file
import os
import pandas as pd

load_dotenv() # Reads the .env file
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

# Initialize the data
data_client = StockHistoricalDataClient(api_key, secret_key)

# Define the Request Parameters
symbol = ["AAPL", "MSFT", "JPM", "KO", "XOM"] # stock name
# Select timeframe
start_time = datetime(2020, 1, 1)
end_time = datetime(2026, 8, 14)

# Request Object for Daily Bars (Open, High, Low, Close, Volume)
request_params = StockBarsRequest(
    symbol_or_symbols = symbol,
    timeframe=TimeFrame.Day,
    start=start_time,
    end=end_time
)

# Fetch Data
stock_bars = data_client.get_stock_bars(request_params)

# Convert the data into Pandas Dataframe
stock_df = stock_bars.df

# Separate the Stocks Data
for s in stock_df.index.get_level_values('symbol').unique():
    new = stock_df.xs(s)
    # Save the Raw Data for the next steps
    new.to_csv(f'output/data/raw_{s}.csv')

# Testing purposes
print(stock_df.index)
print("Raw Data Preview")
pd.set_option('display.max_columns',None)
pd.set_option('display.width',1000)
print(stock_df.head())


