# SPY Options Agent, Built to Prove Itself Wrong

Built for the **Alpaca AI Trading Agents Hackathon**. Sells defined-risk SPY
put credit spreads on a weekly cadence, reviewed by an LLM that can only
make a proposal smaller or cancel it, then points a falsification engine at
its own result before publishing anything.

**Full submission writeup, start here:** [`WRITEUP.md`](WRITEUP.md).
This README covers setup, running the code, and repo structure. This repo
also contains a separate, earlier machine-learning research track (5-day
stock direction prediction across 40 stocks) that is not part of the
trading system, described under "The ML track" below.

## Live dashboard

**[stock-ten-orcin.vercel.app](https://stock-ten-orcin.vercel.app)** is
read-only, live from the real paper account. It is read-only by design: a
public URL that could also trigger real trades would let anyone who finds
the link act on a real brokerage account. Pause, resume, force-close, and
on-demand runs exist only in a local admin console (`CONTROLS_ENABLED=true`,
`streamlit run pipeline/ui/app.py`) that never gets deployed publicly.

A live filled order exists: SPY 735/730 put credit spread, 6 contracts,
expiring 2026-09-11, filled at a net credit of $0.23 per share, cash up
$137.70. That fill happened on account `PA3LRFJ9JMVX`, opened before this
project noticed Alpaca's hackathon rules require a brand-new account per
submission -- that account is disqualified from judging regardless of its
clean history, and is offered here only as evidence the system executes
correctly.

The account this submission is judged on is `PA3HWE141FA8`, created
2026-09-03 with a $100,000 starting balance, after a real Alpaca
restriction on new accounts for Indonesian tax residents delayed opening
a compliant one past the official measurement window's close. It has no
meaningful trading history from that window. `WRITEUP.md`'s "Real, and
then a correction we found late" section states this in full.

## What the trading system does

The system sells insurance on the S&P 500. Each session it offers a
contract: if SPY falls more than 3% over the next week, it pays out. Most
weeks there is no fall and it keeps the fee. Every position is a
defined-risk put credit spread, both legs sent as a single multi-leg
order, so the maximum loss is fixed before the trade exists and a naked
short is structurally impossible.

## What it returns

About 4.8% a year on the account, with a 5.9% worst drawdown. SPY
buy-and-hold returned about 15.0% a year over the same period, with a
32.1% drawdown. Risk-adjusted, that is a Sharpe of 0.56 against SPY's
0.69, roughly 80% of the index's risk-adjusted return, at a fifth of its
drawdown.

That comparison is exactly what this project's own audit (Experiment 29)
found reason to distrust. Correcting for the 31 things tried against this
data (the full [`EXPERIMENT.md`](EXPERIMENT.md) ledger), that 0.56 Sharpe
is not statistically distinguishable from the best of 31 lucky tries
(Deflated Sharpe Ratio = 0.20 at N=31):

| Trials tested (N) | 1 | 5 | 10 | 30 | 100 |
|---|---|---|---|---|---|
| Deflated Sharpe Ratio | 0.894 | 0.523 | 0.372 | 0.205 | 0.100 |

N=31 is this project's actual trial count as of today. It will rise again
once further hypotheses are tested (see `pipeline/falsify/trial_count.py`
for exactly which changes count as a new trial and which don't), so a bare
"DSR=0.2" is dated the moment that happens. Full derivation, reproducible
with no credentials or network in about 17 seconds
(`python -m pipeline.falsify.audit`):
[`EXPERIMENT_29_SHARPE_AUDIT.md`](EXPERIMENT_29_SHARPE_AUDIT.md).

This strategy is not designed to beat the market. It is sized so that it
cannot blow up, and that same sizing is why it earns little.

## The problem found, and what fixed it

The original test covered Feb 2024 onward, because that is where option
price records start. That turned out to be the calmest stretch of
available history: SPY fell more than 3% in a week 2.3% of the time in
that window and 8.5% in the four years before it.

Testing further back required knowing what the fee would have been. The
answer was CBOE's VIX9D index, the market's own 9-day volatility measure,
free since 2011 and almost exactly this strategy's tenor. Ten years of
fees were rebuilt, validated against the real prices that do exist, and
replayed across 538 weeks.

**2018 lost 41% of what the entire decade earned.** One year.

The fix came from published research on volatility selling: when the VIX
curve flattens or inverts, meaning the market expects more turbulence soon
than later, stop selling. Skipping the worst third of weeks by that
measure turned 2018 from a large loss into a small profit and cut the
worst drawdown by 75%, at every distance, width, and cost level tried.

That result was then tested twice, specifically to try to break it.
First, measured with skipped weeks earning cash instead of zero, the
term-structure filter costs about 0.6 percentage points of annual return
in exchange for roughly half the volatility and a 3x smaller drawdown, a
Sharpe of 0.56 against 0.35 unfiltered. Second, and more decisively: a
performance measure specifically designed not to be gameable by
option-selling payoffs (the manipulation-proof measure of Goetzmann,
Ingersoll, Spiegel and Welch, 2007; ordinary Sharpe ratios are provably
gameable by exactly this shape of strategy) reaches the same conclusion
independently. Two different methods agreeing that this is insurance, not
an edge, is stronger evidence than either alone. See
[`EXPERIMENT_29_SHARPE_AUDIT.md`](EXPERIMENT_29_SHARPE_AUDIT.md).

A third check produced the one result not expected going in: risk-matched
to SPY's own volatility (levering the strategy roughly 11x to get there),
the same non-gameable measure says it loses to plain SPY buy-and-hold at
every level of risk aversion tested. The strategy's real value is not
"beats the index," it never claimed that at this size. It is a much
smaller, much shallower ride to a smaller number, which is a legitimate
thing to want but a different claim than a bare Sharpe ratio communicates.

Two caveats, stated directly:

The rule avoided all five of 2018's losing weeks while skipping 63% of
that year, because its threshold was calibrated on 2016-2017, the calmest
stretch on record. Skipping 63% at random would dodge about 3 of those 5.
Getting all 5 beats chance at roughly p = 0.10 (0.627^5), not significant
at any conventional bar. The honest read is that all of 2018's protection
came from one calibration decision on one year, not a result that has
cleared a real statistical hurdle.

Take 2018 out and the filter is a wash: 0.59 Sharpe against 0.60
unfiltered, essentially identical. Nearly all of the filter's value comes
from one year. That is what a tail hedge looks like, and excluding the
worst year is a diagnostic rather than a reason to drop the protection,
but it means there is exactly one full observation of the event the
filter exists for.

The mechanism, understood only after checking: 2022 had a worse breach
rate than 2018 (19.6% against 15.7%) and lost far less. 2022 was volatile
throughout, so the fees collected were fat and absorbed the losses. 2018
spiked from a calm base, so the fees collected beforehand were tiny and
the losses arrived undefended. The thing that hurts a premium seller is a
volatility spike from calm, not high volatility itself, which is exactly
what a flattening VIX curve detects and a realized-volatility threshold
cannot.

A competing idea, skipping weeks when the offered fee itself was small,
was tested and did nothing: 2018 stayed exactly as bad. That negative
result is logged next to the positive one, not omitted.

## What sets this apart from a typical trading bot

Most automated trading bots publish a backtest Sharpe ratio and stop
there. That number does not say how many strategies, parameters, or
thresholds were tried before landing on the one that got published. This
project publishes the correction instead of the bare number (the Deflated
Sharpe Ratio table above), and backs it with two pieces of machinery that
are uncommon even in professional volatility-selling systems:

**A regime-split validation gate.** Extending a short options history
means reconstructing old prices, and a single aggregate correlation for
that reconstruction can look fine while hiding a regime-level failure.
The first attempt here scored 0.649 overall, which looked acceptable,
until splitting by volatility regime showed it priced calm weeks at 3% of
reality and volatile weeks at 125% of it, two opposite errors cancelling
into a confident, completely false result. The reconstruction is now
validated per volatility quartile and the build fails if any bucket
drifts. The corrected model scores 0.972 and stays within 2-3% in every
regime.

**A false-trip test.** Most systems test whether a risk filter helps.
This one also replays every guard against historically winning weeks to
measure how many good trades it would have blocked, with a pre-committed
limit that forces the threshold to loosen or the guard to drop. It has
already cost one guard that was blocking 42% of winning weeks.

Any backtest can be made to look good by choosing the window. This one
looked good partly because of when it started. Stating that plainly is
what this project would want to know if someone handed it this system.

## The ML track

A separate, earlier research track lives in this same repo: a 5-day
stock-direction prediction pipeline across 40 US large-caps, investigating
whether market-derived information from Alpaca historical data provides a
robust out-of-sample signal for whether a stock will have a positive or
negative return over the next 5 trading days. It is not part of the
trading system above. Across a naive baseline, Logistic Regression,
XGBoost, single-symbol feature ablation, a multi-symbol generalization
check, a 40-stock pooled panel model, and a panel diagnostic pass, **no
feature combination tested shows a robust, cross-stock predictive edge**
for 5-day direction. Three results are worth singling out:

- **Pooling works, for the problem it was meant to solve.** Stacking 40
  stocks into one panel cut the train/test overfitting gap from 0.13-0.26
  down to 0.068, confirming the mechanism Sirignano-Cont (2019) describe.
  It did not, however, move accuracy past chance (ROC-AUC 0.498).
- **There is no cross-sectionally useful ranking signal, on the
  project's most rigorous test.** Measured properly, cross-sectional
  Information Coefficient with non-overlapping t-stats, not accuracy or
  AUC, the model's rank of "which stocks will do better than the market
  this week" is statistically indistinguishable from zero (t = -0.27 to
  -0.35, against a plus-or-minus 2.0 significance bar). Re-verified after
  finding and fixing a real data defect (four symbols' un-split-adjusted
  prices were reading real stock splits as fake ~90% single-day crashes):
  the null result held before and after the fix, itself informative.
- **The evaluation was the bottleneck, not just the model.** The target
  is ~54% common market movement that single-stock technicals cannot
  explain, and with 5-day overlapping labels across correlated stocks the
  effective sample size is ~1,000, not 65,000.

See [`EXPERIMENT.md`](EXPERIMENT.md) for full detail, including the
diagnostic process (leakage checks, chronological validation, overfitting
checks, cross-validation, multiple-testing caveats) and a glossary of the
quant/ML terms used. Full research plan and philosophy (archived,
superseded by `VOLATILITY_ML_PLAN.md`):
[`archive/Project_Context_and_Plan_Updated.md`](archive/Project_Context_and_Plan_Updated.md)
and [`archive/ML_Experiment_Plan.md`](archive/ML_Experiment_Plan.md).
Trading-system foundation (archived, superseded by
`OPTIONS_SYSTEM_PLAN.md`):
[`archive/TRADING_SYSTEM_PLAN.md`](archive/TRADING_SYSTEM_PLAN.md).

## Setup

1. Clone the repo and create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root with your Alpaca (and, for the
   live Reviewer, Gemini) credentials:
   ```
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   GEMINI_API_KEY=your_key_here
   ```

## Reproducing the trading system's evidence

No credentials or network required for any of these:

```
pytest tests/                            # 127 tests, under 10 seconds
pytest tests/ -m slow                    # 17 tests, reproduces every published figure end to end
python -m pipeline.falsify.audit         # the full falsification audit, ~17s
python -m pipeline.backtest.reconstruct  # the ten-year evidence reconstruction
```

## Running the trading agent

These place and manage real orders on whatever Alpaca account the `.env`
credentials point to. `--dry-run` is the default for both entry points and
simulates without submitting; `--live` actually places orders.

```
python -m pipeline.run_agent --live              # one entry-decision cycle
python -m pipeline.execution.monitor --run --live  # one exit-monitoring cycle
```

`monitor`'s `--run` flag is required to actually poll the broker; without
it the module only runs its inline self-checks and exits, which silently
no-ops against real positions if forgotten. If either command runs from
cron rather than an interactive shell already inside the repo, prefix it
with `cd /path/to/repo &&`, since cron does not start in the repo
directory and the module import fails without it.

The local admin console (pause, resume, force-close, on-demand runs, never
deployed publicly) is separate:
```
CONTROLS_ENABLED=true streamlit run pipeline/ui/app.py
```

## Running the ML pipeline

Run everything (fetch data for all configured symbols, engineer features,
run every model/experiment, export comparison tables) from the project
root:
```
python -m pipeline.run_all
```

Symbols and date range are configured in
[`pipeline/config.py`](pipeline/config.py). Individual stages can also be
run on their own, e.g.:
```
python -m pipeline.extract
python -m pipeline.transform
python -m pipeline.model.xgb_group_feature
```

## Project structure

```
pipeline/
  falsify/                # Deflated Sharpe Ratio, MinTRL, bootstrap SE, manipulation-proof measure, the hypothesis-falsification engine
  backtest/                # ten-year VIX9D reconstruction, evidence gate, the real-option-price replay
  options/                 # strike/width selection, option-chain access, pricing
  risk/                    # the 15 deterministic guards, false-trip testing
  execution/                # order placement, exit monitoring, position recovery
  reviewer/                 # the Gemini review stage (shrink/veto only, pure-function enforced)
  mcp/                     # Alpaca MCP server surfaces (Reviewer read-only, falsification-engine tools)
  audit/                   # append-only, schema-locked decision log
  ui/                      # the Streamlit dashboard (public read-only + local admin console)
  config.py                # ML track: single source of truth for symbols, date range
  extract.py                # ML track: pulls daily OHLCV bars from Alpaca per symbol
  transform.py              # ML track: feature engineering + 5-day target label
  run_all.py                # ML track: orchestrates the full pipeline across all configured symbols
  run_agent.py               # trading system: one entry-decision cycle
  model/
    baseline_model.py      # naive majority-class baseline
    logistic_model.py       # Logistic Regression baseline
    xgb_model.py             # single-split XGBoost
    xgb_stability.py         # XGBoost with TimeSeriesSplit cross-validation
    xgb_group_feature.py     # feature-group ablation sweep (all combinations)
    pooled_xgb_model.py      # pooled/panel XGBoost across all symbols at once
  panel.py                # builds the stacked multi-symbol panel + date-based split
tests/                    # 127 fast + 17 slow, see "Reproducing the trading system's evidence" above
output/
  data/                   # raw + engineered per-symbol datasets, plus reproducibility CSVs (gitignored except the ones cited above)
  model/                  # multi-stock comparison result tables
raw_data_eda.ipynb        # exploratory data analysis notebook
```

## Known limitations

Stated here rather than left for a reader to find: real option price
history covers February 2024 onward, everything before that is a modeled
reconstruction; the crash filter's entire measured benefit concentrates
in 2018, one event, not a distribution; the 50% profit-target exit is an
industry convention that was never itself backtested; the false-trip test
needs live Alpaca credentials and cannot be reproduced from a bare clone;
and this is days of live paper trading, not evidence of an edge over any
meaningful horizon. Full list with the reasoning behind each:
`WRITEUP.md`'s "Known limitations" section.

## Guiding philosophy

Start simple, test, diagnose, add one thing, test again. Every result in
this project is reported, including negative and inconclusive findings.
See `EXPERIMENT.md` for the reasoning behind each experiment and why some
promising-looking results were later revised or rejected, and
`WRITEUP.md` for the trading system's own account of the same discipline.
