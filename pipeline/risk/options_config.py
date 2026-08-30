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
# judgment call (Part 9B: "chosen", not measured) and, checked against the
# real Experiment 11 backtest, would have blocked EVERY (distance, width)
# cell the evidence gate actually approved -- the 3% distance survivors
# measure 0.055 to 0.068 credit/width, all below 0.08. Lowered to 0.04, well
# under the measured survivors, so this guard still catches a clearly broken
# quote (near-zero credit) without relitigating what the evidence gate
# already approved on stronger statistical grounds.
CREDIT_WIDTH_MIN = 0.04
CREDIT_WIDTH_MAX = 0.35            # Guard #8: above this, too close (negative-premium zone)

MIN_DTE = 7                        # Guard #9
MAX_DTE = 11                       # Guard #9

MIN_OPEN_INTEREST = 500            # Guard #11
MAX_BID_ASK_SPREAD_PCT = 0.15      # Guard #11

VOL_REGIME_RV_THRESHOLD = 0.25     # Guard #12: annualized RV(10d) above this = skip
SPY_DAILY_MOVE_THRESHOLD = 0.02    # Guard #12: yesterday's |move| above this = skip

DRAWDOWN_SOFT_PCT = 0.05           # Guard #13: stop opening new positions
DRAWDOWN_HARD_PCT = 0.08           # Guard #14: close everything, halt

PROFIT_TARGET_PCT = 0.50           # monitor.py exit #1: close at this fraction of credit remaining
EVIDENCE_GATE_SE_THRESHOLD = 2.0   # matches backtest/evidence_gate.py's SE_THRESHOLD

FALSE_TRIP_MAX_BLOCKED_WINNERS_PCT = 0.30  # false-trip test bar for any guard/exit rule
