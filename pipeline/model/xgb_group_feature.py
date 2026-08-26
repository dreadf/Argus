from itertools import combinations

import numpy as np
import pandas as pd
from sklearn import metrics
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

df = pd.read_csv('output/data/engineered_data.csv')

pd.set_option('display.max_column', None)
pd.set_option('display.width', 1000)

# Feature
x = df.drop(columns=['symbol','target_5d', 'fwd_5d_return', 'close', 'high', 'open', 'low', 'timestamp', 'volume', 'vwap', 'SMA_10', 'SMA_30'])
print(x.head())
# Target set
y = df['target_5d']

# Split into the features into groups
# Group A: Price/Return (Has the price been going up or down, and by how much over some window)
group_a = ['daily_return', 'momentum_5','momentum_10', 'momentum_20']

# Group B: Trend/Technical (Is the moment unusual relative to its own recent pattern?)
# RSI summarizes trend strength (is this overbought/oversold)
# distance-from-SMA summarizes how stretched the prie is from the average price
group_b = ['RSI', 'distance_SMA10', 'distance_SMA30']

# Group C: Volatility (How much the stock swings, regardless of the direction)
group_c = ['volatility_5','volatility_10', 'ATR_5', 'ATR_10']

# Group D: Volume (How many people are trading)
group_d = ['volume_spike', 'trade_count']

# Build the feature sets
# We'll test A alone, then A+B, then A+B+C
groups = {
    'A': group_a,
    'B': group_b,
    'C': group_c,
    'D': group_d,
}
feature_sets = {

}

for size in range(1, len(groups)+1):
    # Calculate the combinations based on the size its on, size = 1 means a combination of 1 item
    for combo in combinations(groups.keys(), size):
        label = '+'.join(combo)
        columns = []
        # We add it all up here for the combination
        for name in combo:
            columns = columns + groups[name]
        feature_sets[label] = columns

# Split the dataset
tcsv = TimeSeriesSplit(n_splits=5)
results = []

for label, columns in feature_sets.items():
    x_subset = x[columns]
    for i, (train_idx, test_idx) in enumerate(tcsv.split(x_subset)):
        x_train, x_test = x_subset.iloc[train_idx], x_subset.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        model = XGBClassifier (
                    n_estimators=50,
                    max_depth=2,
                    subsample=0.8,
                    learning_rate=0.1,
                    eval_metric='logloss',   # Evaluation metric for training validation
                    reg_lambda=1.0,          # L2 Regularization: penalizes extreme predictions (Default is 1.0)
                    reg_alpha=0.1,          # L1 regularization term on weights (deletes weak branches)
            )

        model.fit(x_train, y_train)
        y_pred = model.predict(x_test)
        pred_prob = model.predict_proba(x_test)[:,1]

        # Evaluation
        acc = metrics.accuracy_score(y_test, y_pred)
        roauc = metrics.roc_auc_score(y_test, pred_prob)

        # We append the result into a list
        results.append(
            {
                'label': label,
                'fold': i,
                'accuracy': acc,
                'roc_auc': roauc
            }
        )

# DataFrame can't be append, so it must be done, outside of the loop
results = pd.DataFrame(results)
print('\nCROSS VALIDATION EVALUATION\n')

# We summarize it into a table instead
summary = results.groupby('label').agg(
    auc_mean=('roc_auc', 'mean'),
    auc_std=('roc_auc', 'std'),
    acc_mean=('accuracy', 'mean'),
    # An inline function that sums roc_auc that is more than 0.5
    folds_above_half=('roc_auc', lambda s: (s >= 0.5).sum())
).sort_values(['folds_above_half', 'auc_mean'], ascending=False)

print(summary.round(3))


# Results of this experiment

# Group B is the most stable with 5 out of 5 folds that has above 0.5 in terms of accuracy and ROC-AUC
# Then, Group A was also stable with 4 out of 5 folds. This means that group B has the most stable and
# consistent pattern. If we compare it to the group C and D, they each both have 2 fold each that is
# higher than 0.5 (which indicate one lucky fold).

# Though it is interesting to see, if we combine A and B the result went down (group A + group B).
# However, when A+D is added up, it went above 0.5 on all 5 folds. IT has the highest AUC and has
# the highest AUC. Though C always hurts the result, so volatility makes the prediction worst.
