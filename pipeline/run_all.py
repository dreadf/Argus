import pandas as pd
from pipeline.config import SYMBOLS, START_DATE, END_DATE
from pipeline.extract import fetch_and_save
from pipeline.transform import engineer_features
from pipeline.model.baseline_model import run_baseline
from pipeline.model.xgb_model import run_xgb_model
from pipeline.model.logistic_model import run_logistic_model
from pipeline.model.xgb_stability import run_xgb_stability
from pipeline.model.xgb_group_feature import run_ablation

# Extract Data
fetch_and_save(SYMBOLS, START_DATE, END_DATE)

# Store the results
baseline_results = []
logistic_results = []
xgb_results = []
xgb_stability_results = []
xgb_ablation_results = []

for s in SYMBOLS:
    engineer_features(s)
    baseline_results.append(run_baseline(s))
    logistic_results.append(run_logistic_model(s))
    xgb_results.append(run_xgb_model(s))
    xgb_stability_results.append(run_xgb_stability(s))
    xgb_ablation_results.append(run_ablation(s))

# Transform to Data Frame for easy viewing
baseline = pd.DataFrame(baseline_results)
logistic = pd.DataFrame(logistic_results)
xgb = pd.DataFrame(xgb_results)
xgb_stability = pd.DataFrame(xgb_stability_results)

# To read which combination works accross stocks
xgb_ablation = pd.concat(xgb_ablation_results)
xgb_ablation_summary = xgb_ablation.groupby('label').agg(
    num_folds = ('folds_above_half', lambda s: (s >= 4).sum())
).sort_values('num_folds', ascending=False)

# Export into files
baseline.to_csv("output/model/multi_stock_baseline.csv")
logistic.to_csv("output/model/multi_stock_logistic.csv")
xgb.to_csv("output/model/multi_stock_xgb.csv")
xgb_stability.to_csv("output/model/multi_stock_xgb_stability.csv")
xgb_ablation.to_csv("output/model/multi_stock_xgb_ablation.csv")
xgb_ablation_summary.to_csv("output/model/xgb_ablation_summary.csv")