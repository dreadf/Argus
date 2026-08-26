import pandas as pd
import numpy as np
from sklearn import metrics
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from pipeline.config import SYMBOLS

def run_logistic_model(symbol):
    df = pd.read_csv(f'output/data/engineered_{symbol}.csv')
    #print(df.columns)

    # Separate features (x) and target (y0
    x = df.drop(columns=['target_5d', 'fwd_5d_return', 'close', 'high', 'open', 'low', 'timestamp', 'volume', 'vwap', 'SMA_10', 'SMA_30'])
    y = df['target_5d']

    # Split the dataset into train and test by its chronological order
    pct_split = 0.8
    split = int(len(df) * pct_split)

    # Make the test and train variables for each X and Y dataframe to store the split results in each of them
    x_train = x.iloc[:split]
    x_test = x.iloc[split:]
    y_train = y.iloc[:split]
    y_test = y.iloc[split:]

    # Scale our features
    # Since logistic regression are sensitive to feature scales, we have to normalize them.
    # We can't have RSI with 0-100 ranges and daily_return in small decimals ranges
    # StandardScaler() converts the feature into Z-Score, where mean = 0 and SD = 1
    scaler = StandardScaler()
    # Then we fit the scaler into our train features, fit will take the average and the SD of this dataset and converts the data
    x_train_scaled = scaler.fit_transform(x_train)
    # IMPORTANT: For the train features, use transform instead of fit to prevent data leakage,
    # Transofrm will take the average and SD from the test dataset to prevent any future data leaking
    x_test_scaled = scaler.transform(x_test)
    # Then these will create numpy arrays, not pandas dataframe

    # Train the model using the logistic regression
    model = LogisticRegression()
    model.fit(x_train_scaled, y_train) 

    # Generate predictions and evaluate the model
    # We're going to predict the x_test with the model weights
    y_pred = model.predict(x_test_scaled)
    # To see the confidence score we do:
    pred_proba = model.predict_proba(x_test_scaled)
    # Filter only for the positive confidence scores
    positive_proba = pred_proba[:,1]

    # Evaluation
    # Accuracy
    acc_pred = metrics.accuracy_score(y_test, y_pred)
    # ROC-AUC
    # Model's output is actually confidence score, it frames how confidence is the model in its decision (0 / 1)
    # ROC AUC is measuring how often does the model's confidence score correctly rank the "Up" day higher
    rocauc_pred = metrics.roc_auc_score(y_test, positive_proba)
    # print(f'Model Accuracy: {acc_pred}')
    # print(f'Model ROC-AUC: {rocauc_pred}')

    # Coefficient Check
    # We use this to check the coefficient, since coefficient actually tells us how important a feature is
    # Pair the weights with your feature column names into a labeled Pandas Series
    coef = pd.Series(data=model.coef_[0], index=x.columns)
    # Sort them based on the magnitude
    sorted_coef = coef.abs().sort_values(ascending=False)
    # print(f'\nFeature Importance:\n{sorted_coef.round(4)}')
    # print(f'\nOriginal Weights: \n{coef.loc[sorted_coef.index].round(4)}')

    return {
        'symbol': symbol,
        'accuracy': acc_pred,
        'ROC_AUC': rocauc_pred,
    }

if __name__ == '__main__':
    for s in SYMBOLS:
        run_logistic_model(s)