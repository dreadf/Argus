import pandas as pd
import numpy as np
from sklearn import metrics

# Import File
df = pd.read_csv('output/data/engineered_data.csv')

pd.set_option('display.max_column', None)
pd.set_option('display.width', 1000)

# Data Split
split = int(len(df) * 0.8)
train = df.iloc[:split]
test = df.iloc[split:]

# Check target (target_5d) class imbalance
print(train['target_5d'].value_counts(normalize=True), '\n')

# Take the major class in the target feature
major = train['target_5d'].value_counts(normalize=True).idxmax()

# Naive Predictions
# We're going to make a baseline on "always predict majority class is gonna happen"
baseline = np.full(test['target_5d'].shape, major)

# Baseline Acccuracy
acc_baseline = metrics.accuracy_score(test['target_5d'], baseline)
recall_baseline = metrics.recall_score(test['target_5d'], baseline)
f1_baseline = metrics.f1_score(test['target_5d'], baseline)
print(f'Baseline Accuracy: {acc_baseline:.2f}')
print(f'Baseline Recall: {recall_baseline:.2f}')
print(f'Baseline F1: {f1_baseline:.2f}')