# An options agent built to prove itself wrong

Submitted to the Alpaca AI Trading Agents Hackathon (28 Aug, 4 Sep 2026).

Sells defined-risk SPY put credit spreads, weekly, with a rules engine that
Claude and Gemini can only make more conservative, never less. Then points a
falsification engine at its own result. This document leads with what that
engine found.

---

## The audit, first

Before this project claims anything, here is what happened when it checked
its own headline number.

We built a Deflated Sharpe Ratio (Bailey and Lopez de Prado, 2014) and pointed
it at the strategy's own return series. The first version came back with the
strategy's Sharpe at -0.70 and a DSR of essentially zero. Before publishing
that, we found the cause: the simulation credited zero interest on collateral
that was sitting idle most weeks, while still subtracting the full risk-free
rate as the benchmark. A rate was removed that was never paid in. Fixed
against the industry's own reference convention (CBOE's PutWrite index,
"fully collateralized... invested at the 1- and 3-month Treasury Bill rate,"
every day, traded or not), the corrected Sharpe is **+0.56 to +0.57**.

That correction is the point, not a footnote. The engine's first real catch
was this project's own error, in the direction that made the strategy look
worse, not better. Having fixed it, here is what survives:

Corrected for the **31 things this project has tried** against this data (its
own numbered experiment ledger, every one logged whether it worked or not),
the Deflated Sharpe Ratio is **0.20 at N = 31**. That is not "it doesn't
work." It is "roughly a one-in-five chance the edge is real once you account
for how many times we were allowed to be wrong." Not proven.

A second, independent check pushes further. Ordinary Sharpe ratios are
provably gameable by exactly the shape of payoff this strategy has (Goetzmann,
Ingersoll, Spiegel and Welch, 2007), so we also computed their
Manipulation-Proof Performance Measure, which cannot be gamed the same way. It
independently confirms the project's own earlier finding that the crash-timing
filter is insurance, not an edge, and it shows that risk-matched to SPY's own
volatility, this strategy loses to plain buy-and-hold at every level of risk
aversion tested.

Four independent lines of evidence went into that number: two argued
against the strategy, one of them caught the project's own bug before it
reached a reader.

---

## Positioning

Most automated trading bots publish a backtest Sharpe ratio and stop
there. That number does not say how many strategies, parameters, or
thresholds were tried before landing on the one that got published, so it
is cheap to produce and hard to trust on its own. This system publishes
both numbers instead of one: a raw Sharpe of +0.56 to +0.57, and what
that Sharpe becomes once it is charged for the 31 things actually tried
against this data (Deflated Sharpe Ratio, Bailey and Lopez de Prado
2014): 0.20. Most bots do not report that correction at all.

The AI in this system can only shrink a trade or cancel it, never
enlarge one and never place one on its own. Many bots let a model size
or place trades directly. Here the model reviews a proposal that a fixed
rules engine already generated and every risk guard already approved,
and its only two powers are shrink or veto, enforced by a pure function
with no network call in it, so the safety property holds regardless of
what the model outputs.

The risk guards are tested the same way the strategy is: each one is
replayed against real historical winning weeks to measure how often it
would have blocked a good trade, with a pre-committed limit that already
forced one guard's threshold down after it was found blocking 42% of
winners. A guard nobody has checked against the trades it would have
prevented is a guess wearing a safety label, not a control.

---

## What it trades

The system sells insurance on the S&P 500. Each session it offers a
contract: if SPY falls more than 3% over the next week, it pays out. Most
weeks there is no fall and it keeps the fee. Every position is a defined-risk
put credit spread, two legs sent as a single order, so the maximum loss is
fixed before the trade exists and a naked short is structurally impossible.

The machine-learning work in this repo is a separate, unrelated track. It
tried to predict five-day stock direction and found nothing. What trades has
no model in it at all, only a rules engine that a language model can
restrict but never expand.

---

## Viable, solid, reliable, creative, real

**Viable.** Every (distance, width) combination the strategy could trade was
tested against real, historical expired option prices, not a model of them.
Twenty-four cells, three clear a two-standard-error bar against their own
breakeven rate, all at 3% distance. Trading cost was not assumed, it was
measured live: an earlier attempt used an invented 2-cent-per-leg guess that
emptied the evidence gate entirely (zero of 24 cells survived), so the real
bid-ask on every live candidate was fetched instead, landing at the market's
own $0.01 minimum tick.

**Solid.** The strategy's option-price history only goes back to February
2024, so a ten-year reconstruction was built to extend it, priced from CBOE's
VIX9D. The first version scored an aggregate correlation of 0.649, which
looks acceptable until you split it by volatility regime: it priced calm
weeks at 3% of reality and volatile weeks at 125% of reality, two opposite
errors canceling into a confident, completely false result. The
reconstruction now validates per volatility quartile and the build fails if
any bucket drifts outside a tight band. The corrected model scores 0.972 and
holds within 2-3% in every regime.

**Reliable.** Fifteen deterministic guards sit between any proposal and an
order: position caps, drawdown halts, liquidity floors, a VIX term-structure
check that fails closed on stale data, expiry-day and one-leg-orphan rules.
A recovery module treats the broker's real position state as ground truth
and blocks opening anything the audit log does not recognize. Every order
placement defaults to a dry run; going live requires an explicit,
mutually-exclusive flag.

**Creative.** Beyond the guards, four methods are uncommon even among
serious quant work. A regime-split validation gate that fails the build on
drift, described above. A false-trip test that runs every risk guard against
historically winning weeks to measure how many good trades it blocks, with a
pre-committed limit that already forced one guard's threshold down after it
was found blocking 42% of winners. A pre-registered randomization null that
reruns a promising-looking result 2,000 times with the signal shuffled, and
correctly killed a result that a simple t-test had called significant. And
the falsification audit itself, which found its own accounting bug before
publishing a number.

**Real.** A live filled order exists on the account: SPY 735/730 put credit
spread, 6 contracts, expiring 2026-09-11, filled at a net credit of $0.23 per
share, cash up $137.70. The sign convention on Alpaca's multi-leg limit
price was unverified by the broker's own documentation until this fill
confirmed it. A public, read-only dashboard shows the account live. Every
number in the falsification audit reproduces from a clean clone with no
credentials, in about 17 seconds.

**On the account itself, stated rather than left for a judge to wonder
about:** the paper account (`PA3LRFJ9JMVX`) predates the hackathon, opened
earlier for read-only market data access. It carried zero positions and
zero orders before the hackathon's own start date (28 Aug 2026); every
order on it, including the fill above, was placed during the contest
window. We are disclosing this rather than presenting the account as newly
created for the submission, because the second thing would not be true.

---

## Features

- Fixed-risk SPY put credit spreads, 7-11 days to expiry, sized to a
  strict percentage of account equity per position
- Fifteen deterministic risk guards, all fail-closed on missing or stale
  data rather than silently proceeding
- A VIX-term-structure crash filter, walk-forward calibrated (never a
  full-sample constant), that skips trading when the market's own pricing
  says turbulence is coming sooner than later
- An LLM reviewer (Gemini) that can only approve, shrink, or veto a
  guard-approved proposal, never raise its size or originate a trade,
  enforced by a pure function with no network dependency, not by the prompt
- A recovery module that reconciles every session against the broker's own
  position and order state before allowing a new trade
- An append-only, schema-locked audit log recording every decision,
  including every rejection, with unknown fields rejected rather than
  silently dropped
- A public, read-only live dashboard, and a separate local admin console
  (never deployed publicly) for pause, resume, and force-close controls
- A falsification suite: Deflated Sharpe Ratio, Minimum Track Record
  Length, a bootstrap standard-error check, and a manipulation-proof
  performance measure, all reproducible offline
- 127 fast unit tests (under ten seconds, no credentials) plus 17 slower
  tests that reproduce every published performance figure end to end

---

## How it works

```
  Picker            15 Guards           Reviewer            Execution
 (fixed rules)  ->  (deterministic, ->  (Gemini, read-  ->  (direct
                     fail-closed)        only account        alpaca-py,
                                         context, may         multi-leg
                                         only APPROVE /       limit order)
                                         SHRINK / VETO)
                                              |
                                              v
                                     apply_reviewer_decision
                                     (pure function: clamps
                                      any multiplier to
                                      [0,1], never raises
                                      size, never invents
                                      a proposal)
```

The Picker selects from candidates that already cleared the evidence gate.
Guards check account state, liquidity, concentration, and the term-structure
filter, in that order, and any failure halts the proposal before it reaches
a model. The Reviewer gets one real, read-only account fetch and returns a
decision; that decision passes through a pure, network-free function before
it can touch an order, so the safety property does not depend on what the
model says, it depends on what the code allows regardless of what the model
says. After a fill, a 15-minute monitor loop checks four exit conditions in
priority order: a one-leg orphan, day-before-expiry, profit target, and hard
drawdown, with orphan and expiry rules overriding profit targets. A recovery
module runs on every cycle, including no-ops, to reconcile the account.

---

## Alpaca infrastructure

The Model Context Protocol server is read-only context for the Reviewer, not
the execution path. It is built from a hand-picked, per-operation allowlist
of 25 trading and 20 market-data operations, with a runtime assertion that
the allowlist and the forbidden write operations never overlap. The
order-placement tools are never registered at all, not filtered out after
the fact. Execution itself is direct `alpaca-py`, deliberately, so the code
that places real orders stays plain, unit-testable Python rather than a tool
call through a model.

Building this surfaced real API behavior worth stating plainly: an
unfiltered option-chain request silently defaults to calls only, chain
pagination can return a full page with more data still outstanding, the
account's data subscription rejects a full-history request against the SIP
feed but the same range succeeds when chunked, and a bar request with no
explicit adjustment parameter returns raw prices, which read every real
stock split in the 40-symbol universe as a fake 90% single-day crash until
fixed. Each of these was found live, confirmed against a second source, and
guarded against in code, not just noted and moved past.

The Alpaca CLI was kept as a fallback if the MCP wiring failed. It did not
fail, so the CLI was never needed, and this project satisfies the
requirement through the MCP server.

---

## Performance

All figures below are reproducible with no credentials or network via
`python -m pipeline.falsify.audit`, in about 17 seconds.

| | Annual return | Volatility | Sharpe | Max drawdown |
|---|---|---|---|---|
| Filtered (single position, 3% cap) | 3.89% | 1.56% | **+0.574** | 2.89% |
| Filtered (2 concurrent, 6% cap) | 4.83% | 3.25% | +0.563 | 5.91% |
| Unfiltered, every week (2 concurrent basis) | 5.42% | 6.94% | +0.350 | 17.59% |
| SPY buy-and-hold, same period | ~15.0% | | ~0.69 | 32.1% |

The strategy earns less than the index and carries roughly a fifth of its
drawdown. It was never designed to beat the index; it was designed not to
blow up, and the same sizing that prevents that is why it earns little.

**Deflated Sharpe Ratio: 0.20 at N = 31.** Minimum Track Record Length: this
strategy would need 932 weeks (17.9 years) of data to prove its Sharpe
exceeds zero at 95% confidence, against 10.3 years available. The better
this strategy is at its actual job, never blowing up, hence extreme negative
skew and fat tails, the harder that makes Sharpe to prove statistically.
That tension is a finding, not a flaw to engineer around.

**The crash filter, tested twice.** Measured with skipped weeks earning
cash, the VIX-term-structure filter costs about 0.6 percentage points of
annual return in exchange for roughly half the volatility and a threefold
smaller drawdown. A completely separate, non-gameable measure (the
manipulation-proof performance measure above) reaches the same conclusion
independently: the filter costs return relative to trading every week. Two
different methods agreeing is stronger than either alone.

**2018, examined rather than just cited.** The filter avoided all five of
2018's losing weeks while skipping 63% of the year. Skipping 63% at random
would dodge about three of five; getting all five beats chance at roughly
p = 0.10, which is not significant at any conventional bar. Take 2018 out
entirely and the filter is a wash, 0.59 Sharpe against 0.60 unfiltered.
Nearly all of the filter's value comes from one year. That is what a tail
hedge looks like, and it means this project has exactly one full observation
of the event the filter exists for, not evidence to oversell.

---

## The experiments

Two research tracks preceded the trading system and both produced honest
negative results before this system was built on top of what remained.

**Direction prediction (closed).** Naive baseline through pooled 40-stock
panel models: no feature combination tested shows a cross-stock predictive
edge for five-day direction. The pooled model's rank of "which stocks beat
the market this week" measured by cross-sectional Information Coefficient,
the rigorous test, came back statistically indistinguishable from zero
(t = -0.27 to -0.35). This was re-verified after finding and fixing a real
data defect, four symbols' un-split-adjusted prices reading real stock
splits as fake 90% single-day crashes, and the null result held before and
after the fix. A negative result surviving a real data-quality correction is
itself informative.

**Volatility forecasting (five pre-registered hypotheses, four killed):**

| Hypothesis | Question | Verdict |
|---|---|---|
| H1 | Does the VIX term structure time weekly option overpricing? | Killed |
| H2 | Does downside semivariance beat plain realized-volatility HAR? | Killed |
| H3 | Does QLIKE-direct fitting beat OLS fitting? | **Confirmed** |
| H4 | Does the volatility forecast convert into a trading edge? | Killed, eight ways |
| H5 | Does XGBoost beat HAR with exogenous features? | No |

The one unconditional positive, HAR-X (realized volatility augmented with
VIX), is a real, literature-confirmed forecaster. Every attempt to convert
that forecast into strike timing, sizing, or a skip filter failed, including
a near-miss result that looked significant on a simple test and was killed
by the same pre-registered randomization null described above. Forecasting
volatility well and beating a liquid market's own pricing of it turned out
to be different claims, and only the first one holds.

**The options evidence base**, described in the Performance section above,
is the track that survived: real historical option prices, a validated
ten-year reconstruction, and the falsification audit that this document
opened with.

---

## Known limitations, stated rather than found

- Real option price history covers February 2024 onward; everything before
  that is a modeled reconstruction, however validated.
- The crash-filter's entire measured benefit concentrates in one year
  (2018). One event is not a distribution.
- The Deflated Sharpe Ratio's analytic standard error was found to be 1.7 to
  1.8 times anti-conservative by a bootstrap check, meaning it overstates
  significance. Since this project's claim is "not proven," that known bias
  makes the conclusion safer, not shakier, but it means the DSR should never
  be used alone to support a positive claim.
- The false-trip test needs live Alpaca credentials to run and cannot be
  reproduced from a bare clone; its result is cited from a saved artifact
  instead.
- The 50% profit-target exit is an industry convention, not a number this
  project backtested. The plan's own words: "we did NOT test it... this is
  our most glaring untested number." Day-before-expiry closing and the
  15-minute polling cadence are deliberate, reasoned choices; the exact
  profit-taking threshold is not.
- This is five days of live paper trading. No strategy's edge is visible
  over a single week, and this document does not claim otherwise.

---

## Reproduce it

```
git clone <this repo> && cd stock
pip install -r requirements.txt
pytest tests/           # 127 tests, under 10 seconds, no credentials, no network
pytest tests/ -m slow   # 17 tests, reproduces every published figure end to end
python -m pipeline.falsify.audit        # the full falsification audit, ~17s
python -m pipeline.backtest.reconstruct # the ten-year evidence reconstruction
```

Full experiment log, including every negative result and why it was trusted
or rejected: [`EXPERIMENT.md`](EXPERIMENT.md). Full falsification account:
[`EXPERIMENT_29_SHARPE_AUDIT.md`](EXPERIMENT_29_SHARPE_AUDIT.md). Every
external source cited above: [`SOURCES.md`](SOURCES.md).
