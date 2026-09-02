# Stock Direction Prediction — 5-Day Multi-Stock Experiment (40 US large-caps)

A learning-first, experiment-driven ML pipeline built for the **Alpaca AI Trading Agents Hackathon**, investigating a narrow research question:

> **Can market-derived information from Alpaca historical data provide a robust out-of-sample signal for whether a stock will have a positive or negative return over the next 5 trading days?**

Full research plan and philosophy (archived, superseded by `VOLATILITY_ML_PLAN.md`): [`archive/Project_Context_and_Plan_Updated.md`](archive/Project_Context_and_Plan_Updated.md) and [`archive/ML_Experiment_Plan.md`](archive/ML_Experiment_Plan.md).
Full experiment log (what was tried, why, results, interpretation): [`EXPERIMENT.md`](EXPERIMENT.md).
Trading-system foundation (archived, superseded by `OPTIONS_SYSTEM_PLAN.md`): [`archive/TRADING_SYSTEM_PLAN.md`](archive/TRADING_SYSTEM_PLAN.md).

## Live dashboard

**[stock-ten-orcin.vercel.app](https://stock-ten-orcin.vercel.app)** — read-only, live from the real paper account. It's read-only by design: a public URL that could also trigger real trades would let anyone who finds the link act on a real brokerage account. Pause/resume, force-close, and on-demand runs exist too, but only in a local admin console (`CONTROLS_ENABLED=true`, `streamlit run pipeline/ui/app.py`) that never gets deployed publicly.

## Key finding so far

Across a naive baseline, Logistic Regression, XGBoost, single-symbol feature ablation, a multi-symbol generalization check, a 40-stock pooled panel model, and a panel diagnostic pass, **no feature combination tested shows a robust, cross-stock predictive edge** for 5-day direction. Three results are worth singling out:

- **Pooling works — for the problem it was meant to solve.** Stacking 40 stocks into one panel cut the train/test overfitting gap from 0.13–0.26 down to **0.068**, confirming the mechanism Sirignano-Cont (2019) describe. It did not, however, move accuracy past chance (ROC-AUC 0.498).
- **There is no cross-sectionally useful ranking signal, on the project's most rigorous test.** Measured properly — cross-sectional Information Coefficient with non-overlapping t-stats, not accuracy or AUC, which barely distinguish a real signal from chance on a 50%-base-rate panel — the model's rank of "which stocks will do better than the market this week" is statistically indistinguishable from zero (**t = −0.27 to −0.35**, against a ±2.0 significance bar). Re-verified after finding and fixing a real data defect (four symbols' un-split-adjusted prices were reading real stock splits as fake ~90% single-day crashes): the null result held before and after the fix, which is itself informative — the negative finding was not an artifact of contaminated data.
- **The evaluation was the bottleneck, not just the model.** The target is ~54% common market movement that single-stock technicals cannot explain, and with 5-day overlapping labels across correlated stocks the effective sample size is **~1,000, not 65,000**.

See [`EXPERIMENT.md`](EXPERIMENT.md) for full detail, including the diagnostic process (leakage checks, chronological validation, overfitting checks, cross-validation, multiple-testing caveats) and a **glossary** of the quant/ML terms used.

## What the trading system does

The system **sells insurance on the S&P 500.** Each session it offers a contract: if SPY falls more than 3% over the next week, we pay out. Someone pays us a fee. Most weeks there is no fall and we keep it. Every position has a fixed maximum loss set before entry.

The machine-learning experiments in this repo are **not** part of the trading system. Those tried to predict market direction and failed. What trades is a rules engine with no model in it.

## What it returns, stated up front

About 4.8% a year on the account, with a 5.9% worst drawdown. SPY buy-and-hold returned about 15.0% a year over the same period, with a 32.1% drawdown. Risk-adjusted, that is a Sharpe of 0.56 against SPY's 0.69, roughly 80% of the index's risk-adjusted return, at a fifth of its drawdown. But risk-adjusted comparisons like this one are exactly what this project's own audit (Experiment 29) found reason to distrust: correcting for the 30 things tried against this data (the project's full [`EXPERIMENT.md`](EXPERIMENT.md) ledger), that 0.56 Sharpe is not statistically distinguishable from the best of 30 lucky tries (Deflated Sharpe Ratio = 0.20 at N=30). We are publishing that correction rather than the bare number, because a number nobody has stress-tested against how many times it was allowed to be wrong is not a number worth leading with.

| Trials tested (N) | 1 | 5 | 10 | 30 | 100 |
|---|---|---|---|---|---|
| Deflated Sharpe Ratio | 0.894 | 0.523 | 0.372 | 0.205 | 0.100 |

N=30 is this project's actual trial count as of today; it will rise again once further hypotheses are tested, so treat a bare "DSR=0.2" as dated the moment that happens. Full derivation, reproducible with no credentials or network in about 17 seconds (`python -m pipeline.falsify.audit`): [`EXPERIMENT_29_SHARPE_AUDIT.md`](EXPERIMENT_29_SHARPE_AUDIT.md).

This strategy is not designed to beat the market. It is sized so that it cannot blow up, and that same sizing is why it earns little. We would rather lead with those numbers than have you find them.

## The problem we found, and what fixed it

Our original test covered Feb 2024 onward, because that is where option price records start. That turned out to be the **calmest stretch of available history**: SPY fell more than 3% in a week 2.3% of the time in our window and 8.5% in the four years before it.

Testing further back required knowing what the fee would have been. The answer was CBOE's **VIX9D index**, the market's own 9-day volatility measure, free since 2011 and almost exactly our tenor. We rebuilt ten years of fees, validated the rebuild against the real prices we do have, and replayed 538 weeks.

**2018 lost 43% of what the entire decade earned.** One year.

The fix came from published research on volatility selling: when the VIX curve flattens or inverts, meaning the market expects more turbulence soon than later, stop selling. Skipping the worst third of weeks by that measure turned 2018 from a large loss into a small profit and **cut the worst drawdown by 77%**, at every distance, width, and cost level we tried.

**Then we tried to break that result, twice.** First, measured with skipped weeks earning cash instead of zero, the term-structure filter costs about 0.6 percentage points of annual return in exchange for roughly half the volatility and a 3x smaller drawdown, a Sharpe of 0.56 against 0.35 unfiltered. Second, and more decisively: a performance measure specifically designed to **not** be gameable by option-selling payoffs (the manipulation-proof measure of Goetzmann, Ingersoll, Spiegel & Welch, 2007 — ordinary Sharpe ratios are provably gameable by exactly this shape of strategy) reaches the same conclusion independently: the filter costs return relative to trading every week. Two different methods agreeing that this is insurance, not an edge, is stronger evidence than either alone. See [`EXPERIMENT_29_SHARPE_AUDIT.md`](EXPERIMENT_29_SHARPE_AUDIT.md).

**Third, and this is the finding we did not expect going in:** risk-matched to SPY's own volatility (levering the strategy roughly 11x to get there), the same non-gameable measure says it loses to plain SPY buy-and-hold at every level of risk aversion tested. The strategy's real value is not "beats the index" — it never claimed that at this size — it is a much smaller, much shallower ride to a smaller number, which is a legitimate thing to want but a different claim than a Sharpe ratio by itself communicates. We would rather say that once than let the Sharpe number say it for us.

Two caveats we would rather state than have you find:

First, the rule avoided all eight of 2018's losing weeks while skipping **63%** of that year, because its threshold was calibrated on 2016-2017, the calmest stretch on record. Skipping 63% at random would dodge about five of eight. Getting all eight beats chance at roughly p = 0.03, which is suggestive on one year and nothing more.

Second, **take 2018 out and the filter is a wash** — 0.59 Sharpe against 0.60 unfiltered, essentially identical. Nearly all of its value comes from one year. That is what a tail hedge looks like, and excluding your worst year is a diagnostic rather than a reason to drop the protection, but it means we have exactly one observation of the event the filter exists for.

**The mechanism, which we only understood after checking:** 2022 had a *worse* breach rate than 2018 (19.6% against 15.7%) and lost far less. 2022 was volatile throughout, so the fees were fat and absorbed the losses. 2018 spiked from a calm base, so the fees collected beforehand were tiny and the losses arrived undefended. **The thing that hurts a premium seller is a volatility spike from calm, not high volatility itself** — which is exactly what a flattening VIX curve sees and what a realized-volatility threshold cannot.

We tested our own idea first, skipping weeks when the offered fee was small. **It did nothing.** 2018 stayed exactly as bad. That negative result is logged next to the positive one.

## The two things here that are actually unusual

Neither the strategy nor the fix is new. Selling index put spreads has had a benchmark index since 1986 and filtering on the VIX curve is standard among professional volatility sellers. Two pieces of the machinery are less common:

**A regime-split validation gate.** Extending a short options history means reconstructing old prices, and everyone reports a single correlation for that reconstruction. Our first attempt scored 0.649, which looks fine. Split by volatility regime it priced calm weeks at 3% of reality and volatile weeks at 125% of it, two opposite errors cancelling into a respectable average. It produced a confident, completely false finding. So the reconstruction is now validated **per volatility quartile** and the build fails if any bucket drifts. The corrected model scores 0.972 and stays within 2-3% in every regime.

**The false-trip test.** Most systems test whether a risk filter helps. We replay every guard against historically *winning* weeks to measure how many good trades it blocks, with a pre-committed limit that forces us to loosen or drop it. It has already cost us one guard that was blocking 42% of winning weeks.

## Why we say all this instead of showing a bigger number

Any backtest can be made to look good by choosing the window. Ours looked good partly because of when it started. Saying so is what we would want to know if someone handed us this system.

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
3. Create a `.env` file in the project root with your Alpaca API credentials:
   ```
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ```

## Running the pipeline

Run everything (fetch data for all configured symbols, engineer features, run every model/experiment, export comparison tables) from the project root:
```
python -m pipeline.run_all
```

Symbols and date range are configured in [`pipeline/config.py`](pipeline/config.py).

Individual stages can also be run on their own, e.g.:
```
python -m pipeline.extract
python -m pipeline.transform
python -m pipeline.model.xgb_group_feature
```

## Project structure

```
pipeline/
  config.py              # single source of truth: symbols, date range
  extract.py              # pulls daily OHLCV bars from Alpaca per symbol
  transform.py            # feature engineering (SMA, RSI, momentum, volatility, ATR, etc.) + 5-day target label
  run_all.py              # orchestrates the full pipeline across all configured symbols
  model/
    baseline_model.py      # naive majority-class baseline
    logistic_model.py       # Logistic Regression baseline
    xgb_model.py             # single-split XGBoost
    xgb_stability.py         # XGBoost with TimeSeriesSplit cross-validation
    xgb_group_feature.py     # feature-group ablation sweep (all combinations)
    pooled_xgb_model.py      # pooled/panel XGBoost across all symbols at once
  panel.py                # builds the stacked multi-symbol panel + date-based split
output/
  data/                   # raw + engineered per-symbol datasets (gitignored)
  model/                  # multi-stock comparison result tables
raw_data_eda.ipynb        # exploratory data analysis notebook
```

## Guiding philosophy

Start simple → test → diagnose → add one thing → test again. Every result in this project is reported honestly, including negative/inconclusive findings — see `EXPERIMENT.md` for the full reasoning behind each experiment and why some promising-looking results were later revised or rejected.
