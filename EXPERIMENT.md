# Experiment Log — 5-Day AAPL Direction Prediction

Living log of every experiment run in this project, per the research question and philosophy in `ML_Experiment_Plan.md`: *"Can market-derived information from Alpaca data provide a robust out-of-sample signal for whether a stock will have a positive or negative return over the next 5 trading days?"*

Dataset: AAPL daily OHLCV, 2020-01-01 to 2026-08-14 (`pipeline/extract.py`), engineered via `pipeline/transform.py` into `output/data/engineered_data.csv` — 1,628 rows after feature warm-up/dropna. Chronological 80/20 split (no shuffling): 1,302 train rows / 326 test rows. Target class balance: ~55.7% positive / 44.3% negative (`target_5d`).

---

## Experiment 0 — Naive Baseline

**Script:** `pipeline/baseline_model.py`

**What we did:** Predicted the majority class (`target_5d`'s most common value in train) for every row in the test set — no model, no features.

**Why:** Establishes the "dumb but honest" floor. Any real model needs to clear this bar before it's worth trusting, per the plan's "does ML beat something embarrassingly simple?" question.

**Results:**
- Accuracy: **0.557**
- Recall: 1.00 (trivial — a constant predictor catches every actual positive by definition)
- F1: 0.72

**Interpretation:** Sets the bar any real model must clear. Recall of 1.00 here is not meaningful — it's a mechanical artifact of always guessing the same class, not evidence of skill.

---

## Experiment 1 — Logistic Regression

**Script:** `pipeline/logistic_model.py`

**What we did:** Trained Logistic Regression on engineered features (RSI, momentum_5/10/20, distance_SMA10/30, volatility_5/10, ATR_5/10, volume_spike, trade_count, daily_return), features scaled with `StandardScaler` (fit on train only). Evaluated accuracy, ROC-AUC, and inspected feature coefficients.

**Why:** Establishes whether a simple linear model finds a linear relationship between engineered features and 5-day direction.

**Results (first pass — before fixing a feature-leakage bug):**
- Accuracy: 0.571, ROC-AUC: 0.515
- Coefficient check flagged `SMA_30` at magnitude 1.18 — far above every other feature (next-highest ~0.77).

**Bug found and fixed:** Raw, non-stationary price-scale columns (`SMA_10`, `SMA_30`, `vwap`, `volume`) were never excluded from the feature set, despite already having proper scale-independent engineered counterparts (`distance_SMA10/30`, `volume_spike`). This caused multicollinearity (inflating/destabilizing coefficients) and let the model partly exploit price-level drift across the 2020–2026 span rather than a real recurring pattern.

**Results (after excluding raw price-scale columns):**
- Accuracy: **0.552**, ROC-AUC: **0.468** (below random)
- No single feature dominates the coefficient ranking anymore (top: `momentum_10` at 0.33).

**Corroborating check:** `raw_data_eda.ipynb` — correlation of every individual feature against `target_5d` is below 0.09 in absolute value (strongest: `momentum_10` at 0.084).

**Interpretation:** Three independent linear diagnostics (Logistic Regression accuracy/AUC, its coefficients, and raw feature-target correlation) agree: this feature set shows **no meaningful *linear* relationship** with 5-day AAPL direction. The earlier, better-looking AUC (0.515) was an artifact of the leakage bug, not real signal. This does not rule out nonlinear relationships — hence Experiment 2.

---

## Experiment 2 — XGBoost

**Script:** `pipeline/xgb_model.py`

**What we did:** Same feature set and chronological split as Experiment 1 (no scaling needed — tree-based). Trained `XGBClassifier`, evaluated accuracy/ROC-AUC, inspected `feature_importances_`, and checked train-vs-test accuracy for overfitting.

**Why:** Logistic Regression can only detect linear, marginal relationships. XGBoost can capture nonlinear interactions (e.g. "momentum matters only when volatility is low") that correlation/linear coefficients are blind to — this experiment asks whether such interactions exist.

**Results — first pass (`n_estimators=100`, `max_depth=3`):**
- Test accuracy: 0.528, ROC-AUC: 0.529 (both near baseline/random)
- Train accuracy: **0.793** vs test accuracy 0.528 → **26.5-point gap**, a clear overfitting signature. Feature importances were spread fairly flat (0.05–0.11 range), no standout feature.

**Results — after reducing `n_estimators` to 50 (regularization attempt):**
- Test accuracy: **0.549**, ROC-AUC: **0.533**
- Train accuracy: 0.737 vs test 0.549 → gap narrowed to **18.8 points**, still overfitting, and test performance still barely above baseline/random.

**Further regularization tuning** (`max_depth=2`, `subsample=0.8`, `reg_lambda=1.0`, `reg_alpha=0.1`): narrowed the train/test gap to ~0.14–0.15 and lifted single-split ROC-AUC to as high as **0.580** (best single-split result of the project). A `colsample_bytree` typo (`colsample=` instead of `colsample_bytree=`) was found and fixed along the way — it had been silently ignored by XGBoost (with a console warning) and wasn't actually regularizing anything; once properly active it did not improve results, and was reverted.

**Interpretation (single-split, superseded — see Experiment 2b below):** Best single 80/20 split configuration reached ROC-AUC 0.580, train/test gap ~0.14 — looked like a genuine, if modest, nonlinear edge. Flagged as needing a stability check across multiple time windows before trusting it, since a single split can look good by chance.

---

## Experiment 2b — Stability Check (TimeSeriesSplit Cross-Validation)

**Script:** `pipeline/xgb_stability.py`

**What we did:** Replaced the single 80/20 split with `sklearn.model_selection.TimeSeriesSplit(n_splits=5)`, re-fitting a fresh `XGBClassifier` (same tuned hyperparameters as Experiment 2's best config) on each of 5 chronological folds, to check whether the single-split 0.580 AUC result was a stable, repeatable pattern or a lucky window.

**Why:** A single train/test split can look good purely by chance. Walk-forward-style validation across multiple time windows is the plan's prescribed way to distinguish a real, robust signal from noise.

**Results:**

| Fold | Train rows | Accuracy | ROC-AUC |
|---|---|---|---|
| 0 | 273 | 0.528 | 0.497 |
| 1 | 544 | 0.432 | 0.431 |
| 2 | 815 | 0.542 | 0.487 |
| 3 | 1086 | 0.491 | 0.470 |
| 4 | 1357 | 0.554 | **0.576** |

- ROC-AUC — Mean: **0.492**, Std: 0.053
- Accuracy — Mean: **0.509**, Std: 0.049

**Interpretation:** Fold 4 (the largest training window, ending closest to the original single-split boundary) reproduces the earlier 0.580 AUC result almost exactly. Every earlier fold sits at or below 0.5, one (fold 1) as low as 0.431. Mean AUC across folds is **below random**. This strongly suggests the earlier single-split 0.580 result was a favorable, non-representative slice of time rather than a stable, repeatable pattern — the "small std" does not indicate a good, stable signal; it indicates *consistently weak/random* performance interrupted by one lucky fold. **XGBoost does not show a robust out-of-sample edge over the naive baseline across multiple time windows.**

---

## Experiment 3 — Feature Ablation

**Script:** `pipeline/xgb_group_feature.py`

**What we did:** Split the existing feature set into four named groups matching the plan's categories — **A** (price/return: `daily_return`, `momentum_5/10/20`), **B** (trend/technical: `RSI`, `distance_SMA10/30`), **C** (volatility: `volatility_5/10`, `ATR_5/10`), **D** (volume: `volume_spike`, `trade_count`) — then tested performance (same tuned `XGBClassifier`, same 5-fold `TimeSeriesSplit`) across three designs: (1) the plan's prescribed cumulative ladder (A, A+B, A+B+C, A+B+C+D), (2) each group in isolation, and (3) all 15 possible non-empty combinations via `itertools.combinations`.

**Why:** Experiment 2b showed no robust signal from the full combined feature set. Cumulative ablation alone can't distinguish "this group adds nothing" from "this group has signal that's being diluted by combination with others" — isolating and fully combining groups was needed to tell those apart.

**Results — cumulative ladder:**

| Group | AUC mean | Folds ≥ 0.5 |
|---|---|---|
| A | 0.541 | 4/5 |
| A+B | 0.509 | 3/5 |
| A+B+C | 0.479 | 1/5 |
| A+B+C+D | 0.492 | 1/5 |

**Results — isolated groups:**

| Group | AUC mean | Folds ≥ 0.5 |
|---|---|---|
| A | 0.541 | 4/5 |
| **B** | 0.519 | **5/5** (tightest std of any single group: 0.018) |
| C | 0.479 | 2/5 |
| D | 0.518 | 2/5 |

**Results — full 15-combination sweep (top of table, ranked by folds ≥ 0.5 then AUC mean):**

| Combo | AUC mean | AUC std | Folds ≥ 0.5 |
|---|---|---|---|
| **A+D** | **0.544** | 0.029 | **5/5** |
| **B** | 0.519 | 0.018 | **5/5** |
| A | 0.541 | 0.049 | 4/5 |
| B+D | 0.532 | 0.050 | 4/5 |
| A+B+D | 0.526 | 0.033 | 3/5 |
| A+B | 0.509 | 0.039 | 3/5 |
| *(every combination containing C)* | 0.48–0.50 | high | ≤2/5 |
| A+B+C+D (full set) | 0.492 | 0.053 | 1/5 |

**Overfitting check (train − test accuracy gap) on the 4/5 and 5/5 tier:**

| Group | Train acc | Test acc | Gap |
|---|---|---|---|
| A | 0.689 | 0.554 | 0.134 |
| B | 0.700 | 0.530 | 0.170 |
| A+D | 0.723 | 0.545 | 0.178 |
| B+D | 0.709 | 0.549 | 0.160 |

All four sit in a similar, already-known overfitting range — no red flags disqualifying any of them, and "best AUC" (`A+D`) is not the same candidate as "least overfitting" (`A`).

**Interpretation:** **Every one of the 8 combinations containing Group C lands in the bottom half of the ranking** (≤2/5 folds ≥ 0.5) — a pattern repeated across many different pairings, not a single unlucky result, making it fairly trustworthy that volatility/ATR features consistently hurt this model on this data. **`A+D` (price/return + volume) and `B` alone (trend/technical) are the two standout performers** — both hit 5/5 folds ≥ 0.5, both with low variance. This revises the earlier "no exploitable signal anywhere" conclusion: there does appear to be a small, consistent, real edge in `A+D` and in `B`, previously masked by combining everything together (especially by including Group C). **Caveat:** 15 combinations were tested in this sweep — some separation is expected from multiple testing alone; the C-hurts-everywhere pattern's repetition across 8 combos is the main reason to trust this over cherry-picking a single winner.

---

## Experiment 4 — Multi-Stock Generalization Check

**Scripts:** full pipeline refactored into reusable functions and orchestrated by `pipeline/run_all.py` — `fetch_and_save()` (`extract.py`), `engineer_features()` (`transform.py`), and `run_baseline()`/`run_logistic_model()`/`run_xgb_model()`/`run_xgb_stability()`/`run_ablation()` (`pipeline/model/`), all reading symbols/date range from a single `pipeline/config.py`.

**What we did:** Re-ran the exact same 15-combination ablation sweep (Experiment 3) independently across 5 symbols from different sectors — `AAPL`, `MSFT` (tech), `JPM` (financials), `KO` (consumer staples), `XOM` (energy) — to test whether the `A+D`/`B` edge found on AAPL alone was a genuine market-wide pattern or an AAPL-specific idiosyncrasy.

**Why:** Every prior experiment (0 through 3) was run on AAPL only. A pattern found on one symbol could easily be idiosyncratic to that stock rather than reflecting anything general about price/volume technical features — the plan's own robustness checks flag exactly this risk.

**Results — how many of the 5 stocks each combination hits ≥4/5 folds ≥ 0.5 on:**

| Combo | Stocks hitting ≥4/5 folds | Avg AUC across stocks |
|---|---|---|
| **B+D** | **2 / 5** (KO, XOM) | 0.496 |
| A+D | 1 / 5 (AAPL only) | 0.489 |
| A, B, C, A+B+D, A+B+C, A+B | 1 / 5 each | 0.485–0.494 |
| D, C+D, A+C+D, A+C, B+C, B+C+D, A+B+C+D | 0 / 5 | 0.483–0.496 |

**Per-symbol detail for the two previously-leading combos:**

| Symbol | A+D (folds ≥0.5) | B+D (folds ≥0.5) |
|---|---|---|
| AAPL | 5/5 | 3/5 |
| MSFT | 1/5 | 2/5 |
| JPM | 1/5 | 2/5 |
| KO | 2/5 | 4/5 |
| XOM | 2/5 | 4/5 |

**Interpretation:** **`A+D`'s standout 5/5 result does not replicate on any other symbol** — it drops to 1-2/5 on MSFT, JPM, KO, and XOM, meaning the earlier "best finding of the project" was very likely specific to AAPL over this particular date range, not a general market pattern. **`B+D` is the closest thing to a cross-stock pattern found so far** (consistent ≥4/5 on KO and XOM specifically, both more defensive/traditional sectors than AAPL/MSFT/JPM), but even it only holds up on 2 of the 5 stocks tested — nowhere near the robust, general edge that would be needed to trust it broadly. **No combination generalizes convincingly across sectors.** This is a legitimate, if sobering, answer to the project's core research question: single-symbol price/volume technical ablation results should not be assumed to generalize, and the honest finding at this stage is that no tested feature combination shows a robust, cross-stock predictive edge for 5-day direction.

---

## Experiment 5 — Pooled Panel Model Prototype

**Scripts:** `pipeline/panel.py` (`build_panel_data()`, `split_by_date()`, `get_x_y()`) and `pipeline/model/pooled_xgb_model.py` (`run_pooled_xgb()`).

**Why (research-driven):** `RESEARCH_pooling_vs_individual.md` surveyed the literature on individual vs. pooled vs. ensemble modeling for exactly this kind of overfitting problem. Gu-Kelly-Xiu (2020) and Sirignano-Cont (2019) both argue pooling many stocks into one training set gives a model a much richer combined scenario space, directly targeting the overfitting that plagued Experiments 2–3 (train/test gaps of 0.13–0.26). The doc's own staged recommendation was to prototype plain pooling first, before adding any stock/sector-level structure.

**What we did:** Expanded `SYMBOLS` in `config.py` from 5 to **40 stocks across 11 sectors** (Technology, Communication Services, Consumer Discretionary, Consumer Staples, Financials, Healthcare, Energy, Industrials, Materials, Utilities, Real Estate) for diversity. Built a stacked panel (`build_panel_data`) — every symbol's already-engineered feature rows concatenated into one long DataFrame, each row tagged with its `symbol`. Split the *whole panel* by a single date cutoff (`split_by_date`, 80% of unique trading days as train, 20% as test) — critically, one shared cutoff date across all 40 stocks at once, not a per-symbol chronological split. Trained one `XGBClassifier` (`n_estimators=100, max_depth=4, subsample=0.8, learning_rate=0.1`) on the pooled train set; `symbol` itself was excluded from the feature set for this first pass (plain, "structure-free" pooling, matching the literature's baseline case).

**Results:**

| | Per-stock XGBoost (avg of 5, Experiment 4) | Pooled XGBoost (40 stocks) |
|---|---|---|
| Test Accuracy | 0.539 (range 0.520–0.557) | **0.527** |
| Test ROC-AUC | 0.506 (range 0.408–0.562) | **0.498** |
| Train − Test Gap | 0.13–0.26 (severe overfitting) | **0.068** |

**Interpretation:** Accuracy and AUC are essentially unchanged from the per-stock average — both still sit at "coin flip" level. But the **train/test gap shrank by roughly 2–4x**, exactly matching Sirignano-Cont's prediction that pooling reduces overfitting by giving the model far more effective training data. This is a genuine, measured confirmation of that mechanism in our own data, not just a claim from the paper. Separately, 52.7% accuracy lines up almost exactly with **Döbelt (2026)'s own "plain pooled, structure-free" LSTM baseline (52.2%)** — independent confirmation that this ~50–55% ceiling is a real, repeated finding across the literature (Gu-Kelly-Xiu, Sirignano-Cont, Döbelt, Pesaran et al. all converge here), not a bug or a weak implementation. **Plain pooling fixes the overfitting problem but does not, by itself, push accuracy meaningfully past chance** — which is exactly why Döbelt needed to add sector embeddings (52.2% → 52.5%) and why the ensemble/hierarchical papers (Ghosn-Bengio, Feng-He, Pesaran et al.) go further than plain pooling. Next step, per the research doc's own ordering: test whether adding stock-level structure (e.g. bringing `symbol` back in as an encoded feature) recovers any of that signal.

---

## Experiment 6 — Panel Diagnostics: Why the Pooled Model Sits at Chance

**Status:** exploratory diagnostic pass, run as throwaway analysis scripts against the existing panel — **not yet codified into `pipeline/`**. The numbers below come from a single 80/20 date split (with a purge, see below) and should be read as directional evidence, not settled results. Codifying these as repeatable pipeline stages is a next step.

**Why:** Experiment 5 established that plain pooling fixes overfitting but leaves AUC at 0.498. "Accuracy is at chance" is a symptom, not a diagnosis. Before adding more model structure (sector embeddings, hierarchical priors), it is worth asking a cheaper question: *is there any signal in these features at all, and if the model is failing, how exactly is it failing?* Adding structure to a model that has no signal to work with only spends effort.

### 6a — Variant sweep on the pooled panel

Six variants of the pooled model, all on 40 symbols with a purged split (see 6d):

| Variant | Test ROC-AUC |
|---|---|
| A. as-is (absolute target, raw `trade_count`, no purge) | 0.4950 |
| B. as-is + 10-day purge at the split boundary | 0.4996 |
| C. drop `trade_count` | 0.4917 |
| D. cross-sectional **relative** target | 0.4973 |
| E. cross-sectionally ranked features + relative target | 0.4985 |
| F. cross-sectionally ranked features + absolute target | 0.4970 |

Every variant lands on 0.50. None of the standard panel-modeling fixes moves the needle on AUC.

### 6b — The model is not random, it is inverted

Built a daily long/short book from variant E — each day, long the top-quintile-scored stocks, short the bottom quintile, hold 5 days:

- Mean 5-day spread: **−0.457%**
- Hit rate: **43.6%**
- t-statistic: **−3.12** (n = 326 days)

A t-stat of −3.12 is not noise. The model is *reliably wrong* out of sample. That is a different and more informative failure than "no signal."

### 6c — Cause: the momentum relationship inverts between train and test

Measured the **cross-sectional Information Coefficient (IC)** of each feature — the per-day Spearman rank correlation between the feature and forward 5-day *relative* return, averaged across days. t-stats computed on every 5th date only, so the 5-day overlapping labels don't inflate significance.

| Feature | IC, train (2020-02 → 2025-04) | IC, test (2025-05 → 2026-08) |
|---|---|---|
| `momentum_10` | **+0.0095** | **−0.0422** |
| `momentum_5` | **+0.0112** | **−0.0290** |
| `distance_SMA10` | **+0.0077** | **−0.0339** |
| `RSI` | +0.0185 | −0.0126 |
| `volatility_5` | +0.0120 | +0.0531 |

Every momentum-family feature **flips sign**. The model learned "recent winners keep winning" from the training period and deployed it into a mean-reverting window — which is exactly the −3.12 t-stat in 6b. Momentum inverting across regimes is normal behaviour in equity markets, not an anomaly.

Checked whether volatility's positive sign is a stable lead. Yearly mean IC for `volatility_5`: `+0.056, −0.011, −0.033, +0.048, +0.015, +0.046, +0.030` (2020→2026). It flips in 2021–22, so it is not stable either. `RSI` is the most consistently-signed feature in the dataset (positive in 6 of 7 years) but at IC ≈ 0.02 with t ≈ 1.5 — below significance, and one of 39 features/period-combinations tested.

### 6d — Three structural problems with the experiment design

**1. The label is mostly market beta.** Measured the correlation between each stock's forward 5-day return and the equal-weight 40-stock market's forward 5-day return: **mean 0.540** (range 0.229–0.751). On **22.5%** of days, ≥80% of the 40 stocks move the same direction. So `target_5d` is largely asking *"will the market go up next week?"* — a question that single-stock technical features cannot answer. A market-timing failure has been getting attributed to a stock-selection feature set. **The cross-sectional relative target (variant D/E) is the correct framing regardless of anything else, because it removes this component.**

**2. Effective sample size is far smaller than the row count.** The panel is 65,400 rows, but: 40 symbols correlated at 0.54 with a common factor, and 5-day overlapping labels (consecutive rows share 4 of 5 days of their target window). Effective independent observations ≈ 1,635 dates ÷ 5 ≈ **327**, times a handful of independent cross-sectional dimensions — order **~1,000, not 65,000**. Any t-stat computed on raw rows is inflated by roughly √5 from label overlap alone. This is why Sirignano-Cont's "one year of pooled data = 500 years of single-stock data" does not transfer here: that holds for order-book data where cross-sectional correlation is low, not for daily returns of 40 mega-caps.

**3. The entire out-of-sample verdict rests on one macro regime.** Test period is a single continuous window, 2025-04-29 → 2026-08-17. Whatever momentum happened to do in those 16 months *is* the result. A single walk-forward split cannot distinguish "no signal" from "signal, wrong regime" — and 6c shows it is the second one.

### 6e — Bugs found

- **`pipeline/panel.py`, `split_by_date()`** — `.loc[:cutoff]` and `.loc[cutoff:]` both include the cutoff date, so one trading day appears in *both* train and test (confirmed: 1 overlapping date). Small, but it is leakage.
- **No purge/embargo anywhere.** Because the label looks 5 days forward, the last 5 training rows have targets that resolve *inside* the test period. Every split in this project (`TimeSeriesSplit` in Experiments 2b/3/4 included) has this. Adding a 10-day purge moved pooled AUC 0.4950 → 0.4996 — small here, but it is the difference between an honest and a slightly optimistic number, and it matters more as signal gets stronger.
- **`trade_count` is a symbol fingerprint in the pooled model.** It is fed raw and unnormalized, and its median ranges from 33,372 (LIN) to 1,046,594 (TSLA). The model can identify the ticker from it and memorize per-symbol base rates. Dropping it *lowered* AUC (0.4950 → 0.4917), which suggests it was contributing identity information rather than signal.

### 6g — First test of the regime hypothesis: negative

The obvious follow-up to 6c is: *if momentum's sign depends on the market regime, can we detect the regime in advance and switch signs?* Tested directly, using only backward-looking information available at decision time.

Built two candidate regime states from the panel itself (equal-weight average of all 40 stocks' `daily_return`):
- `mkt_vol20` — 20-day rolling std of market return (market calm vs. turbulent)
- `mkt_tren20` — 20-day rolling sum of market return (market rising vs. falling)

Split all days into terciles on each, then measured `momentum_10`'s IC separately inside each tercile:

| Regime variable | Tercile | mean IC | t-stat (non-overlapping) |
|---|---|---|---|
| market volatility | LOW | +0.0083 | 0.59 |
| | MID | −0.0205 | −0.59 |
| | HIGH | −0.0008 | −0.09 |
| market trend | LOW (falling) | −0.0311 | −1.28 |
| | MID | +0.0117 | 0.66 |
| | HIGH (rising) | +0.0065 | −0.69 |

**No tercile reaches significance** (all |t| < 1.3), and the ordering is not monotonic — under the volatility split the middle bucket is the most negative, which is not what a real regime effect looks like. **The simplest version of the regime hypothesis does not hold in this data.**

This does not kill the idea outright — 20-day realized vol/trend are crude regime proxies, and the tercile split throws away information — but it does mean the momentum sign-flip in 6c is *not* cheaply exploitable, and the regime direction should be demoted from "most promising next step" to "tested once, negative, needs a much better regime definition to be worth revisiting."

### 6f — Interpretation

The pooled model's 0.498 AUC is not "the features are useless." It is three things stacked: (a) the target is 54% market beta that these features cannot explain, (b) the momentum signal that does exist inverted between train and test, and (c) the evaluation has ~1,000 effective observations, not 65,000, so nothing at this effect size could have been proven either way.

This reframes the "next steps" from Experiment 5. Adding sector embeddings or hierarchical structure to a model whose *label* is dominated by an unexplainable market factor is optimizing the wrong stage. The evaluation framing has to be fixed first.

---

## Experiment 7 — Relative Target Integrated into the Pooled Pipeline

**Scripts:** `pipeline/panel.py` (`add_relative_target()`, new) and `pipeline/model/pooled_xgb_model.py` (updated to train on `relative_target` instead of `target_5d`).

**What we did:** Codified the cross-sectional relative target that Experiment 6 recommended as a diagnostic fix. `add_relative_target(panel_df)` computes, per date, the cross-sectional median of `fwd_5d_return` across all 40 symbols (`panel_df.groupby(panel_df.index)['fwd_5d_return'].transform('median')`) and labels each row `1` if its `fwd_5d_return` beats that day's median, `0` otherwise — so `relative_target` is 50/50 by construction, every day. Wired into `run_pooled_xgb()`: called right after `build_panel_data()` and before `split_by_date()`, with `relative_target` and `market_median_return` both added to the feature-exclusion list (the latter is derived from `fwd_5d_return`, so leaving it in as a feature would be leakage). Also fixed, in the same session, the `split_by_date()` boundary-overlap bug flagged in Experiment 6e — the cutoff now gets a 7-day gap (`cutoff_date - Timedelta(7d)` for train end, `cutoff_date + Timedelta(1d)` for test start) instead of both sides including the cutoff date.

**Why:** Experiment 6d measured that ~54% of `target_5d`'s variance is common market movement, unexplainable by single-stock technicals. The relative target removes that component from the label, isolating the question "can these features rank stocks against each other" from "can these features predict market direction" (which they were never expected to answer).

**Results:**

| | Experiment 5 (`target_5d`, no purge) | Experiment 7 (`relative_target`, 7-day purge) |
|---|---|---|
| Test Accuracy | 0.527 | 0.500 (baseline is also 0.500 — relative target is 50/50 by construction, so this number alone is uninformative) |
| Test ROC-AUC | 0.498 | **0.497** |
| Train − Test Gap | 0.068 | 0.099 |

**Interpretation:** AUC is unchanged within noise (0.498 → 0.497) — the relative target did **not** recover any signal. This is not a new finding; it corroborates Experiment 6a's variant D (relative target alone, AUC 0.4973) and variant E (relative target + ranked features, AUC 0.4985), which already showed this. Combined with 6c's diagnosis (the momentum features' cross-sectional IC inverts sign between train and test, +0.0095 → −0.0422), the picture is consistent: removing market beta from the label was necessary but not sufficient, because the remaining signal problem is in the *features'* stability across this test period, not in what the label was measuring. Accuracy alone (0.500) is not meaningful here and must not be compared directly to Experiment 5's 0.527 — the two targets have different baselines (54.4% vs 50.0%), so only AUC is comparable across them.

**Against the Phase 3 gating criteria** (`Project_Context_and_Plan_Updated.md`): AUC 0.497 does not clear "IC positive and stable across multiple walk-forward windows." Per that gate, the honest conclusion is **do not proceed to live/paper execution** with this feature set — this is a valid research result, not a blocked task.

---

## Experiment 8 — Market-Relative Features (Residual Momentum & Rolling Beta)

**Scripts:** `pipeline/panel.py` (`add_market_features()`, new) and `pipeline/model/pooled_xgb_model.py` (wired in between `build_panel_data()` and `add_relative_target()`). `config.py` gained `MARKET_SYMBOL = "SPY"`, kept separate from `SYMBOLS` so SPY never becomes a tradeable candidate. `raw_SPY.csv`/`engineered_SPY.csv` generated via the existing `fetch_and_save()`/`engineer_features()` functions, unmodified.

**Research check (done before implementing, per standing project rule):** Blitz, Huij & Martens (2011, *Journal of Empirical Finance*), "Residual Momentum" — sorting stocks by momentum net of the market component produces a materially more stable signal than sorting by raw momentum. Blitz, Hanauer & Vidojevic (2017), "The Idiosyncratic Momentum Anomaly" — idiosyncratic momentum is not explained by market/size/value/profitability/investment factors and subsumes total-return momentum in several tests (not vice versa). Gu, Kelly & Xiu (2020) — already cited in `RESEARCH_pooling_vs_individual.md` — include market beta among their 94 standard cross-sectional characteristics. This directly targets Experiment 6c's diagnosis (`momentum_10` IC flipped +0.0095 → −0.0422 between train and test): residual/idiosyncratic momentum is the literature's specific answer to a momentum signal that inverts against the market factor.

**What we did:** `add_market_features(panel_df, market_symbol)` joins SPY's engineered columns (`daily_return`, `momentum_5/10/20`, `volatility_5/10`, `RSI`, suffixed `_mkt`) onto every stock's row for the matching date (`DataFrame.join` on the shared `timestamp` index — one market value broadcast to all 40 symbols per date, not a new row). From that, two feature families are derived:
- **Residual momentum** (`residual_momentum_5/10/20`) = `momentum_N − momentum_N_mkt` — the part of a stock's move not explained by the market that day.
- **Rolling beta** (`beta_60`) = 60-day rolling `cov(daily_return, daily_return_mkt) / var(daily_return_mkt)`, computed per symbol.

Raw market columns (`*_mkt`) were deliberately **excluded** from the feature set: on any given date they take one value shared by all 40 symbols, so for a cross-sectional/relative target they carry ~zero information on their own, and keeping them alongside the residual features (which are a linear function of them) would reintroduce the multicollinearity Experiment 1 already found and removed (raw `SMA_10`/`SMA_30` vs `distance_SMA`).

**Sanity checks:** row count dropped exactly 65,400 → 63,040 (2,360 = 59 warm-up rows × 40 symbols, matching the 60-day beta window — no unexplained loss). `beta_60` mean 0.849, std 0.618, range roughly [−4.3, 3.9] — centered near 1 as expected for a basket of large caps. `residual_momentum_10` std (0.0648) is modestly lower than raw `momentum_10` std (0.0704), directionally consistent with the "more stable" claim in Blitz et al., though the difference is small in this sample.

**Results:**

| | Experiment 7 (`relative_target`, no market features) | Experiment 8 (`relative_target` + market features) |
|---|---|---|
| Test Accuracy | 0.500 (baseline 0.500) | 0.504 (baseline 0.500) |
| Test ROC-AUC | 0.497 | **0.502** |
| Train − Test Gap | 0.099 | 0.112 |
| Feature count | 13 | 17 |

**Feature importance (Experiment 8 model):** fairly flat across all 17 features (0.050–0.066 range, no standout). Notably, `residual_momentum_20` is the single most important feature (0.066), and `beta_60` (0.061) sits mid-pack alongside established features like `RSI` and `distance_SMA10` — both new feature families are being used by the model, not ignored.

**Interpretation:** AUC moved from 0.497 to 0.502 — technically crossed back above 0.50, but the move is small enough (0.005) to be well within single-split noise given the effective sample size problem established in Experiment 6d (~1,000 independent observations, not 63,040 rows). This is **not** strong enough evidence on its own to call it a recovered edge. It is, however, a directionally consistent result: the literature-motivated residual momentum feature is the top-ranked feature by importance, which is more informative than the AUC delta alone. Per the Phase 3 gating criteria (`Project_Context_and_Plan_Updated.md`), this result still does not clear "IC positive and stable across multiple walk-forward windows" — one split, one small AUC move, is not sufficient. The honest read: market-relative features are a legitimate, literature-backed idea that measurably changed what the model leans on (see feature importances), but a single-split AUC of 0.502 is not yet a validated edge.

**Next step implied:** re-run this under `TimeSeriesSplit`/multiple walk-forward windows (as Experiment 2b did for the original single-symbol XGBoost result) before drawing any conclusion about whether this 0.502 is real or a favorable slice of time — the project has been burned by exactly this pattern once already (Experiment 2's single-split 0.580 AUC did not survive Experiment 2b's multi-window check).

---

## Experiment 9 — News Count Feature

**Scripts:** `pipeline/news_extract.py` (new — fetches raw news articles from Alpaca's News API) and `pipeline/panel.py` (`add_news_features()`, new), wired into `pooled_xgb_model.py` between `add_market_features()` and `add_relative_target()`.

**Research check (done before implementing, per standing project rule):** literature on news volume as a market signal finds it is a stronger predictor of *volatility/tail risk* than of *direction* — "abnormally high news coverage predicts tail risk on both sides," and retail attention to news is linked to volatility increases up to 4 days after an event. Separately, "News versus Sentiment" (Financial Analysts Journal, ~900k articles) found daily-granularity news predicts returns only 1-2 days out, while weekly-aggregated news predicts up to a quarter — closer to this project's 5-day horizon. Expectation set going in: `news_count` more plausible as a risk/regime signal than a directional one.

**What we did:** `fetch_news()` in `news_extract.py` pulls articles per symbol via Alpaca's `NewsClient`, chunked into quarterly date ranges (discovered mid-build: `get_news()` paginates internally and `limit` caps the *total* articles returned per call at ~10,000, not "per page" — a single call for one heavily-covered symbol across the full 2020-2026 range would silently truncate). Retries 3x with backoff per chunk, checkpoints to CSV per symbol. `add_news_features()` in `panel.py` explodes each article's `symbols` list into one row per mentioned symbol, aggregates to a daily `news_count` per (symbol, date) via `groupby(...).size()`, and merges onto the panel on `['symbol', 'timestamp']` (both keys, unlike the market-feature join which only needs date) with `fillna(0)` for no-news days.

**Bug found and fixed:** because articles are fetched one symbol at a time, an article mentioning multiple tracked symbols (e.g. an article about both `CAT` and `PEP`) gets pulled down once per symbol it's relevant to and stored as duplicate rows. **43% of the raw 223,597 fetched rows (96,286) were duplicates** of this kind. Left unfixed, `explode()` would double- or multi-count `news_count` specifically for symbols that frequently co-occur in the same articles — a systematic bias, not random noise. Fixed with `drop_duplicates(subset=['created_at', 'headline'])` *before* exploding (deduping after exploding doesn't work, since the `symbol` column differs per exploded row by design). Note: dedup key is `created_at`+`headline`, not Alpaca's article `id` — `fetch_news()` doesn't currently save `id`. Practically safe (two distinct articles sharing an identical to-the-second timestamp and headline is effectively impossible), but worth fixing at the source if `news_extract.py` is ever re-run.

**Coverage is extremely uneven across symbols** (raw article counts, full 2020-2026 period): `TSLA` 32,234, `AAPL` 23,244, `NVDA` 18,878 vs. `LIN` 592, `AMT` 696, `DUK` 692 — a ~50x spread between the most- and least-covered names, all mega-caps. `news_count` on the full panel: mean 3.23, median 1, max 159, with 25th percentile at 0 (a quarter of all stock-days have zero news).

**Results:**

| | Experiment 8 (17 features, no news) | Experiment 9 (18 features, +`news_count`) |
|---|---|---|
| Test Accuracy | 0.5044 (baseline 0.5000) | 0.5025 (baseline 0.5000) |
| Test ROC-AUC | 0.5018 | **0.5088** |
| Train − Test Gap | 0.1124 | 0.1128 |

**Feature importance (Experiment 9 model):** `news_count` is the **least important feature of all 18** (0.0427, tied for lowest with `daily_return`). Full ranking top-to-bottom: `distance_SMA30`, `momentum_20`, `ATR_10`, `residual_momentum_20`, `RSI`, `beta_60`, `volatility_5`, `volatility_10`, `residual_momentum_10`, `distance_SMA10`, `trade_count`, `residual_momentum_5`, `momentum_5`, `ATR_5`, `momentum_10`, `volume_spike`, `daily_return`, `news_count`.

**Interpretation:** AUC moved up again (0.5018 → 0.5088), continuing the small-step pattern from Experiment 8. But this time the evidence argues *against* attributing the move to the new feature: `news_count` is the single least-used feature in the model. A feature the model barely splits on cannot plausibly be responsible for a 0.007 AUC change — the more likely explanation is retraining noise (adding any feature, even a weak one, perturbs XGBoost's greedy split search slightly). This is a stronger version of the caution already applied in Experiment 8: there, the new features at least ranked among the more important ones; here, the new feature is demonstrably the least relevant one, which undercuts the AUC move even further. Per the Phase 3 gating criteria, this still does not clear "IC positive and stable across multiple walk-forward windows" — if anything, `news_count` in its current raw form (simple daily article count, no sentiment, no decay weighting, uneven coverage across symbols) looks like a feature with little to contribute to this model, consistent with the research check's expectation that news *count* alone is a weaker directional signal than a risk/volatility one.

**Next step implied:** per `TRADING_SYSTEM_PLAN.md` Layer 1 (not yet built), re-measure this and Experiment 8 using cross-sectional IC with non-overlapping t-stats instead of AUC — AUC deltas at this magnitude (0.005-0.007) are not distinguishable from noise given the ~1,000 effective-observation ceiling established in Experiment 6d, and IC/quintile-spread analytics were built specifically to answer this class of question more decisively.

---

## Running Synthesis (as of last entry)

The project has now been tested end-to-end across baseline → linear model → nonlinear model → single-symbol feature ablation → multi-symbol generalization check → pooled panel prototype → panel diagnostics, with consistent diagnostic rigor at each step (leakage checks, chronological splitting, overfitting checks, cross-validation, multiple-testing awareness).

**Honest conclusion at this stage:**

1. **AAPL-specific patterns (`A+D`) do not generalize.** `B+D` shows a partial, sector-limited pattern (KO/XOM) that is most likely multiple-testing noise.
2. **Plain pooling across 40 stocks solved the overfitting problem** (train/test gap 0.13–0.26 → 0.068), confirming Sirignano-Cont's mechanism in our own data. This is a real, positive result.
3. **Pooling did not produce signal**, and Experiment 6 explains why: the target is ~54% common market movement that single-stock technicals cannot explain, and the momentum relationship that does exist **inverted** between the train and test periods (IC +0.010 → −0.042), making the model reliably *wrong* rather than merely random (long/short t-stat −3.12).
4. **The evaluation, not just the model, is the bottleneck.** Effective sample size is ~1,000, not 65,000. The out-of-sample verdict rests on a single 16-month macro regime. No result at this effect size could have been proven either way with this design.

**Revised next steps, in priority order:**

1. **Change the evaluation metric from accuracy/AUC to cross-sectional IC and long/short quintile spread.** AUC on a 54%-base-rate pooled panel barely distinguishes a useful model from a useless one, and cannot say whether a strategy would make money. A *stable* IC of 0.03 is a real, tradeable factor — results at that magnitude have been getting discarded in this project because "0.52 AUC looks like nothing." It is not nothing, but it only counts if it is stable, which is what needs measuring.
2. **Fix the validation before running any new model.** Purged walk-forward with a 5-day embargo, and *multiple* sequential test windows instead of one. Fix the `split_by_date()` boundary-overlap bug and normalize or drop `trade_count`.
3. **Adopt the cross-sectional relative target as the default framing** (predict "does this stock beat the median stock this week", not "does this stock go up"), which removes the unexplainable market-beta component from the label.
4. **The regime hypothesis has been tested once and came back negative (6g).** Conditioning `momentum_10`'s IC on 20-day market volatility or 20-day market trend produced no significant bucket (all |t| < 1.3) and no monotonic ordering. Revisit only with a substantially better regime definition; do not treat it as the obvious next step.
5. **Group E (market context, e.g. SPY) remains untried**, but 6g lowers the expected value of using it purely as a regime-conditioning variable. Its value now rests on whether it adds information the 40-stock panel average does not already contain.
6. **Add stock/sector structure (Döbelt-style embeddings, hierarchical priors) only after steps 1–4.** Adding model structure on top of a mis-specified label and an under-powered evaluation optimizes the wrong stage.

**A standing caveat worth keeping in view:** 13 technical features derived from daily OHLCV on 40 US mega-caps is among the most heavily mined datasets in finance. The prior probability that a stable, exploitable edge is sitting there undiscovered is low. The negative result this project has produced is the *expected* result, and it is more valuable than an unreproducible 0.58 AUC. The genuinely open questions are the regime-conditioning one (step 4), or whether an orthogonal information source (fundamentals, cross-asset, news/sentiment) is needed rather than a better model on the same 13 columns.

---

## Glossary (for readers new to quant ML)

- **ROC-AUC** — probability the model scores a randomly chosen "up" day higher than a randomly chosen "down" day. 0.5 = coin flip, 1.0 = perfect. Below 0.5 means the model is *backwards*.
- **IC (Information Coefficient)** — the standard signal-strength metric in quant finance. Each day, rank all stocks by a feature, rank them by what actually happened next, and correlate the two rankings (Spearman). Then average over all days. IC ≈ 0.00 = no information; **IC ≈ 0.02–0.05, if stable, is a genuinely tradeable factor.** It is preferred over accuracy/AUC because it measures *ranking* skill, which is what a long/short portfolio actually needs.
- **Cross-sectional** — comparing stocks *against each other on the same day*, rather than comparing one stock against its own past. "Which of today's 40 stocks will do best" instead of "will AAPL go up."
- **Market beta / common factor** — the portion of a stock's move that is just the whole market moving. Measured here at ~54% of the 5-day return.
- **Purge / embargo** — deleting training rows whose forward-looking label overlaps the test period. Without it, the model has seen a sliver of the future.
- **Effective sample size** — how many *genuinely independent* observations there are. Overlapping labels and correlated stocks mean 65,400 rows can carry only ~1,000 observations' worth of evidence.
- **Long/short quintile spread** — buy the top 20% the model likes, short-sell the bottom 20%, measure the return difference. The most direct "would this have made money" test.
- **t-statistic** — how many standard errors a result sits from zero. |t| > 2 is the usual "probably not luck" bar. Negative t means reliably wrong.
- **Regime** — a persistent market environment (trending vs. mean-reverting, calm vs. volatile). Relationships that hold in one regime routinely invert in another.
