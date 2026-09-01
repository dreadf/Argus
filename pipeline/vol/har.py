"""
The HAR (Heterogeneous Autoregressive, Corsi 2009) volatility forecaster --
the field benchmark this track's ML question (H5) is required to beat, per
the plan's pre-registered prior from the literature ("HARd to Beat", arXiv
2406.08041) that it likely won't on RV/VIX alone.

HAR regresses tomorrow's log realized vol on three lagged averages
(daily, weekly, monthly) -- the "heterogeneous" part being that different
market participants are assumed to look back over different horizons.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.linear_model import LinearRegression


def build_shar_features(log_rv: pd.Series, log_rv_pos: pd.Series, log_rv_neg: pd.Series) -> pd.DataFrame:
    """Patton-Sheppard SHAR specification: the daily term is split into
    positive and negative realized semivariance, weekly/monthly terms stay
    as plain total RV (their finding was that the sign split matters most
    at the shortest horizon -- yesterday's down-moves predict tomorrow's
    vol much more than yesterday's up-moves do, an effect that averages out
    at weekly/monthly aggregation). All three series must already be
    log-transformed and aligned to the same index."""
    daily_pos = log_rv_pos.shift(1)
    daily_neg = log_rv_neg.shift(1)
    weekly = log_rv.shift(1).rolling(5).mean()
    monthly = log_rv.shift(1).rolling(22).mean()
    return pd.DataFrame({
        "shar_daily_pos": daily_pos,
        "shar_daily_neg": daily_neg,
        "shar_weekly": weekly,
        "shar_monthly": monthly,
    })


def build_har_features(log_rv: pd.Series) -> pd.DataFrame:
    """log_rv: daily log realized vol (or log realized variance -- HAR is
    typically specified in whichever scale the target uses, kept consistent
    throughout this module). Returns daily/weekly/monthly lagged averages,
    aligned so row t's features use only information available AT close of
    day t (never day t's own value, which the target needs to predict)."""
    daily = log_rv.shift(1)
    weekly = log_rv.shift(1).rolling(5).mean()
    monthly = log_rv.shift(1).rolling(22).mean()
    return pd.DataFrame({"har_daily": daily, "har_weekly": weekly, "har_monthly": monthly})


def build_har_x_features(log_rv: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """HAR-X: the plain HAR daily/weekly/monthly terms plus log(VIX) as an
    exogenous regressor -- the literature-confirmed extension (Kambouroudis
    2021 and others: adding VIX to HAR "notably improves forecast
    performance") never tested in this project before Experiment 18. VIX is
    lagged the same way as the HAR terms (shift(1), known at the close
    before the day being forecast, never leaked from the target day
    itself). `vix` must be aligned to log_rv's index (same dates), in raw
    level (not yet logged) -- log-transformed here to match the log scale
    of the other HAR features and RV's own right-skewed distribution."""
    har = build_har_features(log_rv)
    log_vix = np.log(vix).reindex(log_rv.index).shift(1)
    return har.assign(har_x_vix=log_vix)


def build_har_j_features(log_rv: pd.Series, jump_pct: pd.Series) -> pd.DataFrame:
    """HAR-J (Andersen, Bollerslev & Diebold 2007): the plain HAR daily/
    weekly/monthly terms plus the previous day's JUMP component (RV minus
    bipower variation, already computed and clipped at 0 in
    output/data/vol_spy_intraday_full.csv, Experiment 14's own data build,
    never fed into a model until this entry) as a fourth regressor.
    `jump_pct` must be in the same annualized-vol-pct units as `log_rv`'s
    source and aligned to log_rv's index. log1p-transformed (not log) since
    the jump component is legitimately 0 on most days -- plain log would be
    -inf. Lagged the same way as every other HAR feature (shift(1), known
    at the close before the day being forecast, never the target day's own
    value)."""
    har = build_har_features(log_rv)
    log_jump = np.log1p(jump_pct).reindex(log_rv.index).shift(1)
    return har.assign(har_j_jump=log_jump)


def naive_forecast(log_rv: pd.Series) -> pd.Series:
    """Dumbest possible baseline: tomorrow's vol = today's vol."""
    return log_rv.shift(1)


def ewma_forecast(log_rv: pd.Series, lam: float = 0.94) -> pd.Series:
    """RiskMetrics-style EWMA on the (non-log) variance scale, converted
    back to log for comparability with the HAR family. lam=0.94 is the
    standard RiskMetrics daily decay."""
    var = np.exp(log_rv) ** 2
    ewma_var = var.ewm(alpha=1 - lam, adjust=False).mean().shift(1)
    return np.log(np.sqrt(ewma_var))


class HARModel:
    """Fits by OLS (the classical Corsi specification) unless
    loss='qlike', in which case it fits by directly minimizing out-of-sample
    QLIKE via numerical optimization -- Test H3's hypothesis that this beats
    OLS on out-of-sample QLIKE, per the 2026 Journal of Forecasting result
    cited in the plan."""

    def __init__(self, loss: str = "ols"):
        self.loss = loss
        self.coef_ = None
        self.intercept_ = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "HARModel":
        valid = X.join(y.rename("y")).dropna()
        Xv, yv = valid[X.columns].to_numpy(), valid["y"].to_numpy()

        if self.loss == "ols":
            model = LinearRegression().fit(Xv, yv)
            self.coef_, self.intercept_ = model.coef_, model.intercept_
        elif self.loss == "qlike":
            ols = LinearRegression().fit(Xv, yv)
            x0 = np.concatenate([[ols.intercept_], ols.coef_])

            def qlike_objective(params):
                intercept, coef = params[0], params[1:]
                log_forecast = intercept + Xv @ coef
                forecast_var = np.exp(log_forecast) ** 2
                realized_var = np.exp(yv) ** 2
                ratio = realized_var / np.maximum(forecast_var, 1e-12)
                return np.mean(ratio - np.log(np.maximum(ratio, 1e-12)) - 1.0)

            result = minimize(qlike_objective, x0, method="Nelder-Mead",
                               options={"maxiter": 5000, "xatol": 1e-8, "fatol": 1e-10})
            self.intercept_, self.coef_ = result.x[0], result.x[1:]
        else:
            raise ValueError(f"unknown loss {self.loss!r}")
        return self

    def predict(self, X: pd.DataFrame) -> pd.Series:
        return pd.Series(self.intercept_ + X.to_numpy() @ self.coef_, index=X.index)
