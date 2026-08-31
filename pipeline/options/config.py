UNDERLYING = "SPY"

# DTE window lives in risk/options_config.py (MIN_DTE/MAX_DTE) -- Guard #9's
# owner, and the only place these were ever actually read from (this file
# used to carry its own DTE_MIN/DTE_MAX, unreferenced anywhere).

# SPY lists expiries on Monday, Wednesday, and Friday.
EXPIRY_WEEKDAYS = (0, 2, 4)

# Swept together in the backtest (Part 2B); nothing here is a fixed decision
# until the evidence gate picks a distance.
DISTANCE_TARGETS = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06)
WIDTH_TARGETS = (1, 2, 5, 10)
