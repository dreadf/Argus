"""
The numeric limits from OPTIONS_SYSTEM_PLAN.md Part 5/6. All percentages are
of CURRENT equity, not starting equity (Part 6's "exact decision logic"
section) -- guards.py re-reads these against live account state each cycle,
never a fixed starting-balance number.
"""

PER_TRADE_CAP_PCT = 0.03           # Guard #4: max loss on one spread
# Guard #5: max combined loss, all open positions. Was 0.12, which EXCEEDS
# DRAWDOWN_HARD_PCT (0.08) below -- a single bad day across concurrent
# same-distance SPY spreads (one correlated bet, not several diversified
# ones) could realize more loss than the amount meant to trigger the halt,
# making Guard #14 unreachable in the exact scenario it exists for. Set
# below the hard stop so the halt can actually bind; leaves room for 2
# positions at the 3% per-trade cap rather than the nominal 4.
CRASH_DAY_BUDGET_PCT = 0.06
MAX_CONCURRENT_POSITIONS = 4       # Guard #6 -- left at 4; CRASH_DAY_BUDGET_PCT is what binds

NET_DELTA_CAP_SHARE_EQUIV = 150    # Guard #7, ~$115k notional at $769 spot


# Guard #8: credit/width sanity band. The plan's original 0.08 floor was a
# judgment call (Part 9B: "chosen", not measured). First fix: lowered to
# 0.04 after confirming it would otherwise block every cell the evidence
# gate approved (3% distance survivors AVERAGE 0.055-0.068 credit/width).
#
# The false-trip test (pipeline/risk/false_trip.py) then found that even
# 0.04 was still wrong: the WEEKLY ratio at these survivors has enormous
# variance (mean 0.067, std 0.059, range -0.02 to 0.37 at 3%/$1) because a
# $1-wide, 3%-OTM spread often prices in single pennies. A static floor
# meaningfully above zero blocks 42-50% of real winning weeks -- far above
# the plan's own 30% false-trip bar. Per Part 6's own instruction ("a guard
# that blocks 40% of winners... should be loosened or dropped"), the floor
# is set to 0.0: it still catches a genuinely broken quote (negative or
# zero credit), while the real economic screening -- which distances/widths
# are worth trading at all, and how much can be lost -- is already done by
# the evidence gate and the per-trade/crash-day dollar caps, not by this
# guard re-litigating each week's ratio.
CREDIT_WIDTH_MIN = 0.0
CREDIT_WIDTH_MAX = 0.35            # Guard #8: above this, too close (negative-premium zone); false-trip tested, 1/123 blocked

MIN_DTE = 7                        # Guard #9
MAX_DTE = 11                       # Guard #9

MIN_OPEN_INTEREST = 500            # Guard #11
MAX_BID_ASK_SPREAD_PCT = 0.15      # Guard #11
# Guard #11 extension: order size must also stay a small fraction of quoted
# depth, not just clear the absolute open-interest floor above. Without
# this, size_contracts (which sizes purely off equity-based dollar caps) can
# propose more contracts than the market can realistically absorb once
# equity is large enough -- worked out by hand that this crosses the
# MIN_OPEN_INTEREST floor itself at roughly $1.08M equity on the narrowest
# evidence-gate-tested width. 10% of open interest is a conservative,
# round-number ceiling; nothing in Experiment 11 depends on the exact value.
MAX_CONTRACTS_PCT_OF_OPEN_INTEREST = 0.10

VOL_REGIME_RV_THRESHOLD = 0.25     # Guard #12: annualized RV(10d) above this = skip
SPY_DAILY_MOVE_THRESHOLD = 0.02    # Guard #12: yesterday's |move| above this = skip

DRAWDOWN_SOFT_PCT = 0.05           # Guard #13: stop opening new positions
DRAWDOWN_HARD_PCT = 0.08           # Guard #14: close everything, halt

PROFIT_TARGET_PCT = 0.50           # monitor.py exit #1: close at this fraction of credit remaining
# The 2-SE evidence-gate bar itself is owned by backtest/evidence_gate.py's
# SE_THRESHOLD -- this used to be a second, unreferenced copy of the same
# number here.

FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT = 0.30  # false-trip test bar for any guard/exit rule

# T2 fix: the evidence gate's tie-break (selector.choose_distance_width) used
# to pick the highest cushion_se with no cost model, which is highest
# exactly where credit is thinnest -- 3%/$1's mean P&L falls from $0.052 to
# -$0.048 at a 4c/spread haircut, so the gate was recommending the cell
# trading costs destroy.
#
# The number below is MEASURED, not assumed. A first attempt used an
# invented 2c/leg (4c/spread), reasoned loosely from an old docstring
# claiming "$0.01-$0.05 wide" quotes -- plugged into the gate's existing
# (already cost-aware, but previously always fed 0.0) required_win_rate
# formula, that guess emptied the evidence gate entirely: zero cells clear
# 2 SE at 4c/spread. Rather than pick a smaller number because it keeps a
# trade alive (exactly the guard-fitting pattern Guard #8's 0.08->0.04->0.0
# history is a documented warning against), this was replaced with a live
# measurement: fetched the real chain (2026-09-01, spot $766.87, 8 DTE) and
# read the actual bid/ask on both legs of every (distance, width) cell the
# gate considers. Every liquid candidate (OI in the hundreds to tens of
# thousands) quoted at the $0.01 minimum tick, both legs, at every distance
# from 2% to 4%. Using the standard half-spread-per-leg convention (Rule
# #8 limits at mid, so the expected cost of a marketable limit is roughly
# half the quoted spread per leg): 0.005 + 0.005 = $0.01/spread.
#
# Known limitation: this is one snapshot on one calm day. Spreads widen in
# stress, which is exactly when the VIX term-structure guard (Wednesday's
# work) is designed to skip trading anyway, so the two are not independent,
# but this number should not be treated as a stress-period estimate.
DEFAULT_SLIPPAGE_PER_SHARE = 0.01
