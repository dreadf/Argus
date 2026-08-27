# Stock Direction Prediction — 5-Day AAPL/MSFT/JPM/KO/XOM Experiment

A learning-first, experiment-driven ML pipeline built for the **Alpaca AI Trading Agents Hackathon**, investigating a narrow research question:

> **Can market-derived information from Alpaca historical data provide a robust out-of-sample signal for whether a stock will have a positive or negative return over the next 5 trading days?**

Full research plan and philosophy: [`Project_Context_and_Plan_Updated.md`](Project_Context_and_Plan_Updated.md) and [`ML_Experiment_Plan.md`](ML_Experiment_Plan.md).
Full experiment log (what was tried, why, results, interpretation): [`EXPERIMENT.md`](EXPERIMENT.md).

## Key finding so far

Across a naive baseline, Logistic Regression, XGBoost, single-symbol feature ablation, and a multi-symbol generalization check (AAPL, MSFT, JPM, KO, XOM), **no feature combination tested shows a robust, cross-stock predictive edge** for 5-day direction. A promising-looking result on AAPL alone (`price/return + volume` features) did not replicate on other symbols. The closest thing to a repeatable pattern (`trend/technical + volume` features) only held up on 2 of 5 stocks (KO, XOM). See [`EXPERIMENT.md`](EXPERIMENT.md) for full detail, including the diagnostic process (leakage checks, chronological validation, overfitting checks, cross-validation, multiple-testing caveats).

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
output/
  data/                   # raw + engineered per-symbol datasets (gitignored)
  model/                  # multi-stock comparison result tables
raw_data_eda.ipynb        # exploratory data analysis notebook
```

## Guiding philosophy

Start simple → test → diagnose → add one thing → test again. Every result in this project is reported honestly, including negative/inconclusive findings — see `EXPERIMENT.md` for the full reasoning behind each experiment and why some promising-looking results were later revised or rejected.
