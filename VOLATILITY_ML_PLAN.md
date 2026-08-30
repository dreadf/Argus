# Volatility ML Plan

Research track for the options system. Replaces `ML_Experiment_Plan.md` as the
active research plan.

The 5-day direction question is closed with a documented negative answer in
`EXPERIMENT.md`, Experiments 0 to 10. Experiment 10 in particular re-measured
Experiments 8 and 9 with cross-sectional IC instead of AUC and found both
indistinguishable from zero (t = -0.73 and -1.13), confirming that the apparent
AUC improvement across Experiments 7 to 9 was noise throughout.

**Numbering here continues from 11.**

## The reframe: we have been predicting the wrong quantity twice over

There are **three** different things we could predict, and they are not interchangeable. Getting this distinction right is most of the value of this section.

| # | Target | The question | Makes money? |
|---|---|---|---|
| 1 | **Direction** | Will SPY go up or down? | ❌ Closed. Nine experiments. No. |
| 2 | **Realized volatility** | How far will SPY move? | ⚠️ Only indirectly |
| 3 | **The premium (IV − RV)** | Are options *overpriced* relative to what actually happens? | ✅ **This is the actual money question** |

We shifted from #1 to #2 earlier in this conversation. That was an improvement, but **#3 is the real target.** Here's why the difference matters:

> Suppose we predict perfectly that SPY will move 2% next week. Useful? Only if we also know what the market *charged* for that risk. If they priced 3% of movement, we profit. If they priced 1%, we lose - **with the exact same, perfectly accurate forecast.**

Volatility forecasting alone doesn't tell us whether a trade is good. The *gap between what's priced and what happens* does.

## What the research says (checked before planning, per standing project rule)

**On ML vs. the simple baseline - evidence is genuinely mixed, and the split is informative:**
- HAR-RV and regime-switching HAR "consistently outperform both machine learning approaches and standard linear benchmarks, **especially when the information set is limited**" ([Financial Innovation review](https://link.springer.com/article/10.1186/s40854-025-00809-5), 2006–2023 study)
- But XGBoost beat HAR and LSTM on Dow stocks by MSE and QLIKE ([comparative study](https://www.diva-portal.org/smash/get/diva2:2031701/FULLTEXT01.pdf)), and ML "significantly improves prediction relative to HAR" in **data-rich environments with a large feature space** ([Journal of Financial Econometrics](https://academic.oup.com/jfec/article/22/2/492/7081291))

**Read that split honestly: our information set is limited** - daily bars, one asset, ~13 features. That is the regime where the literature says HAR wins. **Our prior should be that HAR-RV beats XGBoost here**, and Experiment 11 is designed to confirm or refute that, not to justify ML.

**On the premium (target #3):** Bollerslev, Tauchen & Zhou (2009) is the canonical work - the IV−RV gap predicts returns, most strongly at quarterly horizons ([Duke/RFS](https://public.econ.duke.edu/~boller/Published_Papers/rfs_09.pdf)). **Critical caveat for us:** their results "depend crucially on the use of *model-free* implied volatilities, along with accurate realized variation measures constructed from **high-frequency intraday, as opposed to daily, data**." We have daily data and Black-Scholes-style IV. **Our version of this measurement is structurally weaker than the published one, and the plan must say so rather than cite the paper as if it transfers cleanly.**

**On whether accuracy even matters:** "A more accurate implied volatility calculation **does not promise better performance in the real market**" ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1059056020302513)). This is why Experiment 12 exists as a separate gate - a better R² is not a better strategy, and we test the two separately.

**On what already exists (so we don't claim novelty we don't have):** IV/RV ratio filtering to find overpriced options and IV-rank floors as entry gates are **already standard practice** in existing open-source bots ([earnings-trade-automation](https://github.com/ProgramComputer/earnings-trade-automation), [SPY options platform](https://github.com/IgorGanapolsky/trading)). Our IV−RV gate is table stakes, not innovation. What's ours is the falsification discipline around it.

## The experiment ladder

Same philosophy as the equity track: **start with the dumbest thing that works, and make every addition prove itself.** Each experiment has a gate; failing the gate means stop, not "try harder."

### Experiment 11 - Can we forecast SPY volatility at all?

- **Target:** forward 7–11 day realized volatility, on log scale, annualized (log because vol is right-skewed; annualized so it's comparable to IV)
- **Contenders, in order of stupidity:**
  1. **Naive** - next week's vol = this week's vol
  2. **HAR-RV** - weighted average of yesterday's, last week's, last month's vol. Three inputs, one linear regression.
  3. **XGBoost** - your existing SPY features (`volatility_5/10`, `ATR_5/10`, `RSI`, `momentum_*`, `volume_spike`)
- **Metrics:** QLIKE (the field standard - punishes *under*-predicting vol harder than over-predicting, which matches our actual risk), MSE on log-vol, and R²
- **Validation:** walk-forward, purged, non-overlapping t-stats - identical discipline to `eval.py:38`
- **⛔ Gate:** XGBoost ships **only** if it beats HAR-RV on QLIKE across *multiple* walk-forward windows, not one. Per the literature, expect it not to. **"HAR-RV wins" is a perfectly good result and ships HAR-RV.**

### Experiment 12 - Does forecasting accuracy actually make money?

The experiment the research says most people skip.

- **What:** take Experiment 11's winner. Feed it into the spread backtest two ways - (a) as a skip filter (don't trade when high vol forecast), (b) as a distance scaler (sell further out when vol forecast is high)
- **Compare against:** the same strategy with **no** forecast at all
- **Metric:** P&L and win-rate cushion on the *same* 120 weeks, net of costs
- **⛔ Gate:** the forecast layer ships only if it improves the cushion by more than its own standard error. **A model that forecasts well but doesn't improve trading gets logged and dropped.**
- **Multiple-testing warning:** this is now a second layer of selection on the same 120 observations. Log every variant tried, per `TRADING_SYSTEM_PLAN.md:411`.

### Experiment 13 - Predict the premium directly (the real target)

- **The unlock:** we cannot get historical implied volatility from Alpaca - but **we can reconstruct an implied-probability series from the expired option prices we already have.** `credit ÷ width` *is* the market's implied breach probability, in dollars, no Black-Scholes needed. That gives a usable market-expectation series back to ~Feb 2024.
- **Target:** `implied_breach_prob − realized_breach_outcome` - literally "how wrong was the market's pricing this week"
- **Features:** current implied level, its percentile vs. recent history (IV rank), realized vol, the current gap, recent SPY moves
- **Question:** is the premium *predictable*, or just noisy-positive-on-average? If we can tell rich weeks from cheap weeks in advance, that's a real timing edge and it beats trading every week blindly.
- **⛔ Gate:** must beat "always trade" on the same non-overlapping sample, by more than one standard error.
- **Honest limitation to state:** daily data + reconstructed implied probabilities is a weaker instrument than the published literature's intraday model-free approach. We are measuring a blurrier version of the real quantity.

### Experiment 14 - Feature ablation: does `news_count` finally earn its place?

A genuine callback. Experiment 9's own research check found news volume predicts **volatility and tail risk better than direction** - and `news_count` then ranked dead last of 18 features for *direction*. **It was the right feature pointed at the wrong target.**

- **What:** the Experiment 3 ablation structure, on the volatility target. Groups: (A) vol history, (B) price/technical, (C) volume/`trade_count`, (D) **`news_count`**
- **Question:** does news volume add incremental volatility-forecasting power over vol history alone?
- **Why it matters:** if yes, that's a clean, self-contained, research-predicted result - a feature that failed one question and succeeded on another, which is a genuinely good story and costs us nothing to test since the data is already fetched.

### Experiment 15 - Does the 40-stock panel add anything?

Reuses `panel.py`, which would otherwise be dead code.

- **Idea:** market-wide *dispersion* (how differently the 40 stocks are moving) and average pairwise correlation are known leading indicators of index volatility. When correlations spike, index vol spikes.
- **Features:** cross-sectional std of daily returns across the 40 symbols; rolling average correlation
- **⛔ Gate:** must improve on Experiment 11's winner out of sample. If not, `panel.py` is retired honestly rather than kept for sentiment.

## Ordering, and what to test after this hackathon

| Priority | Experiment | Why this order |
|---|---|---|
| 1 | **10** | Everything downstream needs a volatility forecast that's been checked against a dumb baseline |
| 2 | **11** | Cheap, and it can kill the whole ML track early if forecasting doesn't convert to profit. Better to learn that before building more. |
| 3 | **12** | The real money question, but needs the reconstructed implied series from Exp 11/11 infrastructure |
| 4 | **13** | Self-contained, data already on disk, research-predicted, nice story |
| 5 | **14** | Most speculative, reuses the most existing code |

**Within the hackathon window, only Experiment 11 is realistically in scope** (Wednesday, timeboxed to 2h). **13 to 15 are the post-hackathon research track** - which is the honest way to end the write-up: here's what we tested, here's what we'd test next, here's why in that order.

---
