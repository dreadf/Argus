"""
The numeric limits from OPTIONS_SYSTEM_PLAN.md Part 5/6. All percentages are
of CURRENT equity, not starting equity (Part 6's "exact decision logic"
section) -- guards.py re-reads these against live account state each cycle,
never a fixed starting-balance number.
"""

PER_TRADE_CAP_PCT = 0.03           # Guard #4: max loss on one spread
CRASH_DAY_BUDGET_PCT = 0.12        # Guard #5: max combined loss, all open positions
MAX_CONCURRENT_POSITIONS = 4       # Guard #6

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
