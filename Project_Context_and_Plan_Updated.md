# Project Context & Hackathon Battle Plan — Updated

## 🌍 Context

This project originally started as an end-to-end data science portfolio piece designed to extract stock data (via `yfinance`), predict 5-day trends, and display them on a frontend dashboard. It has since evolved into a competitive project for the **Alpaca AI Trading Agents Hackathon**.

**Important:** The project is intentionally being developed as a learning-first, experiment-driven system. The architecture should not become more complex unless experiments show that an additional component provides measurable value.

## 🎯 The BIG Goal

My personal goal is to learn how to code and set up projects based on real work cases and scenarios through this hands-on experience.

The overarching technical objective is to build an **Autonomous AI Trading Agent** focused on *risk-aware decision making*. The first research question is deliberately narrow:

> **Can market-derived information from Alpaca data provide a robust out-of-sample signal for whether a stock will have a positive or negative return over the next 5 trading days?**

The initial system will therefore use **one primary ML model and one 5-day prediction horizon**. The model will not directly be treated as a "buy/sell oracle". Its prediction will feed a separate decision/risk layer, which can later be connected to Alpaca paper trading.

The eventual product may include a dashboard, an agent layer, paper-trading execution, and an LLM/MCP interface, but these are downstream of the core ML experiment.

*Note: The product idea MAY CHANGE. If research or experiments reveal a better approach, a component that adds noise rather than signal, or a stronger way to differentiate the product, the scope should be adapted.*

---

# 🧭 Core Project Philosophy

### Start simple → test → diagnose → add one thing → test again.

Do **not** assume that more models, more indicators, more horizons, or more data sources automatically improve performance.

Every proposed extension must answer:

1. What new question does this component answer?
2. What information does it add that the current system does not have?
3. Does it improve out-of-sample predictive or trading performance?
4. Does the improvement survive realistic validation and transaction costs?
5. If not, remove it.

This is especially important because stock-market ML research frequently reports modest and fragile predictive gains, with major risks from leakage, data snooping, overfitting, and unrealistic backtests.

---

# 🚀 Current Phase: Phase 1 — Environment & ETL

**Target:** Now → Aug 27, flexible.

### Goal
Get clean historical market data flowing automatically through Alpaca and establish a reproducible dataset.

### Tasks

- [ ] Create/configure Alpaca paper-trading account.
- [ ] Secure Alpaca API credentials safely.
- [ ] Set up VS Code and Python environment.
- [ ] Install required libraries (`alpaca-py`, `pandas`, etc.).
- [ ] Write `extract.py` to pull historical daily OHLCV data.
- [ ] Store/inspect raw data.
- [ ] Clean missing/duplicate/inconsistent observations.
- [ ] Build a feature-engineering pipeline.
- [ ] Start with market-derived features such as:
  - returns/log returns
  - moving averages / distance from moving averages
  - momentum
  - RSI
  - rolling volatility
  - volume / relative volume
  - price range / ATR-type measures
- [ ] Ensure every feature uses information available **at or before the prediction timestamp**.

### Deliverable
A clean, reproducible dataset where each row represents the information available at time `t`.

---

# 🧠 Phase 2 — The Brain: First ML Experiment

**Target:** Begin immediately after Phase 1 is stable.

## Goal
Test whether market-derived features can predict **5-day forward return direction** out-of-sample.

### Target definition

For a stock price `P_t`:

`Forward_5D_Return = (P_{t+5} / P_t) - 1`

Initial classification target:

- `1` if Forward_5D_Return > 0
- `0` otherwise

This is the **direction model**.

### Important change from the previous plan

Do **not** make ARIMA → XGBoost the mandatory progression. ARIMA is a time-series forecasting baseline and is not naturally aligned with the initial binary classification target.

Instead, establish a simple classification baseline first:

1. Naive baseline
2. Logistic Regression
3. XGBoost

Random Forest can be added if useful for comparison.

### Validation

Do not randomly shuffle the financial time series.

Use chronological / walk-forward validation and keep a final untouched holdout period for the final evaluation.

Where overlapping labels create leakage risk, investigate purged/embargoed validation.

### Metrics

**Prediction:**
- Accuracy
- Precision / Recall / F1 where appropriate
- ROC-AUC
- Probability calibration
- Class balance

**Trading/economic:** only after a strategy is defined:
- cumulative return
- annualized return
- Sharpe ratio
- maximum drawdown
- volatility
- turnover
- transaction costs / slippage assumptions

### Core experiment

> **Can XGBoost extract useful 5-day directional signal beyond simple baselines?**

If not, do not immediately add more models or data sources. Diagnose the failure first.

---

# 🔬 Phase 2B — Feature Experiments / Ablation

Only after the baseline pipeline works.

Instead of throwing every possible variable into the model, test feature groups separately.

### Suggested sequence

**Experiment A — Price/return information**
- lagged returns
- momentum
- price changes

**Experiment B — + Technical indicators**
- RSI
- moving-average features
- trend features

**Experiment C — + Volume**
- volume change
- relative volume

**Experiment D — + Market context**
- broad-market return
- sector/market-relative features if available

Later, if justified:

**Experiment E — + Other information**
- fundamentals
- news/sentiment
- macro variables
- alternative data

The objective is not to maximize the number of features. The objective is to determine which feature groups provide **incremental out-of-sample signal**.

---

# 🧪 Phase 2C — Only Add Complexity When a Failure Justifies It

The initial project has **one model and one horizon**.

Additional components are hypotheses, not requirements.

## Possible future extension: Magnitude model

Question:

> "Instead of only predicting whether the return is positive, can we predict the magnitude of the 5-day return?"

Target:

`Forward_5D_Return`

This becomes a regression problem.

Only build it if the direction model demonstrates useful signal and the project has a clear reason to need magnitude information.

## Possible future extension: Risk/uncertainty model

A separate ML risk model is **not required initially**.

Start with simple statistical risk measures such as historical/rolling volatility and drawdown.

Only introduce a learned risk model if experiments show that simple risk measures are insufficient.

## Possible future extension: Multiple horizons

Possible experiment:

- 1-day direction
- 5-day direction
- 10-day direction

These can be separate models because they answer different forecasting questions.

Do not assume that multiple horizons improve the system. Test whether their predictions provide incremental information beyond the 5-day model.

## Possible future extension: Alternative labels / Triple Barrier

Instead of the initial positive/negative 5-day label, a later experiment could define outcomes based on:

- upper barrier reached first
- lower barrier reached first
- maximum holding period reached first

This may align better with trading decisions, but it is an **alternative target design**, not an additional mandatory model.

## Possible future extension: Meta-labeling

A secondary model could learn whether an existing primary signal should be acted upon.

This should only be considered after establishing that the primary model is useful and that filtering its signals is a real problem.

---

# ⚙️ Phase 3 — Decision & Paper-Trading Layer

**Only after the predictive experiment is credible.**

### Important architecture distinction

The ML model answers:

> **What might happen?**

The strategy/risk layer answers:

> **What should we do with that information?**

The backtester answers:

> **Would that decision have worked historically?**

### Initial decision architecture

```text
Alpaca data
    ↓
Feature engine
    ↓
5-day direction model
    ↓
P(positive 5-day return)
    ↓
Simple risk/decision rules
    ↓
TRADE / HOLD / NO TRADE
    ↓
Backtest
    ↓
Alpaca Paper Trading
```

Do not let the ML model directly output a blind "BUY" instruction.

### Trading-plan concepts

Entry, take-profit, stop-loss, maximum holding period, position limits, and transaction-cost assumptions belong primarily to the **strategy/risk layer**, not necessarily to the prediction model.

These rules should be evaluated through backtesting.

---

# 🤖 Phase 4 — Agent Layer

**Target:** Aug 28 – Sep 2, flexible.

### Goal
Turn the validated model + strategy into an automated paper-trading workflow.

### Components

1. Receive/update market data.
2. Generate features.
3. Generate model prediction.
4. Apply decision/risk rules.
5. Record the decision.
6. If conditions are satisfied, send a **paper-trading** order through Alpaca.
7. Track open/closed positions and outcomes.
8. Log every model prediction and decision for later analysis.

The agent should be auditable: every action should have a recorded prediction, input state, decision rule, and outcome.

---

# 💻 Phase 5 — Visualization / Application

**After the core pipeline works.**

The UI should expose the system rather than become the system.

### Possible dashboard sections

**Market view**
- price chart
- technical indicators
- recent volume

**Model view**
- predicted probability of positive 5-day return
- historical model performance
- confidence/calibration information
- feature importance / explanation

**Decision view**
- current signal
- decision: trade / hold / no trade
- risk metrics
- current portfolio exposure

**Backtest view**
- equity curve
- benchmark comparison
- Sharpe
- maximum drawdown
- trade history

**Agent activity**
- recent decisions
- paper orders
- open/closed positions
- model reasoning/logs

Streamlit is sufficient for an initial prototype; a custom frontend can be considered if time permits.

---

# 💬 Phase 6 — LLM / MCP Layer

This is an interface/explanation layer, not the primary stock predictor.

Possible user questions:

- "Why is the model bullish?"
- "What features contributed most to the prediction?"
- "How has this model performed historically?"
- "Why did the agent choose no trade?"
- "What is the current portfolio risk?"

The LLM should retrieve structured outputs from the quantitative system and explain them. It should not replace the quantitative model with free-form financial guesses.

---

# 📊 Final Evaluation Framework

The final project should distinguish **prediction quality** from **trading quality**.

### Prediction quality

- Does the model beat the naive baseline out-of-sample?
- Is probability calibration reasonable?
- Does performance persist across different time periods?
- Which feature groups actually matter?

### Strategy quality

- Does converting predictions into decisions improve results?
- How sensitive are results to thresholds?
- What happens after transaction costs and slippage?
- What is the maximum drawdown?
- How stable is performance across market regimes?

### Robustness

- Walk-forward validation
- Final untouched holdout
- Leakage checks
- Survivorship-bias checks where applicable
- Multiple-testing/data-snooping awareness
- Sensitivity analysis

---

# 🧩 Final Architecture — Target State

```text
                    USER
                     │
                     ▼
              Dashboard / Chat
                     │
                     ▼
              Agent / Orchestrator
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
   Decision Layer             Model Layer
        │                         │
        │                  5-day direction
        │                         │
        │                    P(positive)
        │                         │
        └────────────┬────────────┘
                     ▼
              Risk / Strategy
                     │
             TRADE / HOLD / NO TRADE
                     │
                     ▼
              Backtest / Logging
                     │
                     ▼
              Alpaca Paper Trading
                     ▲
                     │
                Market Data
```

### The key principle

**The target architecture is allowed to become simpler than this.**

If experiments show that a single XGBoost model + simple risk rules works better than a collection of specialized models, the simpler architecture wins.

---

# 📚 Research Basis

The accompanying research review indicates that ML stock-prediction literature covers movement classification, return regression, portfolio/trading strategy, and execution prediction, with inputs ranging from historical prices and technical indicators to fundamentals, news/sentiment, macro data, and order-book information. It also emphasizes that reported gains can be modest and fragile, making chronological validation, out-of-sample testing, and leakage/data-snooping controls central to credible experiments. fileciteturn2file1L58-L64

The review also shows that model complexity has progressed from classical statistical/ML methods to tree ensembles, RNN/LSTM, CNN, Transformers, GNNs, and RL, but this progression should not be interpreted as evidence that the most complex model is automatically the best choice. fileciteturn2file1L63-L64

---

# 🏁 Immediate Next Steps

1. Finish Alpaca historical-data extraction.
2. Build a clean OHLCV dataset.
3. Implement feature engineering.
4. Define the 5-day forward-return target.
5. Establish a naive baseline.
6. Train Logistic Regression.
7. Train XGBoost.
8. Perform chronological/walk-forward evaluation.
9. Compare prediction metrics.
10. Only after that, build the first simple backtest.

**Do not build additional models until the baseline experiment produces a concrete reason to do so.**
