from alpaca.data.historical.news import NewsClient
from alpaca.data.requests import NewsRequest
from datetime import datetime
from dotenv import load_dotenv # import function to read the .env file
from pipeline.config import SYMBOLS, START_DATE, END_DATE
import os
import pandas as pd
import time

CSV_PATH = 'output/data/raw_news.csv'

_news_client_cache = None


def _get_news_client():
    """Constructed lazily, on first real use, not at module import time --
    the same class of bug fixed this session in pipeline/extract.py,
    pipeline/run_all.py, pipeline/backtest/spread_backtest.py,
    pipeline/options/chain.py, and pipeline/options/vol.py. Every dev
    machine has a real .env, which is exactly why this was invisible
    locally; CI has none, by design."""
    global _news_client_cache
    if _news_client_cache is None:
        load_dotenv()
        _news_client_cache = NewsClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))
    return _news_client_cache

# Discovered while testing: alpaca-py's NewsClient.get_news() already
# paginates internall. It keeps calling the API in the background until it has
# collected `limit` articles (or the server runs out), then returns one merged
# result.

# Split each symbol's date range into
# quarterly chunks, so no single request has a realistic chance of hitting the cap.
def _quarterly_chunks(start_date, end_date):
    bounds = pd.date_range(start=start_date, end=end_date, freq='QS')
    if len(bounds) == 0 or bounds[0] != pd.Timestamp(start_date):
        bounds = pd.DatetimeIndex([pd.Timestamp(start_date)]).append(bounds)
    if bounds[-1] < pd.Timestamp(end_date):
        bounds = bounds.append(pd.DatetimeIndex([pd.Timestamp(end_date)]))

    chunks = []
    for i in range(len(bounds) - 1):
        chunk_start = bounds[i]
        # Consecutive chunks previously shared an exact boundary timestamp
        # (chunk i's end == chunk i+1's start), risking a double-fetched
        # article published at that exact instant -- masked downstream by
        # the dedup in panel.py's add_news_features, but present in the raw
        # fetched file. Subtracting 1 second from every end except the very
        # last one makes the ranges genuinely non-overlapping.
        chunk_end = bounds[i + 1] if i == len(bounds) - 2 else bounds[i + 1] - pd.Timedelta(seconds=1)
        chunks.append((chunk_start, chunk_end))
    return chunks


def _fetch_one_request(symbol, chunk_start, chunk_end):
    request = NewsRequest(
        symbols=symbol,
        start=chunk_start,
        end=chunk_end,
        limit=10000,
        sort='asc',
    )

    # Retry up to 3 times before giving up on this one chunk.
    for attempt in range(3):
        try:
            result = _get_news_client().get_news(request)
            return result.data['news']
        except Exception as e:
            wait = 5 * (attempt + 1)   # 5s, then 10s, then 15s
            print(f'  Request failed ({e}), retrying in {wait}s...')
            time.sleep(wait)

    print(f'  Failed 3 times in a row for {symbol} {chunk_start.date()}-{chunk_end.date()}, skipping this chunk.')
    return []


def fetch_news(symbols, start_date, end_date):
    chunks = _quarterly_chunks(start_date, end_date)
    print(f'{len(symbols)} symbols x {len(chunks)} quarterly chunks = {len(symbols) * len(chunks)} requests planned')

    wrote_header = False   # first write this run should overwrite any stale file

    for symbol in symbols:
        symbol_articles = []

        for chunk_start, chunk_end in chunks:
            articles = _fetch_one_request(symbol, chunk_start, chunk_end)
            for article in articles:
                symbol_articles.append({
                    'created_at': article.created_at,
                    'headline': article.headline,
                    'symbols': article.symbols,
                })
            time.sleep(0.3)   # stay under the 200 calls/minute rate limit

        print(f'{symbol}: {len(symbol_articles)} articles across {len(chunks)} chunks')

        # Checkpoint after each symbol finishes, if this crashes on symbol #30,
        # symbols #1-29 are already safely on disk.
        if symbol_articles:
            pd.DataFrame(symbol_articles).to_csv(
                CSV_PATH,
                mode='w' if not wrote_header else 'a',
                header=not wrote_header,
                index=False,
            )
            wrote_header = True

    print(f'Done. News saved to {CSV_PATH}')


if __name__ == '__main__':
    fetch_news(SYMBOLS, START_DATE, END_DATE)
