UNDERLYING = "SPY"

DTE_MIN = 7
DTE_MAX = 11

# SPY lists expiries on Monday, Wednesday, and Friday.
EXPIRY_WEEKDAYS = (0, 2, 4)

# Swept together in the backtest (Part 2B); nothing here is a fixed decision
# until the evidence gate picks a distance.
DISTANCE_TARGETS = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06)
WIDTH_TARGETS = (1, 2, 5, 10)
