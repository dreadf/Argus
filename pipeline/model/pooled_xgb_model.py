from sklearn import metrics
from xgboost import XGBClassifier

from pipeline.panel import build_panel_data, split_by_date, get_x_y
from pipeline.config import SYMBOLS
import pandas as pd


def run_pooled_xgb():
    # Take the universal data using the functions from panel.py
    panel_data = build_panel_data(SYMBOLS)
    train_df, test_df = split_by_date(panel_data, 0.8)

    # Separate features (x) and target (y)
    exclude = ['symbol', 'target_5d', 'fwd_5d_return', 'close', 'high', 'open', 'low', 'timestamp', 'volume', 'vwap', 'SMA_10', 'SMA_30']
    feature_columns=[col for col in panel_data.columns if col not in exclude]
    target_columns=['target_5d']

    x_test, y_test = get_x_y(test_df, feature_columns, target_columns)
    x_train, y_train = get_x_y(train_df, feature_columns, target_columns)

    # Training the model
    model = XGBClassifier(
        n_estimators=100, 
        max_depth=4, 
        subsample=0.8,  
        learning_rate=0.1, 
    )
    model.fit(x_train, y_train)

    # Predict
    y_pred = model.predict(x_test)
    pred_prob = model.predict_proba(x_test)[:,1]

    # Evaluate
    acc = metrics.accuracy_score(y_test, y_pred)
    roauc = metrics.roc_auc_score(y_test, pred_prob)

    train_pred = model.predict(x_train)
    train_acc = metrics.accuracy_score(y_train, train_pred)
    print(f'\nTrain Accuracy: {train_acc}')
    print(f'Test Accuracy:  {acc}')
    print(f'Gap (train - test): {train_acc - acc}')

    return {
            "accuracy": acc,
            "ROC_AUC": roauc,
            "Gap (train - test)": train_acc - acc,
    }


if __name__ == '__main__':
    print(run_pooled_xgb())