import pandas as pd
import numpy as np
from sklearn import metrics
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

df = pd.read_csv('output/data/engineered_data.csv')

pd.set_option('display.max_column', None)
pd.set_option('display.width', 1000)

# Separate features (x) and target (y)
x = df.drop(columns=['symbol','target_5d', 'fwd_5d_return', 'close', 'high', 'open', 'low', 'timestamp', 'volume', 'vwap', 'SMA_10', 'SMA_30'])
y = df['target_5d']

# Split Chronogically
pct = 0.8
split = int(len(df) * pct)
# Create 4 dataframes
x_train = x.iloc[:split]
x_test = x.iloc[split:]
y_test = y.iloc[split:]
y_train = y.iloc[:split]

# we don't need to scale the dataframes because tree models doesn't care about them

# XGBoost Model
# XGBoost is a tree based model that doesn't look at other rows when training
# Hyperparameter:
# n_estimators: How many trees to build (usually 100 is the default)
# max_depth: How deep each tree can go (keep this small on 3, because we have 1300 training rows only, a deep tree might cause overfit)
# learning_rate: How much each tree corrects the previous one
# eval_metric='logloss': Silenses a deprecation warning
# subsample: XGBoost randomly picks 80% of your historical dates to build Tree #1. Then it throws them back, and randomly picks a different 80% of dates to build Tree #2.
# colsample: It controls columns. At a setting of 0.8, if you have 10 engineered indicators, each tree is only allowed to look at a random selection of 8 individual indicators. It prevents the model from relying exclusively on a single dominant feature.
model = XGBClassifier(
    n_estimators=50, 
    max_depth=2, 
    subsample=0.8,  
    learning_rate=0.1, 
    eval_metric='logloss',   # Evaluation metric for training validation
    reg_lambda=1.0,          # L2 Regularization: penalizes extreme predictions (Default is 1.0)
    reg_alpha=0.1,)          # L1 regularization term on weights (deletes weak branches)

model.fit(x_train, y_train)

# Predict
y_pred = model.predict(x_test)
pred_probs = model.predict_proba(x_test)[:,1]

# Evaluate
acc = metrics.accuracy_score(y_test, y_pred)
print(f'Model Accuracy: {acc}')
roauc = metrics.roc_auc_score(y_test, pred_probs)
print(f'Model ROA AUC: {roauc}')

# Overfitting check: compare train accuracy vs test accuracy
train_pred = model.predict(x_train)
train_acc = metrics.accuracy_score(y_train, train_pred)
print(f'\nTrain Accuracy: {train_acc}')
print(f'Test Accuracy:  {acc}')
print(f'Gap (train - test): {train_acc - acc}')

# Feature Importance
importance = pd.Series(data=model.feature_importances_, index=x.columns)
sorted_importance = importance.sort_values(ascending=False).abs()
print(f'\nFeature Importance:\n{sorted_importance.round(4)}')
print(f'\nOriginal Weights:\n{importance[sorted_importance.index].round(4)}')

