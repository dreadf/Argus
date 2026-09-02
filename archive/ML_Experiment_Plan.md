# ML Experiment Plan — 5-Day Stock Direction Project

## 1. Research Question

> **Can market-derived information from Alpaca historical data provide a robust out-of-sample signal for whether a stock will have a positive or negative return over the next 5 trading days?**

This is the first and only ML question that needs to be answered before expanding the architecture.

---

## 2. Why Start With One Model?

Stock-market data are noisy and adaptive. Adding models, indicators, horizons, news, fundamentals, or other data sources can create additional degrees of freedom and increase the risk of overfitting.

Therefore:

> **Every new component is an experiment, not a requirement.**

The first objective is to establish whether there is any robust signal at all.

---

## 3. Initial Prediction Task

For each observation at time `t`:

`Forward_5D_Return = (Close[t+5] / Close[t]) - 1`

Initial label:

```text
if Forward_5D_Return > 0:
    y = 1
else:
    y = 0
```

The model therefore estimates:

`P(Forward_5D_Return > 0 | information available at t)`

This is a **direction-classification model**.

It is not initially responsible for predicting:

- exact future price
- expected profit
- entry price
- take-profit
- stop-loss
- position size

Those are separate downstream questions.

---

# 4. Experiment 0 — Naive Baseline

Before ML, establish a trivial benchmark.

Possible baselines:

- Always predict UP.
- Predict the majority class.
- A simple momentum-based rule.

The purpose is to answer:

> **Does ML beat something embarrassingly simple?**

If not, more sophisticated ML is not justified.

---

# 5. Experiment 1 — Logistic Regression

### Input

Start with a small, interpretable feature set:

- lagged returns
- 5/10/20-day momentum
- moving-average distance
- RSI
- rolling volatility
- volume ratio

### Output

`P(positive 5-day return)`

### Why?

It provides an interpretable linear baseline.

Question:

> **Is there a reasonably linear relationship between these market features and 5-day direction?**

---

# 6. Experiment 2 — XGBoost

Use approximately the same feature set.

### Question

> **Does a nonlinear tree-based model extract additional signal beyond Logistic Regression?**

Compare:

- Accuracy
- ROC-AUC
- Precision/Recall/F1 where useful
- Calibration
- Out-of-sample stability

Do not select the winner solely on training performance.

---

# 7. Experiment 3 — Feature Ablation

This is one of the most important experiments in the project.

Instead of dumping every indicator into XGBoost, add feature groups sequentially.

### A — Price / return

- lagged returns
- momentum

### B — + Trend / technical

- SMA/EMA
- price-to-SMA distance
- RSI
- MACD if justified

### C — + Volatility

- rolling standard deviation
- ATR-type features
- range measures

### D — + Volume

- volume change
- relative volume

### E — + Market context

- market return
- sector/market-relative performance where available

### F — Optional external data

Only if justified:

- fundamentals
- news/sentiment
- macro
- alternative data

### Decision rule

Keep a feature group only if it produces a meaningful and robust improvement on unseen data.

---

# 8. Experiment 4 — Robust Time-Series Validation

## Never randomly shuffle the entire dataset.

Use chronological splits.

Example:

```text
TRAIN                    VALIDATE
2018 ───────────── 2022   2023

TRAIN                         VALIDATE
2018 ───────────────── 2023   2024

TRAIN                              TEST
2018 ───────────────────── 2024   2025
```

A rolling/walk-forward procedure should be used for model selection.

Reserve a final period as an untouched holdout.

### Important checks

- Look-ahead bias
- Feature leakage
- Target leakage
- Overlapping-label leakage
- Survivorship bias where applicable
- Data snooping / multiple testing

If overlapping 5-day labels make ordinary time-series validation insufficient, investigate purged and embargoed validation.

---

# 9. What Does "Good" Mean?

## Prediction metrics

Use several metrics rather than one number:

- Accuracy
- ROC-AUC
- Precision
- Recall
- F1
- Calibration / reliability
- Confusion matrix

### Important

A 55% accuracy model is not automatically useful.

A 60% model is not automatically useful either.

The model must be evaluated in an economic/trading context.

---

# 10. Experiment 5 — Simple Backtest

Only after establishing an out-of-sample prediction signal.

The first backtest should be intentionally simple.

Example conceptual flow:

```text
Model probability
      ↓
Simple threshold
      ↓
Trade / No Trade
      ↓
Fixed holding period or simple exit rule
      ↓
Portfolio simulation
```

Compare against:

- Buy-and-hold benchmark
- Naive trading strategy

Include realistic assumptions for:

- transaction costs
- slippage
- turnover

Measure:

- cumulative return
- annualized return
- volatility
- Sharpe ratio
- maximum drawdown
- number of trades
- turnover

The purpose is not to find the perfect trading strategy yet.

The purpose is to determine whether the predictive signal has **economic value**.

---

# 11. Only If the Baseline Works: Extension Experiments

These are optional research questions.

## A. Magnitude Model

### Question

> **Can we predict how large the 5-day return will be?**

Instead of:

`y = 0/1`

use:

`y = Forward_5D_Return`

This is a regression model.

Example output:

```text
P(positive 5D return) = 0.72
Expected 5D return     = +2.4%
```

### Test

Compare:

1. Direction model alone
2. Direction + magnitude model

If magnitude does not improve decision/backtest quality, remove it.

---

# 12. Risk Is Initially a Separate Calculation, Not Another ML Model

Do not immediately create a "risk model."

Initially calculate simple risk statistics such as:

- rolling volatility
- ATR/range
- recent drawdown
- realized volatility

Example:

```text
Direction model:
P(up) = 72%

Risk statistics:
20D volatility = high
```

The decision layer can use both.

Only create a separate learned risk model if experiments demonstrate that the simple measures are inadequate.

---

# 13. Trading Plan: Where Does Entry / TP / SL Belong?

These are primarily **strategy-layer concepts**, not necessarily separate ML models.

Conceptually:

```text
                 ML MODEL
                    ↓
             P(up in 5 days)
                    ↓
              STRATEGY LAYER
                    ↓
        ┌───────────┼───────────┐
        ↓           ↓           ↓
      Entry         TP          SL
        │           │           │
        └───────────┼───────────┘
                    ↓
                 BACKTEST
```

The first version should use simple, predefined rules rather than another ML model.

A later research extension can test **triple-barrier labeling**, where the outcome is determined by whichever happens first:

- upper barrier
- lower barrier
- time horizon

This changes the prediction target rather than simply adding another model.

---

# 14. Experiment 6 — Multiple Horizons

Only after the 5-day model is understood.

Possible horizons:

- 1-day
- 5-day
- 10-day

These would answer different questions.

For example:

```text
1-day model  → P(positive 1D return)
5-day model  → P(positive 5D return)
10-day model → P(positive 10D return)
```

Do **not** assume that all three should exist.

Test:

```text
5-day model
        VS
5-day + 1-day information
        VS
5-day + 10-day information
```

The extra horizon must demonstrate incremental out-of-sample value.

---

# 15. Experiment 7 — Meta-Labeling (Optional / Advanced)

Only consider this if the primary model already works.

The primary model creates a signal:

```text
Primary model → BUY signal
```

A secondary model predicts:

```text
Should this signal be acted upon?
```

This can potentially filter weak signals, but it adds another model, another target, and additional overfitting risk.

Therefore it is explicitly **not part of the initial architecture**.

---

# 16. Experiment Matrix

| Experiment | Model | Target | Main Question |
|---|---|---|---|
| 0 | Naive | 5D direction | Is there a trivial baseline? |
| 1 | Logistic | 5D direction | Is there linear signal? |
| 2 | XGBoost | 5D direction | Does nonlinear ML help? |
| 3 | XGBoost | 5D direction | Which feature groups matter? |
| 4 | Best baseline | 5D direction | Is the signal robust out-of-sample? |
| 5 | Best model + simple strategy | Trading outcome | Does prediction have economic value? |
| 6 | Regression model | 5D return | Does magnitude add information? |
| 7 | Multiple models/horizons | 1D/5D/10D | Do horizons add information? |
| 8 | Meta-model | Signal quality | Can weak signals be filtered? |

Experiments 6–8 are **optional** and should only happen if earlier experiments justify them.

---

# 17. Decision Tree for the Project

```text
START
  ↓
Can Alpaca data + simple features predict 5D direction?
  │
  ├── NO
  │    ↓
  │  Diagnose data / features / target / validation
  │    ↓
  │  Do not add complexity blindly
  │
  └── YES
       ↓
Does XGBoost beat simple baselines out-of-sample?
       │
       ├── NO → Keep simpler model / investigate why
       │
       └── YES
            ↓
Does the signal produce economic value in a realistic backtest?
            │
            ├── NO → Diagnose strategy / costs / calibration
            │
            └── YES
                 ↓
       Identify the biggest unanswered question
                 ↓
       Add ONE extension
                 ↓
               TEST
                 ↓
          Keep or remove it
```

---

# 18. The Rule Against Noise

Before adding anything, write:

> **Hypothesis:** What problem does this solve?
>
> **New information:** What does it provide that the current model does not?
>
> **Evaluation:** What metric will determine whether it helped?
>
> **Removal criterion:** When will we delete it?

Example:

> **Hypothesis:** 1-day predictions contain information that the 5-day model misses.
>
> **New information:** Short-horizon market direction.
>
> **Evaluation:** Does adding the 1-day signal improve final holdout performance and risk-adjusted backtest results?
>
> **Removal criterion:** If no robust improvement, remove the 1-day model.

This keeps the project experimental rather than architecture-driven.

---

# 19. Recommended Initial Stack

### Data
- Alpaca API
- pandas

### Modeling
- scikit-learn
- XGBoost

### Evaluation
- scikit-learn metrics
- custom walk-forward evaluation
- custom backtesting logic initially

### Trading
- Alpaca paper trading API

### Application
- Streamlit initially

### Optional later
- MCP
- LLM interface
- richer frontend

---

# 20. First Milestone

Do not move to agent design yet.

Complete this first:

```text
Alpaca
  ↓
Historical OHLCV
  ↓
Feature Engineering
  ↓
5-Day Forward Return
  ↓
Naive Baseline
  ↓
Logistic Regression
  ↓
XGBoost
  ↓
Walk-Forward Evaluation
  ↓
Final Holdout
```

### Success criterion

Not:

> "Get 80% accuracy."

Instead:

> **Establish whether there is a statistically and economically meaningful, robust out-of-sample signal, and understand which inputs/model choices contribute to it.**

Only after this milestone should the project architecture expand.
