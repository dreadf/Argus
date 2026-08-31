from sklearn import metrics
from xgboost import XGBClassifier

from pipeline.panel import build_panel_data, split_by_date, get_x_y, add_relative_target, add_market_features, add_news_features
from pipeline.config import SYMBOLS, MARKET_SYMBOL
import pandas as pd


def run_pooled_xgb():
    # Take the universal data using the functions from panel.py
    panel_data = build_panel_data(SYMBOLS)
    panel_data = add_market_features(panel_data, MARKET_SYMBOL)
    panel_data = add_news_features(panel_data)
    panel_data = add_relative_target(panel_data)
    train_df, test_df = split_by_date(panel_data, 0.8)

    # Separate features (x) and target (y)
    # Raw market columns (*_mkt) are excluded on purpose -- see the docstring on
    # add_market_features() in panel.py for why (they're near-constant per date,
    # and collinear with the residual_momentum_* columns derived from them).
    exclude = [
        'market_median_return', 'relative_target', 'symbol', 'target_5d', 'fwd_5d_return',
        'close', 'high', 'open', 'low', 'timestamp', 'volume', 'vwap', 'SMA_10', 'SMA_30',
        'daily_return_mkt', 'momentum_5_mkt', 'momentum_10_mkt', 'momentum_20_mkt',
        'volatility_5_mkt', 'volatility_10_mkt', 'RSI_mkt',
    ]
    feature_columns=[col for col in panel_data.columns if col not in exclude]
    # A plain string, not a single-element list -- df[target] with a list
    # returns a DataFrame instead of a Series (harmless with XGBClassifier
    # today, but inconsistent with every sibling script here, which all
    # index the target as a Series via a plain column-name string).
    target_columns='relative_target'

    x_test, y_test = get_x_y(test_df, feature_columns, target_columns)
    x_train, y_train = get_x_y(train_df, feature_columns, target_columns)

    # Training the model
    model = XGBClassifier(
        n_estimators=100, 
        max_depth=3, 
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