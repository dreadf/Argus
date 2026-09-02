from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment
from datetime import datetime
from dotenv import load_dotenv # import function to read the .env file
from pipeline.config import SYMBOLS, START_DATE, END_DATE
import os
import pandas as pd

# A single-day move beyond this magnitude is treated as an unadjusted stock
# split slipping through, not a real trading day -- real single-day moves in
# this project's universe (including the 2020 COVID crash) never approach
# this. Historical grounding: fetching without `adjustment` produced fake
# moves of -89.9% (NVDA 10:1 split, 2024-06-10), -95.1% (GOOGL 20:1),
# -94.9% (AMZN 20:1), and -74.2% (AAPL 4:1) -- all comfortably past this bar,
# while no genuine trading day in the fetched history comes close to it.
MAX_PLAUSIBLE_DAILY_MOVE = 0.5


def assert_no_split_artifacts(closes: pd.Series, symbol: str = "") -> None:
    """Raises if any single-day return in `closes` exceeds
    MAX_PLAUSIBLE_DAILY_MOVE in magnitude. Run this after every fetch --
    it is what would have caught the missing-`adjustment` defect before it
    silently contaminated every price-derived ML feature and the 5-day
    forward-return target."""
    returns = closes.pct_change().dropna()
    bad = returns[returns.abs() > MAX_PLAUSIBLE_DAILY_MOVE]
    if not bad.empty:
        worst = bad.abs().idxmax()
        raise ValueError(
            f"{symbol}: {len(bad)} single-day move(s) exceed "
            f"{MAX_PLAUSIBLE_DAILY_MOVE:.0%} (worst: {bad[worst]:+.1%} on {worst}). "
            f"This almost always means an unadjusted stock split, not a real "
            f"trading day -- check the fetch used adjustment=Adjustment.SPLIT."
        )

load_dotenv() # Reads the .env file
api_key = os.getenv('ALPACA_API_KEY')
secret_key = os.getenv('ALPACA_SECRET_KEY')

# Initialize the data
data_client = StockHistoricalDataClient(api_key, secret_key)

def fetch_and_save(symbols, start_date, end_date):
    # Request Object for Daily Bars (Open, High, Low, Close, Volume)
    # adjustment=Adjustment.ALL, not SPLIT: SPLIT alone still leaves a real
    # artifact. Alpaca's SPLIT adjustment retroactively rescales history for
    # ordinary forward splits (fixing NVDA/GOOGL/AMZN/AAPL's fake ~-90% days)
    # but ALSO applies a 2x rescale for HON's 2026-06 Aerospace spinoff --
    # confirmed live: RAW/SPLIT/ALL all agree after 2026-06-29, but SPLIT
    # alone shows 464.42 on 2026-06-26 where RAW and ALL both show ~230-240.
    # ALL does not carry that spinoff-driven 2x artifact and correctly
    # dividend-adjusts on top, which is fine here: this fetch never touches
    # output/data/raw_SPY.csv (SPY is not in config.SYMBOLS, see fetch_and_save's
    # call site), so the options system's strikes -- the only place a
    # dividend adjustment would be wrong -- are never affected by this choice.
    request_params = StockBarsRequest(
        symbol_or_symbols = symbols,
        timeframe=TimeFrame.Day,
        start= start_date,
        end= end_date,
        adjustment=Adjustment.ALL,
    )

    # Fetch Data
    stock_bars = data_client.get_stock_bars(request_params)

    # Convert the data into Pandas Dataframe
    stock_df = stock_bars.df

    # Separate the Stocks Data
    for s in stock_df.index.get_level_values('symbol').unique():
        new = stock_df.xs(s)
        assert_no_split_artifacts(new['close'], symbol=s)
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