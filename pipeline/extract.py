from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime
from dotenv import load_dotenv # import function to read the .env file
from pipeline.config import SYMBOLS, START_DATE, END_DATE
import os
import pandas as pd

load_dotenv() # Reads the .env file
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

# Initialize the data
data_client = StockHistoricalDataClient(api_key, secret_key)

def fetch_and_save(symbols, start_date, end_date):
    # Request Object for Daily Bars (Open, High, Low, Close, Volume)
    request_params = StockBarsRequest(
        symbol_or_symbols = symbols,
        timeframe=TimeFrame.Day,
        start= start_date,
        end= end_date
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
        print(f'Done exporting {s}')

    # Testing purposes
    print(stock_df.index)
    print("Raw Data Preview")
    pd.set_option('display.max_columns',None)
    pd.set_option('display.width',1000)
    print(stock_df.head())

if __name__ == '__main__':
    fetch_and_save(SYMBOLS, START_DATE, END_DATE)