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

# Rule #4 fix (Build Step 7, post-live-run correction): the live run picked a
# $1-odd short strike ($746) and was blocked by the liquidity guard -- real
# open interest 22 against the 500 minimum. SPY open interest concentrates on
# $5/$10 increments, not every $1 strike. Rounding the short-leg target down
# to this increment before searching the listed chain buys MORE distance
# from spot (never less, so no riskier than the evidence gate measured) and
# lands on a strike the market actually has depth in.
LIQUID_STRIKE_INCREMENT = 5
