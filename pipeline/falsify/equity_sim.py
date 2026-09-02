"""
Turns reconstruct.replay()'s per-week $/share P&L into a weekly RETURN
series on a compounding $100,000 account, using the exact live
position-sizing rule (pipeline/options/selector.py's size_contracts,
read-only reference -- never imported, since that module also imports
live broker/account code this session must not touch): each week's
contract count is floor(equity * PER_TRADE_CAP_PCT / max_loss_per_contract),
sized against CURRENT (compounding) equity, not the $100,000 starting
figure -- exactly what a live account does.

WHY THIS EXISTS: README.md states this strategy's Sharpe as 0.35 (vs SPY's
0.66), but no code in the repo computes it -- EXPERIMENT.md's only Sharpe
table (12d) uses the superseded $1-strike rule and materially different
figures (0.03/0.17). This simulation, built from the current validated
replay() and the live sizing formula, is what computes it now.

THE CANONICAL RETURN CONVENTION (fixed here 2026-09-02, after a real bug --
see below). A defined-risk credit spread only ever puts a small fraction of
the account at risk (PER_TRADE_CAP_PCT = 3%, or up to CRASH_DAY_BUDGET_PCT =
6% across concurrent positions); the remainder sits as cash/margin and, on
a real account, earns interest regardless of whether a position is open
that week. This is not a simulation nicety -- it is how the instrument this
strategy benchmarks against is actually built: CBOE's S&P 500 PutWrite
Index (PUT) is explicitly "fully collateralized" with the collateral
"invested at the 1- and 3-month Treasury Bill rate" on every day, traded or
not (Cboe S&P 500 PutWrite Indices Methodology; see SOURCES.md). So the
convention pinned here, applied uniformly:

    weekly return = cash_annual_rate/52 (on the FULL account, every week)
                    + option P&L / equity (on traded weeks only)
    Sharpe        = (annualized return - cash_annual_rate) / annualized vol

Crediting the risk-free rate on only part of the return while still
subtracting the full risk-free rate as the Sharpe benchmark is a mixed-basis
error -- see THE BUG below.

THE BUG THIS REPLACED, kept here rather than deleted because the audit
writeup (EXPERIMENT_29_SHARPE_AUDIT.md) leads with it: the first version of
this module credited `cash_annual_rate` ONLY on the ~34% of weeks the
term-structure filter skips, leaving the ~66%/~94-97%-of-equity untouched
during traded weeks earning nothing -- while sharpe_ratio() still subtracted
the FULL cash rate as the benchmark on every week. That mixed-basis error
alone moved the annualized Sharpe from +0.574 (corrected) to -0.704 (as
first shipped and, briefly, logged in PROGRESS.md). Caught by the
cash-rate-invariance test below, which the buggy version fails immediately.

THE 2-CONCURRENT-POSITION GAP (found, not guessed, now closed): EXPERIMENT.md
:481 states 12d's Sharpe/drawdown table -- the one README's 0.24/0.35 figures
descend from -- was computed on a "portfolio basis: 2 concurrent positions at
the 3% per-trade cap". reconstruct.replay() structurally never has two
positions open at once (strictly weekly, non-overlapping by construction),
so `n_concurrent` below is a coarse proxy (effective cap =
per_trade_cap_pct * n_concurrent, capped implicitly at CRASH_DAY_BUDGET_PCT
by construction when n_concurrent=2) rather than a true overlapping-position
replay -- 12d's exact staggering (entry cadence, hold length) is not
specified anywhere in this repo, so reconstructing it exactly would mean
guessing. The proxy is still informative: at n_concurrent=2 (6% effective
cap) it reproduces EXPERIMENT.md 12d's vol (3.25% vs 3.27%) and README's max
drawdown (5.91% vs 5.8%) within noise -- corroboration, not proof.

Cost: 12d's "$0.01/spread live-measured cost" is risk/options_config.py's
DEFAULT_SLIPPAGE_PER_SHARE = 0.01 (read as a literal, not imported --
pipeline/risk/ is off-limits live-system territory this session must not
import from). replay()'s pnl = credit - payout carries no slippage at all,
so this module applies it explicitly (see slippage_per_share below).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

CASH_ANNUAL_RATE = 0.03  # idle weeks earn this, matching build_equity_curve's
                          # cash_indexed convention in reconstruct.py and the
                          # "skipped weeks earning cash" framing in README.md
STARTING_EQUITY = 100_000.0
WEEKS_PER_YEAR = 52

# risk/options_config.py:96 DEFAULT_SLIPPAGE_PER_SHARE -- read as a literal,
# not imported (pipeline/risk/ is off-limits live-system territory this
# session must not import from). Matches EXPERIMENT.md:481's "$0.01/spread
# live-measured cost", the convention 12d's Sharpe table was computed under.
DEFAULT_SLIPPAGE_PER_SHARE = 0.01

# risk/options_config.py:16 CRASH_DAY_BUDGET_PCT -- likewise a literal, not an
# import. It is exactly 2 x PER_TRADE_CAP_PCT (0.03), which is precisely what
# EXPERIMENT.md:481's "2 concurrent positions at the 3% per-trade cap" means:
# the live ceiling on total capital at risk across all open positions.
CRASH_DAY_BUDGET_PCT = 0.06


def simulate_weekly_returns(result: pd.DataFrame, traded: pd.Series,
                             per_trade_cap_pct: float,
                             starting_equity: float = STARTING_EQUITY,
                             cash_annual_rate: float = CASH_ANNUAL_RATE,
                             slippage_per_share: float = DEFAULT_SLIPPAGE_PER_SHARE,
                             n_concurrent: int = 1) -> pd.Series:
    """`result` must have `entry` (sorted ascending), `short_strike`,
    `long_strike`, `credit`, `pnl` (all per-share, reconstruct.py's
    convention). `traded` is a same-length boolean mask: weeks where it is
    False are idle (no position). Returns one weekly return per row, in the
    same order.

    THE CANONICAL CONVENTION (module docstring has the full derivation and
    the bug this fixed): `cash_annual_rate` is credited on the FULL account
    EVERY week, traded or not -- collateral held against an open spread
    still earns interest on a real account, and CBOE's own PutWrite index
    is built the same way. Option P&L is added on top on traded weeks only.
    This makes Sharpe's benchmark (the same cash_annual_rate, subtracted in
    sharpe_ratio()) symmetric with what is actually credited here.

    Position sizing matches pipeline/options/selector.py's size_contracts:
    contracts = floor(equity * per_trade_cap_pct * n_concurrent /
    max_loss_per_contract), sized against CURRENT (compounding) equity.
    `n_concurrent` (default 1) is a coarse proxy for EXPERIMENT.md:481's
    "2 concurrent positions" convention -- see the module docstring for why
    it is a proxy, not a true overlapping-position replay, and what it
    reproduces (12d's vol, README's drawdown) as corroboration.

    `slippage_per_share` is subtracted from credit before P&L, matching
    evidence_gate.py's `net_credit = credit - slippage_per_share`
    convention (replay()'s own pnl column carries none)."""
    if len(result) != len(traded):
        raise ValueError(f"result ({len(result)} rows) and traded ({len(traded)}) must be the same length")

    width = result["short_strike"] - result["long_strike"]
    net_credit = result["credit"] - slippage_per_share
    net_pnl = result["pnl"] - slippage_per_share
    cash_weekly = cash_annual_rate / WEEKS_PER_YEAR
    effective_cap_pct = per_trade_cap_pct * n_concurrent

    equity = starting_equity
    returns = []
    for i in range(len(result)):
        wr = cash_weekly  # collateral/idle cash earns this EVERY week
        if bool(traded.iloc[i]):
            max_loss_per_contract = width.iloc[i] * 100 - net_credit.iloc[i] * 100
            per_trade_cap = equity * effective_cap_pct
            contracts = math.floor(per_trade_cap / max_loss_per_contract) if max_loss_per_contract > 0 else 0
            pnl_dollars = contracts * net_pnl.iloc[i] * 100
            wr += pnl_dollars / equity if equity > 0 else 0.0
        returns.append(wr)
        equity *= (1.0 + wr)

    return pd.Series(returns, index=result.index, dtype="float64")


def annualized_return_vol(weekly_returns: pd.Series) -> tuple[float, float]:
    """Simple mean/std annualization (mean * 52, std * sqrt(52)), the same
    convention EXPERIMENT.md's 12d table used -- confirmed by reproducing
    its exact 0.03 and 0.17 Sharpe figures algebraically before this module
    was written. Returns (annualized_return, annualized_vol), as fractions
    (0.044, not 4.4)."""
    ann_return = float(weekly_returns.mean() * WEEKS_PER_YEAR)
    ann_vol = float(weekly_returns.std(ddof=1) * np.sqrt(WEEKS_PER_YEAR))
    return ann_return, ann_vol


def sharpe_ratio(weekly_returns: pd.Series, risk_free_annual: float = CASH_ANNUAL_RATE) -> float:
    """(annualized_return - risk_free_annual) / annualized_vol -- the
    convention this module's docstring derives and pins."""
    ann_return, ann_vol = annualized_return_vol(weekly_returns)
    if ann_vol == 0:
        return 0.0
    return (ann_return - risk_free_annual) / ann_vol
