from datetime import datetime

SYMBOLS = [
    # Technology
    "AAPL", "MSFT", "NVDA", "ADBE",
    # Communication Services
    "GOOGL", "META", "DIS", "NFLX",
    # Consumer Discretionary
    "AMZN", "TSLA", "HD", "MCD",
    # Consumer Staples
    "KO", "PG", "WMT", "PEP",
    # Financials
    "JPM", "BAC", "GS", "V",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV",
    # Energy
    "XOM", "CVX", "COP", "SLB",
    # Industrials
    "BA", "CAT", "UPS", "HON",
    # Materials
    "LIN", "FCX", "NEM", "DOW",
    # Utilities
    "NEE", "DUK",
    # Real Estate
    "PLD", "AMT",
]
START_DATE = datetime(2020, 1, 1)
END_DATE = datetime(2026, 8, 25)

# Broad-market proxy (S&P 500 ETF), used to build residual features.
# Kept separate from SYMBOLS so it never becomes a tradeable long/short candidate.
MARKET_SYMBOL = "SPY"