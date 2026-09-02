# Trading System — Foundation Plan

**Status: design only. No code written yet.**

Companion to `ML_Experiment_Plan.md` (the model) and `Project_Context_and_Plan_Updated.md` (the Phase 3/4 spec).

This document explains what the trading system is, why it can be built *in parallel with* the ML
experiments instead of after them, and in what order to build it.

- **Part 1** is the idea in plain words. Read this first. No code.
- **Part 2** is the technical detail. Read it when you sit down to write code.
- **Part 3** is a glossary of the terms used here.

---
---

# PART 1 — The idea, in plain words

## 1. What is missing right now

The model has exactly one job: put a number next to each stock.

```
2026-08-21   AAPL   0.71
2026-08-21   TSLA   0.34
2026-08-21   KO     0.52
```

Higher number = the model likes that stock more. That is the whole output. The model knows nothing about
money, orders, fees, or risk.

The **trading system** is everything that comes after: turning those numbers into actual trades, and
checking whether those trades would have made money.

The repo currently has **none of it**. Searching the code for "backtest", "sharpe", or "order" only finds
those words inside the planning documents. So this is genuinely empty ground — nothing to refactor, and
nothing to be careful of breaking.

## 2. Why it can be built now, before the model works

The trading system needs exactly one thing from the model: a list of **date + stock + number**.

It does not care where the number came from.

That means you can build the entire trading system today and feed it **fake numbers** while testing. Later,
when the model finally produces something worth trading, you swap the fake numbers for the model's numbers.
Nothing else in the system changes.

> **Analogy.** You are building a machine that counts money. You do not need real money to test it. Play
> money works fine, and it is a lot safer to make mistakes with.

This is why the two tracks can run side by side. The ML track keeps experimenting. The trading track builds
the machine. They meet at one small, simple contract: that list of numbers.

## 3. What the trading system actually does

Imagine it is Friday. You have your 40 stocks with a number next to each. Here is everything that happens:

1. **Sort** the 40 stocks, highest number to lowest.
2. **Take both ends.** Buy the best 8. *Short* the worst 8.
   (**Short** = betting a stock goes *down*. You borrow shares, sell them now, and buy them back later —
   cheaper, if you were right.)
3. **Check the shorts are allowed.** Not every stock can be shorted. Alpaca tells you which ones can.
   Drop the ones you cannot short, and refill those slots with the next-worst stocks on the list.
4. **Balance the two sides.** Put roughly the same amount of money into the buys as into the shorts. Then
   if the whole market falls, the two sides cancel each other out, and what is left is only the part you
   actually predicted. That is the point of doing both sides.
5. **Apply limits.** No more than 5% of your money in one stock. No more than 30% in one sector. If fewer
   than 4 stocks survive on either side, skip the week entirely.
6. **Replay history.** Do all of the above every Friday from 2020 until now, on paper, and see whether the
   money grows — *after* subtracting trading fees.
7. **Stop rules.** If it starts losing consistently, stop opening new positions automatically.
8. **Go live, on paper.** Send real orders to an Alpaca paper-trading account.
9. **Write everything down.** Every number, every decision, every order — so you can explain afterwards why
   the system did what it did.

**Steps 1 through 9 need the model for nothing.** Not one of them. That is the whole argument.

## 4. The most important habit: test the ruler before you measure with it

Step 6 above — replaying history — is called a **backtest**. It is also the easiest thing in this entire
project to get quietly, invisibly wrong. A buggy backtest does not crash. It prints a plausible-looking
number that happens to be a lie.

So before trusting it, feed it two fake signals where you already know what the answer *has* to be:

| Fake signal | What it is | The backtest **must** report |
|---|---|---|
| **The cheat** | It peeks at what actually happened next, and ranks the stocks perfectly | a huge profit |
| **The coin flip** | Pure random numbers, zero information | roughly zero — and slightly negative once fees are subtracted |

If the cheat does not make a fortune, your backtest is broken. If the coin flip makes money, your backtest
is broken. Fix it before believing anything else it says.

> **Analogy.** Before trusting a kitchen scale, put a known 1 kg weight on it. If it reads 1.4 kg, you do
> not start weighing flour. You fix the scale.

Why this matters *here* specifically: if you plug the real model in first and it earns nothing, you cannot
tell whether the model is bad or the backtest has a bug. The two fake signals separate those questions
completely, and cost almost nothing to write.

## 5. What to build first — it solves an ML problem at the same time

`EXPERIMENT.md` ends with a list of revised next steps. Number 1 is:

> Change the evaluation metric from accuracy/AUC to cross-sectional IC and long/short quintile spread.

Here is the useful part: **that is not ML code. That is trading-system code.**

"IC" sounds intimidating. The idea is simple:

1. Today, list the 40 stocks in the order the model likes them.
2. One week later, list them again — this time in the order they *actually* performed.
3. Compare the two orderings. How similar are they? That gives a score between −1 and +1.
4. Repeat for every day, then take the average.

That average is the IC.

| IC | What it means |
|---|---|
| `0.00` | the model's ordering has nothing to do with reality |
| `0.02 – 0.05`, **and steady over time** | a real, tradeable edge — small-sounding, but genuinely real |
| negative | the model is reliably *backwards* (this is what Experiment 6b already found) |

The word "steady" is doing heavy lifting there. A single good IC in one time window means nothing; this
project has already been fooled once that way (Experiment 2's 0.580 AUC did not survive Experiment 2b).

So building the IC calculator gives you two things from one piece of work:

- the first component of the trading system, **and**
- the exact measurement the ML track is currently stuck without.

That is why it is first on the build list.

## 6. Honest warning before any of this starts

Building the machine is not the same as being allowed to use it.

`Project_Context_and_Plan_Updated.md` already sets gates that must pass before any real trading: a positive
and *stable* IC across several separate time windows, and a profit that survives after fees are subtracted.
The model does not currently pass them — Experiment 8 produced 0.502, which is essentially a coin flip.

That is fine, and it does not block this work. Build the machine, and drive it with a simple rule-based
signal instead of the model. A complete trading system that correctly **refuses** to trade a signal with no
edge is a stronger result than one that trades it and loses money.

---
---

# PART 2 — The technical detail

Read this part when you are ready to write code. Every section opens with one sentence saying what it is for.

## 7. The one contract everything depends on

*What this is for: the single data shape that connects any signal to the rest of the system.*

```python
# scores: pd.DataFrame with columns ['timestamp', 'symbol', 'score']
#   - one row per (date, stock) that the signal has an opinion about
#   - higher score = more attractive = more likely to be bought.
#     This sign convention is decided once, here, and never re-litigated.
#   - a stock missing on a date means "no opinion" -> excluded from the book that day. NOT zero.
```

Long format, because `build_panel_data()` in `pipeline/panel.py` already produces long format. That means no
reshaping at the boundary.

Everything below is a function of this frame plus prices. Nothing else.

## 8. Layer 0 — Signal sources (`pipeline/signals/`)

*What this is for: producing `scores`. Four of the five sources are fake on purpose.*

```python
def score(panel_df) -> pd.DataFrame:   # ['timestamp', 'symbol', 'score']
```

| Source | What it does | Why it exists |
|---|---|---|
| `random_signal` | uniform random numbers | the zero floor. Backtest must show ≈0, negative after fees. |
| `oracle_signal` | ranks by the actual `fwd_5d_return` | **deliberately cheating.** Must show a huge profit. If it does not, the *backtest* is broken. |
| `planted_ic_signal(rho)` | blends the true future ranking with noise, tuned so the IC comes out at a chosen value | the calibration weight. Feed in IC 0.03, the analytics must measure ≈0.03 back. |
| `momentum_signal` | ranks by `momentum_10` or `residual_momentum_20` | a real signal with no ML in it. Lets the whole stack run end to end today. |
| `model_signal` | wraps `predict_proba` from the pooled XGBoost | the eventual plug-in. Write it last; it is about 10 lines. |

`planted_ic_signal` is not optional. Phase 3 requires a **false-trip test** before any stop rule threshold is
adopted ("simulate a synthetic signal with a known-positive IC and measure how often the kill-switch fires
incorrectly"). That test is impossible without this function. Building it early pays for itself three times.

## 9. Layer 1 — Measuring a signal (`pipeline/eval/`)

*What this is for: answering "does this signal rank stocks correctly, and does it keep doing so?" before any
portfolio exists.*

```python
def daily_ic(scores, fwd_returns, method='spearman') -> pd.Series   # one IC value per date
def ic_summary(ic_series, overlap=5) -> dict    # mean, std, t-stat on non-overlapping dates, n_eff
def quantile_returns(scores, fwd_returns, n=5) -> pd.DataFrame      # avg forward return per group per date
def long_short_spread(quantile_returns) -> pd.Series                # best group − worst group
def ic_decay(scores, prices, horizons=(1, 3, 5, 10)) -> pd.Series   # is 5 days even the right horizon?
def signal_autocorr(scores) -> float             # how much the ranking changes day to day -> implies turnover
```

**One detail that cannot be skipped: the t-statistic.** A t-statistic answers "could this result be luck?"
(|t| > 2 is the usual bar for "probably not"). But `EXPERIMENT.md` established that 5-day overlapping labels
inflate t by roughly √5, and that the real number of independent observations here is about 1,000, not
65,000. So `ic_summary` must compute t on **non-overlapping dates** — take every 5th date — as the headline
number. Newey-West adjustment is a useful cross-check, not the primary. Make the overlap length an explicit
parameter so it can never be silently forgotten.

**How to test this with no model:** run the five signal sources through it. IC(random) ≈ 0, IC(oracle) ≈ 1,
IC(planted 0.03) ≈ 0.03. If those three hold, the analytics are trustworthy.

**Done when:** you can hand it any `scores` frame and get back a one-page verdict — mean IC, its t-statistic
on independent observations, the long/short spread, and the decay curve.

## 10. Layer 2 — Portfolio construction (`pipeline/risk/portfolio_construction.py`)

*What this is for: turning one day's scores into how much money goes into each stock, subject to the limits.*

Phase 3 already specifies the **exact order of operations**, and the order matters — running the steps in a
different sequence produces a different portfolio.

```python
def rank_and_split(scores_on_date, quantile=0.2) -> (longs, shorts)
def filter_shortable(shorts, asset_flags) -> shorts         # drop what cannot be borrowed
def backfill_shorts(ranked, kept_shorts, asset_flags, target_n)   # refill from the next-worst names
def match_notional(longs, shorts, max_net_pct)              # trim the weakest longs only if needed
def apply_concentration_caps(weights, sector_map, caps)     # per-stock, per-sector, minimum count
def compute_net_beta(weights, betas) -> float               # monitor; escalate if |beta| > 0.15
def build_book(scores_on_date, asset_flags, sector_map, betas, cfg) -> pd.Series   # symbol -> weight
```

Every one of these is a **pure function** — no API calls, no file reads, no market data. That makes this the
one place in the project where unit tests genuinely earn their keep: a fixture of 6 fake stocks with
hand-computed expected weights will catch ordering bugs that a backtest would silently absorb into noise.

Note that `beta_60` already exists — `add_market_features()` in `pipeline/panel.py` computes it. The net-beta
monitor's input is already sitting in the panel.

**Missing input:** `sector_map`. Sector membership currently exists only as *comments* in
`pipeline/config.py`. The per-sector cap cannot be enforced until that becomes a real dictionary. Cheapest
task in this document, and a hard dependency.

## 11. Layer 3 — Backtester (`pipeline/backtest/`)

*What this is for: answering "would this portfolio have made money, after fees?"*

```python
def run_backtest(weights_by_date, prices, cost_cfg) -> BacktestResult
    # equity curve, per-period returns, trade log, turnover, realized net beta, per-leg attribution
def apply_costs(turnover, short_notional, cost_cfg) -> pd.Series
def metrics(result) -> dict     # cumulative return, annualized, volatility, Sharpe, max drawdown, hit rate
```

**The entire honesty of a backtest lives in one line.** Weights decided using information available at the
close of day *t* must be multiplied by the returns of day *t+1* onward:

```text
period_pnl = (weights.shift(1) * forward_returns).sum(axis=1) − costs
                       ^^^^^^^
              this shift is the whole thing
```

Get that shift right and a simple vectorized backtest (whole arrays at once, no event loop) is perfectly
honest for a weekly, end-of-day strategy. Event-driven machinery buys nothing at this speed.

**Rebalance timing:** score at Friday's close → trade at Monday's open → hold 5 trading days → repeat.
Non-overlapping, per Phase 3. Be honest up front about what this implies: the test window
(2025-04-29 → 2026-08-17) contains only about 70 rebalances. A Sharpe ratio computed on 70 observations is a
very noisy number, and should be reported with a confidence interval rather than as a fact.

**Report the two sides separately.** If the buy side makes all the money during a rising market, the "edge"
is just market exposure wearing a costume. Splitting long-side return from short-side return is what exposes
that.

**Treat fees as a sweep, not a constant.** The more useful output is the **break-even fee level** — "this
strategy is profitable up to 7 basis points per round trip and dies above that" — rather than one Sharpe
under one assumption. Given Phase 3's own estimate (a gross spread of maybe 0.5% per 5 days across ~16
stocks), the fee sweep is likely to be the number that decides this project, not the IC.

## 12. Layer 4 — Risk and stop rules (`pipeline/risk/`)

*What this is for: limiting losses. Phase 3 already tabulates six triggers and correctly notes they collapse
into about three genuinely independent mechanisms.*

```python
def check_<trigger>(state) -> (bool, str)    # one small function per trigger -> (should it fire?, why)
def false_trip_test(trigger_fn, planted_ic, n_sims) -> float   # how often it fires on a KNOWN-GOOD signal
```

**The rule that matters:** no threshold gets adopted until it passes the false-trip test. With roughly 4
independent observations inside a "20-day rolling spread", a naive stop rule is close to a coin flip, and it
produces the classic failure — switching off after a drawdown (which then recovers) and switching back on
after a rally. So the order is: `planted_ic_signal` → `false_trip_test` → *then* pick thresholds.

This layer is also where the project's own honesty rule applies hardest: **a risk layer does not create an
edge.** Building it is right. Deploying because it exists is not.

## 13. Layer 5 — Execution (`pipeline/execution/`)

*What this is for: making the real account match the portfolio the system decided on.*

```python
def get_current_positions(client) -> pd.Series          # symbol -> signed shares
def reconcile(target_weights, current_positions, equity) -> list[Order]
def submit(orders, client, dry_run=True) -> list[Fill]
def refresh_asset_flags(client) -> pd.DataFrame         # shortable / borrow_status, cached daily
```

**Design this as reconciliation, not as signal-firing.** Compute the portfolio you *want*, compare it to the
positions you *have*, and send only the difference. This makes it **idempotent** — run it twice and the
second run sends nothing. It also handles rejected shorts, partial fills, and crashed runs for free: whatever
did not happen simply shows up as a difference next time. A "send BUY when the model says buy" design has
none of those properties and will eventually double a position.

**The same object drives both paths.** The `target_weights` the backtester consumes is the same
`target_weights` the executor consumes. That is what makes backtest-versus-live agreement real rather than
aspirational.

**Alpaca specifics to confirm before designing around them:**

- Paper accounts are margin accounts and start at $100,000; shorting needs at least $2,000 equity. Fine.
- The Assets endpoint exposes `shortable`, `easy_to_borrow`, and `borrow_status`. Easy-to-borrow (ETB) is the
  target set. Hard-to-borrow (HTB) requires a "locate", submitted in round lots of 100 and not reusable —
  out of scope for version 1, so HTB names get filtered out rather than traded.
- **Fractional and notional orders are generally long-only.** If shorts must be whole shares, exact money
  matching between the two sides is impossible and there is a structural floor on leftover market exposure.
  Confirm this early — it changes the tolerance in `match_notional`, which means it changes Layer 2.
- There are community reports of shorts being rejected despite `shortable=True`. Treat the flags as advisory;
  the reconciler must tolerate rejection rather than assume success.

**How to test this with no model:** dry-run mode against `momentum_signal`. Log every order that *would* have
been sent, and submit nothing. Then paper-trade that same signal for real — it is a legitimate strategy, it
exercises every code path, and it costs nothing but paper money.

## 14. Layer 6 — Audit log and dashboard (`pipeline/audit/`, Streamlit)

*What this is for: Phase 4 requires that every action has a recorded prediction, input state, decision rule,
and outcome.*

One append-only table, one row per (rebalance date, stock):

```text
timestamp | symbol | score | rank | quantile | shortable | filtered_by | target_weight
          | prior_weight | order_side | order_qty | fill_price | triggers_fired | reason
```

Design this schema **now**, before Layers 2–5 are written, so each layer fills in its own columns as it runs.
Retrofitting an audit log is painful. Growing one is free. The Streamlit dashboard then becomes a reader of
this table instead of a second implementation of the same logic.

## 15. Build order

```text
  ┌─ 0. Signal contract + fake signals ──────────────────┐  needs no ML
  │      random / cheat / planted-IC / momentum          │
  ├─ 1. Signal analytics (IC, spread, t-stat) ───────────┤  ← ALSO unblocks the ML track
  ├─ 2. Portfolio construction (pure functions + tests) ─┤  needs: sector_map
  ├─ 3. Backtester (validated by cheat & coin flip) ─────┤
  ├─ 4. Stop rules + false-trip test ────────────────────┤  needs: planted-IC from step 0
  ├─ 5. Alpaca execution, dry-run first ─────────────────┤  needs: paper account only
  └─ 6. Audit log (schema first) + dashboard ────────────┘
                                                            then: model_signal plugs into step 0
```

Steps 0–6 need **nothing** from the ML track. The only thing gated on the model is the *verdict* — whether
the system is permitted to trade the model's scores — and that gate is already written down in Phase 3.

Suggested first three sessions:

1. Layer 0 + Layer 1. Then immediately re-measure Experiment 8's pooled model using IC instead of AUC — that
   answers a question the ML track is currently stuck on.
2. Layer 3, validated against the cheat and the coin flip, driven by `momentum_signal`.
3. Layer 2, then wire 2 → 3 and produce the first real equity curve.

## 16. Decisions to make before writing code

| Decision | Recommendation | Why |
|---|---|---|
| Write your own backtester, or use `vectorbt` / `zipline` | **Your own, ~150 lines** | The case is narrow: weekly, end-of-day, ranking across stocks. `zipline`'s Pipeline is the right shape but heavy to install and run; `vectorbt` is built for sweeping thousands of parameter combinations on single assets. A learning-first project gains more from owning that `shift(1)` itself. |
| Write your own IC analytics, or use `alphalens` | **Your own; cross-check against alphalens once** | Same reasoning, plus the non-overlapping t-statistic requirement is specific to this project and is not what a library gives by default. |
| `scores` layout | **Long: `[timestamp, symbol, score]`** | Matches `build_panel_data()`; no reshape at the boundary. |
| Price source for the backtest | **`raw_{symbol}.csv`** | `engineered_*.csv` has warm-up gaps from `dropna()` *and* carries `fwd_5d_return`, which is the backtest's answer key. Keep answer keys out of the price path. |
| Rebalance timing | **Friday close → Monday open → hold 5 trading days** | Unambiguous, non-overlapping, and matches how the label was built. |
| Module layout | `pipeline/signals/`, `pipeline/eval/`, `pipeline/backtest/`, `pipeline/risk/`, `pipeline/execution/`, `pipeline/audit/` | Extends the existing `pipeline/model/` convention. Flatten it if it feels heavy — the boundaries matter more than the folders. |

## 17. Traps specific to *this* repo

1. **The universe is uneven from date to date.** `transform.py` drops warm-up rows per stock, and
   `add_market_features()` drops another 59 rows for `beta_60`. Define it explicitly: *the universe on date d
   is the set of stocks with a valid score on d*, and refuse to trade if it falls below the minimum count.
   Otherwise early dates quietly trade a 12-stock universe where each "group of 8" is really a group of 2.

2. **`fwd_5d_return` lives inside the engineered CSVs.** It is the answer key. One accidental include in a
   feature list or a careless merge, and every number downstream is fiction. Enforce it structurally: the
   module that owns returns is separate from the module that owns scores, and `oracle_signal` is the *only*
   thing allowed to touch both.

3. **`sector_map` does not exist as data.** It blocks the per-sector cap. Trivial to fix, easy to forget.

4. **Shortability flags are today's values applied to 2020 data** — already logged as Known Limitation #3 in
   `Project_Context_and_Plan_Updated.md`. The backtested short side is therefore slightly optimistic. Keep
   that caveat attached to the number wherever it gets reported.

5. **Survivorship bias.** These 40 large-caps were chosen in 2026 and backtested from 2020. The universe
   already knows who won.

6. **The backtest is a brand-new place to overfit.** This project has been careful about multiple testing on
   the ML side. A backtester with a group count, a holding period, a fee assumption, and cap parameters is a
   fresh set of knobs to turn until the answer looks good. Mitigation: **decide the strategy parameters
   before running the model's scores through it** — write them into `risk/config.py` and into `EXPERIMENT.md`
   first — and log every variant tried, exactly as the ML experiments are logged.

7. **About 70 rebalances is a small sample.** Report confidence intervals, not point estimates.

## 18. Research checked before writing this plan

- Vectorized backtesting is accurate for daily/weekly end-of-day cross-sectional studies; event-driven
  complexity buys nothing at this cadence —
  [IBKR Quant](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/),
  [Python for Algorithmic Trading, ch. 4](https://www.oreilly.com/library/view/python-for-algorithmic/9781492053347/ch04.html)
- Library survey: `zipline-reloaded`'s Pipeline is the cleanest cross-sectional API, `vectorbt` is built for
  large parameter sweeps; both are heavier than this project needs —
  [Best Python Backtesting Libraries 2026](https://hasanjaved.me/blog/best-python-backtesting-libraries-2026/),
  [VectorBT](https://vectorbt.dev/)
- Evaluate the signal (IC, group returns, turnover) *before* building a strategy; effective equity factors
  typically post mean IC between 0.05 and 0.15 —
  [Alphalens guide](https://medium.com/@er.mananjain26/separating-signal-from-noise-a-practical-guide-to-evaluating-alpha-factors-with-alphalens-b883070aab14),
  [ML for Trading — alpha factor research](https://stefan-jansen.github.io/machine-learning-for-trading/04_alpha_factor_research/),
  [PyQuant News — IC & Alphalens](https://www.pyquantnews.com/free-python-resources/real-factor-alpha-how-to-measure-it-with-information-coefficient-and-alphalens-in-python)
- Alpaca shorting mechanics: ETB vs HTB, locates in round lots of 100 and non-reusable, and the
  `shortable` / `easy_to_borrow` / `borrow_status` flags on the Assets endpoint —
  [Margin and Short Selling](https://docs.alpaca.markets/us/docs/margin-and-short-selling),
  [HTB trading & locates](https://alpaca.markets/blog/htb-trading-api-locates/),
  [alpaca-py models](https://alpaca.markets/sdks/python/api_reference/trading/models.html)

---
---

# PART 3 — Glossary

`EXPERIMENT.md` already has a glossary covering **IC**, **cross-sectional**, **market beta**,
**purge/embargo**, **effective sample size**, **long/short quintile spread**, **t-statistic**, and
**regime**. Those are not repeated here. This list covers only the terms this document adds.

- **Short (short selling)** — betting a stock goes down. You borrow shares, sell them now, and buy them back
  later. If the price fell, you keep the difference.
- **Backtest** — replaying a strategy over historical data to see what it would have earned. Easy to get
  silently wrong, which is why Section 4 exists.
- **Long side / short side (or "leg")** — the stocks you bought vs. the stocks you shorted. Reporting them
  separately reveals whether the profit is real skill or just market exposure.
- **Notional** — the dollar amount of a position, as opposed to the number of shares.
- **Gross exposure** — total money at work, both sides added together. **Net exposure** — the *difference*
  between the two sides. A balanced portfolio has high gross and near-zero net.
- **Turnover** — how much of the portfolio gets replaced each rebalance. High turnover means high fees.
- **Slippage** — the gap between the price you expected and the price you actually got.
- **Borrow fee** — what you pay to borrow shares in order to short them. Can be 10–100%+ per year on
  hard-to-borrow names, which is enough to wipe out a small edge entirely.
- **ETB / HTB** — Easy-To-Borrow vs Hard-To-Borrow. ETB can be shorted normally. HTB needs a "locate" first.
- **Reconciliation** — comparing the portfolio you want against the positions you actually hold, and sending
  only the difference.
- **Idempotent** — running it twice produces the same result as running it once. The property that stops a
  crashed-and-restarted run from doubling every position.
- **Sharpe ratio** — return divided by volatility. "How much profit per unit of stomach-churn."
- **Maximum drawdown** — the worst peak-to-trough fall in account value.
- **Basis point (bp)** — one hundredth of a percent. Trading costs are usually quoted in these.
