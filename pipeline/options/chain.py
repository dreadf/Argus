"""
Fetch a live SPY option chain: reference data (strike, expiry, open interest)
merged with live pricing (bid/ask/mid, implied volatility, delta).

Two separate Alpaca endpoints are needed because open_interest lives only on
the trading API's contract reference data, not on the market-data snapshot
(alpaca-py's OptionsSnapshot has no open_interest field at all).

Retry pattern copied from news_extract.py:47-57 (3 attempts, 5s/10s/15s
backoff); rate-limit sleep copied from news_extract.py:77.
"""

from __future__ import annotations

import os
import time
from datetime import date

import pandas as pd
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import OptionChainRequest, OptionLatestQuoteRequest, StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import ContractType
from alpaca.trading.requests import GetOptionContractsRequest
from dotenv import load_dotenv

from pipeline.options.config import UNDERLYING

_trading_client_cache: TradingClient | None = None
_stock_data_client_cache: StockHistoricalDataClient | None = None
_option_data_client_cache: OptionHistoricalDataClient | None = None


def _get_trading_client() -> TradingClient:
    """Constructed lazily, on first real use, not at module import time --
    found live (2026-09-03) via tests/test_monitor.py's realized_pnl tests,
    which only need to monkeypatch fetch_option_mids and never touch a real
    client, but `import pipeline.options.chain` alone used to construct
    three real Alpaca clients unconditionally and crashed CI with "You must
    supply a method of authentication." Same failure mode already fixed
    this session in pipeline/extract.py, pipeline/run_all.py, and
    pipeline/backtest/spread_backtest.py -- a fourth instance, in a file
    none of those fixes touched. Cached after first construction so this
    remains a single client per process, matching the old module-level
    global's behavior for every code path that actually needs it."""
    global _trading_client_cache
    if _trading_client_cache is None:
        load_dotenv()
        _trading_client_cache = TradingClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"), paper=True)
    return _trading_client_cache


def _get_stock_data_client() -> StockHistoricalDataClient:
    global _stock_data_client_cache
    if _stock_data_client_cache is None:
        load_dotenv()
        _stock_data_client_cache = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
    return _stock_data_client_cache


def _get_option_data_client() -> OptionHistoricalDataClient:
    global _option_data_client_cache
    if _option_data_client_cache is None:
        load_dotenv()
        _option_data_client_cache = OptionHistoricalDataClient(os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY"))
    return _option_data_client_cache


MAX_RETRIES = 3


def _retry(fn, description: str):
    for attempt in range(MAX_RETRIES):
        try:
            return fn()
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"  {description} failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"{description} failed {MAX_RETRIES} times in a row")


def get_spot(symbol: str = UNDERLYING) -> float:
    request = StockLatestTradeRequest(symbol_or_symbols=symbol)
    result = _retry(lambda: _get_stock_data_client().get_stock_latest_trade(request), "get_spot")
    return float(result[symbol].price)


def _fetch_contracts(
    symbol: str, expiry_dates: list[date], strike_lo: float, strike_hi: float
) -> pd.DataFrame:
    """Reference data: strike, expiry, open interest. Paginates internally
    on next_page_token -- confirmed live that a single narrow strike-band
    query can return exactly 100 rows (the page size) with a non-null
    next_page_token still outstanding, meaning a version of this function
    that stopped after one request could silently truncate the chain."""
    rows = []
    for expiry in expiry_dates:
        page_token = None
        while True:
            request = GetOptionContractsRequest(
                underlying_symbols=[symbol],
                expiration_date=expiry,
                strike_price_gte=str(strike_lo),
                strike_price_lte=str(strike_hi),
                # The Alpaca API defaults to calls only when `type` is omitted --
                # confirmed empirically (an unfiltered request returned 200 calls
                # and 0 puts). This strategy only ever trades put credit spreads,
                # so puts are the only thing worth asking for.
                type=ContractType.PUT,
                page_token=page_token,
            )
            result = _retry(
                lambda r=request: _get_trading_client().get_option_contracts(r),
                f"get_option_contracts({expiry}, page_token={page_token})",
            )
            for c in result.option_contracts:
                rows.append(
                    {
                        "symbol": c.symbol,
                        "expiry": c.expiration_date,
                        "right": "C" if str(c.type).lower().endswith("call") else "P",
                        "strike": float(c.strike_price),
                        "open_interest": int(c.open_interest) if c.open_interest is not None else 0,
                        "tradable": bool(c.tradable),
                    }
                )
            page_token = result.next_page_token
            if not page_token:
                break
            time.sleep(0.3)
        time.sleep(0.3)
    return pd.DataFrame(rows)


def _fetch_snapshots(expiry_dates: list[date], strike_lo: float, strike_hi: float) -> pd.DataFrame:
    """Live pricing: bid/ask/mid, implied volatility, delta. One request per
    expiry, narrowed by strike range server-side -- an unfiltered chain query
    can return thousands of contracts (Gotchas)."""
    rows = []
    for expiry in expiry_dates:
        request = OptionChainRequest(
            underlying_symbol=UNDERLYING,
            expiration_date=expiry,
            strike_price_gte=str(strike_lo),
            strike_price_lte=str(strike_hi),
            type=ContractType.PUT,  # same default-to-calls behavior as the trading API
        )
        result = _retry(lambda r=request: _get_option_data_client().get_option_chain(r), f"get_option_chain({expiry})")
        for sym, snap in result.items():
            quote = snap.latest_quote
            bid = float(quote.bid_price) if quote and quote.bid_price else None
            ask = float(quote.ask_price) if quote and quote.ask_price else None
            mid = (bid + ask) / 2 if bid is not None and ask is not None else None
            delta = snap.greeks.delta if snap.greeks is not None else None
            rows.append(
                {
                    "symbol": sym,
                    "bid": bid,
                    "ask": ask,
                    "mid": mid,
                    "iv": float(snap.implied_volatility) if snap.implied_volatility else None,
                    "delta": float(delta) if delta is not None else None,
                }
            )
        time.sleep(0.3)
    return pd.DataFrame(rows)


def fetch_chain(
    expiry_dates: list[date],
    spot: float | None = None,
    strike_pad_pct: float = 0.15,
    symbol: str = UNDERLYING,
) -> pd.DataFrame:
    """Merged reference + live pricing for `symbol`'s chain, restricted to
    `expiry_dates` and strikes within `strike_pad_pct` of spot. Returns a
    DataFrame with one row per contract; empty if nothing matched, never
    raises on empty results (a data-sanity guard handles that upstream).
    """
    if spot is None:
        spot = get_spot(symbol)
    strike_lo = round(spot * (1 - strike_pad_pct), 2)
    strike_hi = round(spot * (1 + strike_pad_pct), 2)

    contracts = _fetch_contracts(symbol, expiry_dates, strike_lo, strike_hi)
    if contracts.empty:
        return contracts

    snapshots = _fetch_snapshots(expiry_dates, strike_lo, strike_hi)
    merged = contracts.merge(snapshots, on="symbol", how="left")
    return merged


def fetch_option_mids(symbols: list[str]) -> dict[str, float | None]:
    """Live mid price for a small, known set of option symbols -- used by
    monitor.py to re-price an already-open spread every cycle, where the
    full chain fetch (fetch_chain) would be needlessly wide."""
    if not symbols:
        return {}
    request = OptionLatestQuoteRequest(symbol_or_symbols=symbols)
    quotes = _retry(lambda: _get_option_data_client().get_option_latest_quote(request), "get_option_latest_quote")
    mids = {}
    for sym in symbols:
        quote = quotes.get(sym)
        bid = float(quote.bid_price) if quote and quote.bid_price else None
        ask = float(quote.ask_price) if quote and quote.ask_price else None
        mids[sym] = (bid + ask) / 2 if bid is not None and ask is not None else None
    return mids


def liquidity_filter(chain_df: pd.DataFrame, min_oi: int = 500, max_spread_pct: float = 0.15) -> pd.DataFrame:
    """Guard #11: open interest >= min_oi, bid-ask spread <= max_spread_pct of
    mid, both legs quoted."""
    if chain_df.empty:
        return chain_df
    has_quote = chain_df["bid"].notna() & chain_df["ask"].notna() & chain_df["mid"].notna() & (chain_df["mid"] > 0)
    spread_pct = (chain_df["ask"] - chain_df["bid"]) / chain_df["mid"].replace(0, pd.NA)
    liquid = (
        has_quote
        & (chain_df["open_interest"] >= min_oi)
        & (spread_pct <= max_spread_pct)
        & chain_df["tradable"]
    )
    # spread_pct's comparison against a pd.NA mid (from the .replace(0,
    # pd.NA) above) propagates NA rather than False through `&`, which some
    # pandas versions reject as a boolean mask -- fillna(False) makes the
    # "not liquid" outcome explicit rather than relying on how NA happens
    # to be handled downstream.
    return chain_df[liquid.fillna(False)].copy()


if __name__ == "__main__":
    from pipeline.options.contracts import expiries_in_window

    today = date.today()
    exps = expiries_in_window(today, 7, 11)
    print(f"Spot check: fetching SPY chain for expiries {exps}")

    spot = get_spot()
    print(f"SPY spot: {spot}")

    df = fetch_chain(exps, spot=spot)
    print(f"{len(df)} contracts fetched")
    if not df.empty:
        # Self-check: prices should generally rise with strike for puts (the
        # right closer to spot is more valuable), sanity, not a strict law.
        puts = df[df["right"] == "P"].dropna(subset=["mid"]).sort_values("strike")
        print(puts[["symbol", "expiry", "strike", "bid", "ask", "mid", "iv", "delta", "open_interest"]].head(20))

        liquid = liquidity_filter(df)
        print(f"{len(liquid)} of {len(df)} pass the liquidity filter (OI >= 500, spread <= 15%)")
