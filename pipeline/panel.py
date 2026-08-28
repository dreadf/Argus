import pandas as pd
from pipeline.config import SYMBOLS

# Build panel data in which combines all of the stocks into one DataFrame
def build_panel_data(symbols):
    panel_data = []
    for s in symbols:
        temporal = pd.read_csv(f'output/data/engineered_{s}.csv', index_col='timestamp', parse_dates=True)
        temporal['symbol'] = s
        panel_data.append(temporal)

    return (pd.concat(panel_data))

# Split the data into train and test
def split_by_date(panel_df, train_percentage):
    # Calculates the cutoff date
    unique_dates = sorted(panel_df.index.unique())
    cutoff_index = int(len(unique_dates) * train_percentage)
    cutoff_date = unique_dates[cutoff_index]

    cutoff_date = pd.Timestamp(cutoff_date)
    train = []
    test= []
    for s in panel_df['symbol'].unique():
        tmp_train = panel_df[panel_df['symbol'] == s].loc[:cutoff_date - pd.Timedelta(days=7)]
        tmp_test = panel_df[panel_df['symbol'] == s].loc[cutoff_date + pd.Timedelta(days=1):]
        train.append(tmp_train)
        test.append(tmp_test)

    train_df = pd.concat(train)
    test_df = pd.concat(test)

    return train_df, test_df

# Get the X and Y
def get_x_y (df, feature, target):
    x = df[feature]
    y = df[target]

    return x, y

# Calculates 

if __name__ == '__main__':
    panel = build_panel_data(SYMBOLS)
    print(split_by_date(panel, 0.8))
