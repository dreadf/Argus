import pandas as pd
import numpy as np
from sklearn import metrics
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

df = pd.read_csv('output/data/engineered_data.csv')

pd.set_option('display.max_column', None)
pd.set_option('display.width', 1000)

# Separate features (x) and target (y)
x = df.drop(columns=['symbol','target_5d', 'fwd_5d_return', 'close', 'high', 'open', 'low', 'timestamp', 'volume', 'vwap', 'SMA_10', 'SMA_30'])
y = df['target_5d']

# Split the dataset
tscv =  TimeSeriesSplit(n_splits=5)
results = []

# Loop through to timeseries splitter
for i, (train_idx, test_idx) in enumerate(tscv.split(x)):
    x_train, x_test = x.iloc[train_idx], x.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    model = XGBClassifier(
        n_estimators=50, 
        max_depth=2, 
        subsample=0.8,  
        learning_rate=0.1, 
        eval_metric='logloss',   # Evaluation metric for training validation
        reg_lambda=1.0,          # L2 Regularization: penalizes extreme predictions (Default is 1.0)
        reg_alpha=0.1,)          # L1 regularization term on weights (deletes weak branches)

    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)
    pred_prob = model.predict_proba(x_test)[:,1]

    # Evaluation
    acc = metrics.accuracy_score(y_test, y_pred)
    roauc = metrics.roc_auc_score(y_test, pred_prob)

    results.append(
        {
            'fold': i,
            'accuracy': acc,
            'roc_auc': roauc
        }
    )

results = pd.DataFrame(results)
print('CROSS VALIDATION EVALUATION')
rocauc_mean = results['roc_auc'].mean()
rocauc_std = results['roc_auc'].std()
acc_std = results['accuracy'].std()
acc_mean = results['accuracy'].mean()

print(f'ROC AUC Mean: {rocauc_mean}')
print(f'ROC AUC Std: {rocauc_std}')
print(f'Accuracy Mean: {acc_mean}')
print(f'Accuracy Std: {acc_std}')

