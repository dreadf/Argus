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

## Experiment 10 — Re-measuring Experiments 8 & 9 with IC Instead of AUC

**Scripts:** `pipeline/signals/signals.py` (new — `random_signal`, `oracle_signal`, `planted_ic_signal`, `model_signal`) and `pipeline/signals/eval.py` (new — `daily_ic`, `ic_summary`), per `TRADING_SYSTEM_PLAN.md` Layers 0-1.

**Why:** Experiments 8 and 9 each produced a small AUC increase (0.4968 → 0.5018 → 0.5088) that was flagged both times as plausibly just noise, since AUC on a 50%-base-rate cross-sectional panel barely distinguishes a real edge from chance. `TRADING_SYSTEM_PLAN.md`'s own suggested first session was to build the IC measurement tooling and immediately re-measure Experiment 8 with it, since IC with non-overlapping t-stats is the more decisive metric for this exact question.

**What we did:** Before trusting any IC measurement, calibrated the tool itself against three known-answer signals (the "ruler" check): `random_signal` (pure noise, IC should read ~0), `oracle_signal` (deliberately leaky, scores the model with `fwd_5d_return` itself, IC should read ~1), and `planted_ic_signal(rho)` (blends the true rank with independent noise via `rho*true_z + sqrt(1-rho^2)*noise_z` on a normal-quantile transform, IC should read back ~rho). Results: random → 0.0123 (n=1635 days) / -0.0010 (separate seed), oracle → exactly 1.0000, planted at rho=0.03 → 0.0198 (same ballpark, attributed to sampling noise from the small 40-name cross-section — `random_signal`'s measured std_ic of 0.16 matches the textbook standard error of Spearman correlation for n=40, `1/sqrt(39)`, confirming the tool behaves as statistical theory predicts). All three passed. Then ran `model_signal` on the trained Experiment 8 and Experiment 9 models (test-set predictions only, matching their original chronological split) through `daily_ic` + `ic_summary`.

**Bug found and fixed en route:** `planted_ic_signal`'s per-day blending function initially returned a bare NumPy array from `groupby(...).apply(...)` instead of a `pd.Series` indexed like the group — the same class of bug as `beta_60` in `panel.py` (Experiment 8). Pandas silently collapsed the result to one row per group instead of one row per original row, producing all-NaN scores. Fixed by wrapping the blended array in `pd.Series(blended, index=group.index)`.

**Results:**

| | Experiment 8 (17 features, no news) | Experiment 9 (18 features, +news) |
|---|---|---|
| Test ROC-AUC (original metric) | 0.5018 | 0.5088 |
| **mean_ic** | **-0.0048** | **-0.0038** |
| std_ic | 0.1976 | 0.2040 |
| information_ratio | -0.0242 | -0.0186 |
| n_eff_non_overlap | 63 | 63 |
| **t_stat_non_overlap** | **-0.73** | **-1.13** |

**Interpretation:** Both models' IC is **indistinguishable from zero** (|t| well under the conventional 2.0 bar), and if anything trends slightly *negative*, not positive. This directly contradicts the impression the rising AUC sequence (0.4968 → 0.5018 → 0.5088) gave across Experiments 7-9 — there was no real improving trend; AUC was oscillating within noise the whole time, exactly as flagged (but not conclusively resolved) in each of those experiments' own interpretation sections. IC with a properly calibrated tool and non-overlapping t-stats settles the ambiguity AUC could not: **neither the market-relative features (Experiment 8) nor adding news_count (Experiment 9) produced a cross-sectionally useful ranking signal.**

**Against the Phase 3 gating criteria:** "IC positive and stable across several consecutive walk-forward windows" — not met, by a wide margin, for either model. This reaffirms the standing conclusion (do not proceed to execution) but now on much firmer statistical footing than the AUC-based reasoning could provide.

**Note on sample size:** `n_eff_non_overlap = 63` for both (the test period's ~315 trading days ÷ 5). `TRADING_SYSTEM_PLAN.md` already flagged that ~70 rebalances is a small sample for any Sharpe/t-stat; 63 is in the same range. A t-stat this far from significance (0.73-1.13 in magnitude, when 2.0 is the bar) is unlikely to flip sign with more data, but the honest caveat is that this test window alone cannot rule out a real, small, well-timed edge appearing in a different period -- consistent with Experiment 6d's broader finding that a single continuous test window is a real limitation of this project's validation design.

---

## Experiment 11 — Replaying the SPY put credit spread against real expired option prices

**Context:** the project pivoted from predicting SPY direction to selling put credit spreads (defined-risk insurance on a crash), per `OPTIONS_SYSTEM_PLAN.md`. The core empirical question: at each distance below spot and each spread width, did the market pay more than the risk actually delivered? An earlier version of this measurement existed only as a throwaway research script, not committed code, and every number from it was explicitly marked provisional. This entry is the reproduction in real, committed code.

**What we did:** for every Friday from 2024-02-01 (the start of Alpaca's expired-option-contract history) through 2026-08-21, computed the short and long put strikes for six distances (1% to 6% below that Friday's real SPY close, rounded away from spot to the nearest $1) crossed with four widths ($1, $2, $5, $10), fetched the real historical closing price of both legs on the entry date, and settled each spread at intrinsic value against the real SPY close on the following Friday (the plan's stated entry/settlement assumptions: bar-close entry, no slippage, intrinsic-value settlement). 128 candidate weeks, 2,921 of 3,072 (distance x width) cells had real trade prices for both legs; the rest were dropped as missing data (mostly deep-OTM contracts with zero volume on the entry day, not a defect). For each surviving cell, computed the win rate, the breakeven win rate implied by that cell's own average credit and width, and the cushion between them in standard errors, using `n` = the number of non-overlapping entry weeks (same discipline as `eval.py:38`'s `n_eff`).

**Results (2% and 3% distance shown; full sweep of all 24 cells in `output/data/evidence_gate_results.csv`):**

| Distance | Width | n | Win rate | Required (breakeven) | Cushion (SE) | Mean net P&L/contract | Clears 2 SE? |
|---|---|---|---|---|---|---|---|
| 2% | $1 | 127 | 89.0% | 87.8% | 0.44 | $0.031 | No |
| 2% | $5 | 127 | 89.0% | 90.1% | -0.39 | $0.227 | No |
| **3%** | **$1** | **126** | **97.6%** | **93.2%** | **3.28** | **$0.052** | **Yes** |
| **3%** | **$2** | **126** | **97.6%** | **93.6%** | **2.97** | **$0.096** | **Yes** |
| **3%** | **$5** | **126** | **97.6%** | **94.5%** | **2.28** | **$0.194** | **Yes** |
| 3% | $10 | 124 | 97.6% | 95.6% | 1.45 | $0.315 | No |
| 4% | $1 | 125 | 98.4% | 96.4% | 1.82 | $0.023 | No |
| 1% | any width | 127 | 78.0% | 78.6-85.5% | -0.17 to -2.04 | negative or near-zero | No |

**Interpretation:** three cells clear the 2-SE bar, all at **3% distance** -- widths $1, $2, and $5, with cushions of 3.28, 2.97, and 2.28 SE respectively. This is the same distance the provisional (unreproduced) numbers pointed to, and the measured cushion here (2.28-3.28 SE) is **stronger** than the provisional estimate of 1.8 SE that `OPTIONS_SYSTEM_PLAN.md` Part 2B computed by hand and explicitly flagged as below its own bar. At 1% and 2% distance, the market pays less than the risk actually realized -- consistent with the provisional finding, now on real data. Deeper distances (4%+) mostly fail the SE bar not because they lose money, but because so few losses occur in 120-some weeks that the win-rate estimate itself is too imprecise to clear 2 SE against its own (very high) breakeven rate -- a small-sample problem, not evidence the trade is bad.

**Multiple-testing caveat (Part 9's admission #1):** 24 (distance, width) cells were tested against the same ~126 non-overlapping weeks. Three clearing the bar out of 24 is not automatically robust to that; the $1 and $2 widths post the highest SE cushions but the lowest per-contract P&L, while $5 width has the most P&L but the thinnest cushion. No single cell is picked here -- `selector.py` (Build Step 7) is where that trade-off gets resolved, and it should not be resolved by picking whichever looks best in this table after the fact.

**What this replaces:** every "1.8 SE, below the bar" and "provisional" framing throughout `OPTIONS_SYSTEM_PLAN.md`, `PROGRESS.md`, and the draft submission copy in Part 0B is now superseded by this measurement. Those documents still describe the *reasoning* correctly (the evidence-gate method, the conservative breakeven formula); only the specific numbers were provisional, and this entry is what they were provisional pending.

**Known limitations, stated rather than hidden:** entry priced at bar close and settlement at intrinsic value are assumptions, not universal facts. Option history covers Feb 2024 onward, roughly one broad market regime, the same single-regime weakness flagged in Experiment 6d. 151 of 3,072 cells were dropped for missing data, concentrated in deep-OTM, thin-volume contracts; this does not affect the 3% distance result materially (124-126 of 128 candidate weeks had valid data at every width tested there). The retry logic that produces those missing-data rows was audited and fixed after an initial bug-hunt round found it could have silently mislabeled a real API failure as missing data; the backtest was re-run afterward and every number in the table above (missing-data count, win rates, cushions) is unchanged, confirming the 151 dropped cells really are thin liquidity, not a masked outage.

**Addendum -- the slippage sweep, run:** the cost sweep flagged above as "not-yet-run" has since been added (`spread_backtest.run_backtest`'s `slippage_per_share` parameter, a flat per-share haircut on every trade). The flagship cushions above assume **zero** slippage; here is how they move under a realistic cost:

| Haircut/share | $1 width cushion (SE) | $2 width cushion (SE) | $5 width cushion (SE) |
|---|---|---|---|
| $0.00 (table above) | 3.28 | 2.97 | 2.28 |
| $0.02 | 1.81 (fails) | 2.24 | 1.99 (fails) |
| $0.05 | -0.40 (net underpaid) | 1.13 (fails) | 1.55 (fails) |
| $0.10 | -4.08, net loss-making | -0.71 | 0.81 |

Real bid-ask spreads on these exact far-OTM SPY puts, checked live, run $0.01-$0.05 wide -- the same order of magnitude as the entire measured edge (average credit at 3%/$1 width is $0.068/share). The $1-width cell does not survive an ordinary $0.02/share cost; the $2 and $5 cells are more robust but not untouched. The directional claim ("at 3% distance the market overpays") still holds at every cost level tested, but the specific "clears 2 SE" framing above should be read as cost-free, not final.

---

## Experiment 12 — Live cost calibration, an expiry-selection bug, the Reviewer stage, and a ten-year reconstruction

**Context:** four pieces of work on the live-trading side of the options system, done together because each one changed a number the next one depended on. Numbering coordinated directly with a concurrent session (see the Experiments 13+ header below) to avoid a collision.

### 12a — The evidence gate's cost model was wired but never fed a real number

`evidence_gate.py`'s `required_win_rate` formula already used a slippage-adjusted `net_credit`, from an earlier fix -- but the backtest CSV it read from was always generated with `slippage_per_share=0.0`, so the cost-awareness was a no-op in practice. `selector.choose_distance_width` tie-broke on raw `cushion_se`, which is highest exactly where credit is thinnest (3%/$1's cushion of 3.28 SE was the best in Experiment 11's table, but its mean P&L goes negative under any real cost, per the addendum above).

**First attempt used an invented number and it backfired instructively.** Reasoning loosely from the addendum's "$0.01-$0.05 wide" quote, tried a 2c/leg (4c/spread) assumption. Fed into the gate's own formula, that number emptied it completely -- **zero of 24 cells clear 2 SE at 4c/spread.** Rather than quietly pick a smaller number because it keeps a trade alive (the exact pattern Guard #8's 0.08→0.04→0.0 history is a documented warning against, PROGRESS.md), the number was replaced with a live measurement: fetched the real chain (2026-09-01, spot $766.87, 8 DTE) and read the actual bid/ask on both legs of every (distance, width) cell the gate considers. Every liquid candidate (OI in the hundreds to tens of thousands) quoted at the **$0.01 minimum tick**, both legs, at every distance from 2% to 4%. Using the standard half-spread-per-leg convention (Rule #8 limits at mid): 0.005 + 0.005 = **$0.01/spread**, now `DEFAULT_SLIPPAGE_PER_SHARE` in `risk/options_config.py`.

At that measured cost, **3 of 24 cells still clear 2 SE** (3%/$1, $2, $5, same set as Experiment 11's zero-cost table), and the cost-adjusted tie-break (`mean_net_pnl`, added to `evidence_gate.compute_gate`'s output) now picks **3%/$5** instead of 3%/$1 -- the width whose live open interest can actually support the order (see 12b). Known limitation: one snapshot, one calm day; spreads widen in stress, which is exactly when the new term-structure guard (12d) is designed to skip trading anyway, so the two aren't independent, but this number shouldn't be read as a stress-period estimate.

### 12b — `choose_expiry` was violating "trade what was measured," and it explains a real live block

The Picker's first live run (documented in `PROGRESS.md`, Aug 31) was blocked by the liquidity guard on a $1-off-grid strike (OI 22 vs the 500 minimum). Fixing the strike to round to the nearest **$5 increment** (matching where SPY open interest actually concentrates) improved it to OI 386 on a live re-check -- real, but still short of 500.

Investigating why surfaced a second, independent bug: `spread_backtest.py`'s `_fridays_between` generates **Friday-only** entry/expiry dates -- every win rate and cushion in the evidence gate was measured on Friday-to-Friday cycles exclusively. But `choose_expiry`'s implementation picked whichever listed expiry was nearest to 7 DTE with **no weekday filter**, which can silently select a Wednesday expiry the backtest never tested. Confirmed live: the untested Wed 2026-09-09 expiry's 3% strike quoted **OI=386**; the identical strike on the tested Fri 2026-09-11 expiry quoted **OI=35,231** -- two orders of magnitude more. Restricting `choose_expiry` to Friday-only turned the live pipeline from BLOCKED to **PASS** end to end (all 14 guards), on real market data, same day.

### 12c — The Reviewer stage is built

Third stage of Picker → Guard → Reviewer. `pipeline/reviewer/reviewer.py`: Gemini reviews a Guard-approved proposal plus one real read-only account-context fetch through the existing MCP server (`get_account_info`), and may APPROVE, SHRINK (multiplier 0-1), or VETO. The safety property -- can only shrink or veto, never raise size, never originate a proposal -- is enforced by `apply_reviewer_decision`, a pure function with no LLM or network dependency, not by the prompt: any multiplier outside [0,1], any unrecognized decision string, and any exception from the network call itself (auth, timeout, quota) all clamp to a same-or-fewer-contracts result. Verified with 9 offline self-checks including the adversarial case (a simulated response asking to raise size 5x is clamped to 1.0x) and one live end-to-end call (real MCP fetch + real Gemini call, decision APPROVE, multiplier 1.0, correct reasoning). Wired into `run_agent.py` between guard-pass and order submission.

### 12d — Reconstructing 2016-2026 found a real strike-rounding interaction the earlier scratch analysis missed

**The point of this sub-experiment is the validation gate, not the reconstruction itself.** Real option prices only go back to Feb 2024 (confirmed the calmest stretch of available history in earlier informal analysis this session -- SPY fell >3% in a week 2.3% of the time in that window vs 8.5% in 2020-2023). Testing further back needs the fee modelled, since option prices don't exist that far back; the loss side never needs modelling, since it only needs real SPY closes (fetched to 2016 via `fetch_spy_history.py`, chunked into ~2-year windows after a full-range request was consistently rejected by the SIP feed with "does not permit querying recent SIP data" -- not transient, reproduced 3x; bisecting the same total range into yearly windows succeeded on SIP every time, recovering the genuine full history rather than falling back to IEX, which was confirmed to carry SPY only from 2018-11-01 onward).

**The fee side is modelled from CBOE's VIX9D** (9-day implied vol, free since 2011, closest published instrument to this strategy's tenor) via Black-Scholes with a level-dependent skew multiplier `k(vol) = a + b·VIX9D`, fit by grid search against the real 126 weeks. **The validation gate this exists to demonstrate:** an earlier attempt at this exact reconstruction, informally, used trailing realized volatility instead of VIX9D and had an aggregate correlation of 0.649 -- reported as one number, that looks acceptable. Split by volatility quartile, it priced calm weeks at **3% of reality** and volatile weeks at **125% of reality**, two opposite-signed errors that cancelled into a false aggregate and produced a completely wrong finding (a safety guard appearing to destroy 66% of profit) that had to be retracted before it reached this file. `reconstruct.py`'s `validate_reconstruction` makes that failure structural rather than something that has to be caught by chance: it checks the model/real ratio **per volatility quartile** and raises rather than proceeding if any quartile drifts outside [0.95, 1.05]. The corrected VIX9D model passes at fit `k(vol) = 1.18 − 0.95·VIX9D`, correlation 0.972, quartile ratios 0.98-1.03.

**A real, material correction found only by building this as committed code instead of scratch analysis.** The replay must use the SAME strike rule the live system actually trades (12b's $5-increment rounding), and an earlier informal version of this reconstruction had used the old $1-increment rule instead. Isolated side by side on identical inputs:

| | old $1-rule (superseded) | **correct $5-rule (live)** |
|---|---|---|
| 2018 total P&L | -16.40 | **-9.89** |
| Full-period (2016-2026) total | +38.28 | **+24.03** |

Both numbers move, and not uniformly: rounding to the nearest $5 buys more distance from spot on every week where the raw target wasn't already a multiple of 5, which trims premium collected everywhere. That reduces realized losses in most years but **not all** -- 2020 flips from a thin positive (+0.36 old) to a small loss (**-2.43 new**), because COVID's crash was severe enough that a few extra percent of distance barely changed whether the position was breached, while the extra distance still gave up premium on every other week that year. This is the same "further out isn't a free lunch" pattern found earlier this session (no distance survives 2022 either), now showing up as an interaction with the strike-rounding fix specifically. **Any number from the earlier informal reconstruction (this session's chat, not previously committed anywhere) is superseded by the figures in this entry.**

**The VIX term-structure filter, recomputed on the corrected data (portfolio basis: 2 concurrent positions at the 3% per-trade cap, $0.01/spread live-measured cost from 12a, idle weeks earning 3% cash, walk-forward 33rd-percentile threshold on VIX3M/VIX9D, fit only on prior weeks):**

| | annual return | volatility | Sharpe | max drawdown |
|---|---|---|---|---|
| trade every week | 3.20% | 7.20% | **0.03** | 21.24% |
| **VIX term-structure filter** | 3.56% | 3.27% | **0.17** | **5.63%** |

The base case is barely profitable at all under the corrected strike rule (Sharpe 0.03) -- the filter is not optional polish on a good strategy, it is most of what makes this one defensible. Ex-2018, the filter still costs Sharpe (0.29 → 0.20) while cutting the drawdown from 15.64% to 5.63%; it improves 3 of 10 years and costs 7, with the entire net full-sample benefit concentrated in 2018 (+10.15 of the delta) and 2020 (+4.22). **This remains insurance, not an edge** -- the same conclusion as the earlier informal version of this analysis, just at corrected magnitudes.

**Independent cross-validation from a completely different method (Experiment 13, concurrent session):** a direct statistical test of whether VIX/VIX3M predicts the weekly overpricing gap, on 19 years of data, found no usable correlation in general (wrong sign in the full sample) -- but investigating why backwardation's effect flips in 2013-2019 found 20 of 25 backwardation weeks in that stretch were false alarms and only 5 were real, clustered on **2015 and 2018**, the same years this portfolio backtest independently found the term-structure filter's entire benefit concentrated in. Two unrelated methods -- a statistical mechanism test on individual weeks and a portfolio backtest on realized P&L -- landing on the same shape (bad at predicting typical weeks, good at flagging rare crises) is stronger evidence than either alone. It also sharpens the honest limitation already stated above: the signal's value is concentrated in a small number of real events, not spread evenly across time, which is a reason to keep the filter as tail insurance and a reason not to oversell its Sharpe contribution in a normal year.

**Known limitations, unchanged from the informal version:** fees before Feb 2024 are modelled, not real, though now validated per-quartile rather than in aggregate. The headline still rests substantially on one year (2018) and one crisis. A fee-level filter (skip weeks where the offered credit was small) was tested and does nothing -- 2018 stays a large loss at every threshold tried; logged here as the negative result it is, not repeated as a positive claim anywhere in this project's write-up.

### 12e — `check_term_structure` built as a guard, and false-trip tested with the fix the previous guard's test needed

The guard from 12d's research is now live code (`guards.py`, `check_term_structure`): blocks when VIX3M/VIX9D falls below its own trailing 33rd percentile, computed only from data strictly before the decision date (`data/vix.py`'s `current_contango_and_threshold`, verified by construction against a manual prior-only quantile at an earlier as-of date). Fails closed on stale or missing VIX data, matching `check_data_sanity`'s existing convention. Replaces `check_volatility_regime`'s RV(10d) leg -- the same lagging quantity that broke 12d's first reconstruction attempt -- while keeping its separate yesterday's-move gap-risk leg unchanged.

**The false-trip test this guard needed is the one the guard it replaces never got.** The retired RV-threshold leg passed its own false-trip test at an aggregate 5.7% blocked -- but only 4 of 126 real weeks ever crossed its RV>25% trigger, so that pass was resting on almost no evidence either way. `false_trip.py` now reports `check_term_structure`'s blocked-winner rate **split into VIX9D quartiles with the count in each bucket printed**, specifically so this can't happen again silently:

| regime | n | blocked | blocked % |
|---|---|---|---|
| calmest | 31 | 0 | 0.0% |
| calm | 31 | 0 | 0.0% |
| active | 30 | 5 | 16.7% |
| most volatile | 31 | 20 | 64.5% |

(3%/$5, aggregate 20.3% blocked, well under the 30% bar -- but the aggregate number is the least interesting part of this table.) Every bucket has 30-31 weeks, not 4, and the shape is exactly what the guard is supposed to produce: **zero** false trips in the two calmest quartiles, concentrated blocking specifically where the risk actually lives. A guard that blocked evenly across all four buckets would be gating on something other than what it claims to.

The 20% aggregate is a real, accepted cost of the safety mechanism, not a sign of mis-calibration -- it is the same trade-off already quantified in 12d's portfolio comparison (the filter trades ~62% of weeks to buy a 4x smaller drawdown). A guard with a 0% false-trip rate here would mean it never blocks anything, which would just be Guard #8's original failure mode again under a different name.

---

## Volatility research track (Experiments 13+): predicting how far, not which way

**Context:** direction prediction is closed as of Experiment 10 (definitive negative result, IC indistinguishable from zero). Experiment 11 found an options-selling edge that does not survive realistic trading costs. This track asks a different, narrower question: can *volatility* -- how far SPY moves, not which way -- be forecast well enough to tell rich weeks from poor ones, so the strategy trades selectively instead of every week? Full hypothesis ladder and anti-overfitting protocol: `.claude/plans/we-need-a-major-buzzing-catmull.md`. **Numbering starts at 13, not 12** -- Experiment 12 is reserved for a separate, concurrent session's options-track entry (live-measured backtest cost correction, expiry-selection fix, Reviewer stage), coordinated directly between sessions to avoid a collision. This also supersedes the 12-16 ordering originally sketched in `VOLATILITY_ML_PLAN.md`, which predates that coordination.

### Experiment 13, Step 0 — Two data defects in the Experiment 11 backtest output, found before building anything new

**What we did:** before adding any new model, re-examined `output/data/spread_backtest_results.csv` directly for issues that would bias a volatility-timing result before it's even built.

**Defect A -- a truncation artifact inflates the last entry week to a fake win.** `raw_SPY.csv` ends 2026-08-24. The last entry Friday in the backtest (2026-08-21) is supposed to settle 7 days later, but the nearest available trading day on or before that target is only **3 days out**, because the price data simply stops. SPY barely moved in that 3-day window, so all 24 (distance, width) cells for that week are recorded as wins over an artificially short risk window. **Measured impact: immaterial.** Dropping the week moves the flagship 3%/$1 cushion from 3.28 to 3.30 SE at zero slippage, and from -0.40 to -0.36 SE at $0.05 slippage -- real, but not headline-changing. Dropped for hygiene (127 valid weeks -> 126).

**Defect B -- missing option-price data is not missing at random, and it hides the volatile weeks specifically.** Missing rate rises monotonically with distance (0.8% at 1% OTM up to 13.9% at 6% OTM, where contracts are thin and often don't trade). Critically, missing cells cluster in **more volatile** weeks: at 6% OTM, mean absolute weekly SPY move is 1.697% on weeks with missing data vs. 1.450% on weeks with complete data. This matters specifically for any future adaptive-strike strategy (the plan's H4/Experiment 16): a model choosing to sell further OTM in scary weeks would be choosing exactly the weeks where price data is most likely absent. Silently dropping missing cells in that setting would delete the hard trades and make the strategy look better than it is. Mitigation going forward: restrict adaptive selection to distances with <=3.9% missing data, treat a missing cell as "could not trade, fall back to a default," and report results with and without the affected weeks.

**A finding that changes the shape of the problem -- the ranking of widths inverts under cost, and the edge is not evenly distributed across time.** The Experiment 11 addendum only tested $1/$2/$5 width. The full sweep (all four widths the backtest actually replayed) shows $1 width is the best cell at zero slippage (3.30 SE) and the *worst* at $0.05 slippage (-0.36 SE), while **$5 width is the cost-robust choice** (1.55 SE at $0.05, still short of the 2.0 bar but the best available). Checking whether that holds up over time by splitting the 126 weeks into three equal chronological thirds, at $0.05 slippage:

| Period | Date range | $1 | $2 | $5 | $10 |
|---|---|---|---|---|---|
| early | 2024-02-09 to 2024-11-29 | -1.23 | -0.25 | 0.10 | -0.16 |
| mid | 2024-12-06 to 2025-10-03 | -0.52 | 0.07 | 0.19 | -0.04 |
| late | 2025-10-10 to 2026-08-14 | 1.90 | 3.04 | **3.30** | 2.99 |

$5 width wins in every sub-period, so the "$5 is cost-robust" finding itself is stable, not a full-sample artifact. But **the full-sample 1.55 SE headline is doing something different than it looks**: it is not a moderate, steady edge -- it is close to zero (0.10, 0.19 SE) across the first two-thirds of the real option data, and only clears the 2.0 bar (3.30 SE) in the most recent third. This is exactly the shape of question the volatility-timing hypotheses (H1/H4 in the linked plan) are built to test: is there a real, identifiable condition distinguishing the "late" period from "early"/"mid" (e.g. the VIX term structure -- see the coordination note above, a separate session is independently fetching VIX/VIX9D/VIX3M for a live risk guard, not this historical mechanism test, but the data source is shared and worth checking against for consistency), or is the full-sample average simply being pulled up by one recent, possibly unrepresentative, stretch? Both are live possibilities and the plan's kill criteria are written to distinguish them before either gets reported as a result.

**Script:** `pipeline/vol/step0_recheck.py` (reuses `pipeline.backtest.evidence_gate._cushion_for_cell` rather than reimplementing the cushion math).

### Experiment 13, Test 13a — Does the VIX term structure predict overpricing? (H1, no ML)

**Hypothesis, pre-registered:** the VIX/VIX3M ratio, observable at Friday entry, separates weeks the option market overprices from weeks it doesn't -- selling only in contango (VIX < VIX3M) should survive realistic slippage; selling every week doesn't (Experiment 11's finding). Backed by published research: VIX has closed above VIX3M on only ~8% of days since 2010, and the mechanism cited in the literature is that contango implies overstated volatility while backwardation does not.

**Data:** real observed VIX, VIX3M, and SPY daily closes, 2007-12-04 to 2026-08 (4,694 trading days / 939 non-overlapping Fridays). VIX from a concurrent session's CBOE cache (`output/data/vix.csv`); VIX3M spliced from that same CBOE cache (2009-09-18 onward) plus this session's yfinance mirror for 2007-12-04 to 2009-09-17, the only source with that stretch, cross-checked against the CBOE series on their 4,262 overlapping days first (mean abs diff $0.0005 -- essentially exact agreement, the splice is sound). SPY history fetched separately to `output/data/vol_spy_history.csv` (1993 onward), kept apart from `output/data/raw_SPY.csv` so this never collides with the options bot or the equity-direction track. For each trading day, computed `VIX - forward 21-trading-day realized SPY volatility` (VIX's own native horizon, not the 5-7 day trade horizon, to avoid a silent unit mismatch).

**What we did:** three independent tests of the same hypothesis, from least to most rigorous, on real data only, no simulation.

1. **Binary split, weekly non-overlapping cadence, three sub-periods** (2008-2012, 2013-2019, 2020-2026), comparing mean gap in contango weeks vs. backwardation weeks via Welch's t-test:

| Period | n contango / backward | mean gap contango | mean gap backward | t-stat |
|---|---|---|---|---|
| 2008-2012 | 202 / 49 | 4.83 | 0.99 | 1.58 |
| 2013-2019 | 329 / 25 | 2.84 | 4.39 | **-1.32 (wrong sign)** |
| 2020-2026 | 314 / 16 | 3.70 | -1.58 | 0.94 |

None reach conventional significance; 2013-2019 reverses direction entirely.

2. **Full-sample check for a cadence/autocorrelation artifact.** All trading days (raw, autocorrelated -- consecutive days share nearly all of the same 21-day forward window): t = 3.20, p = 0.001, looks strong. Weekly, non-overlapping: t = 1.28, p = 0.20, not significant. The strong-looking daily number is inflated by counting the same underlying volatility episode roughly 20 times over.

3. **Investigating the 2013-2019 reversal directly**, rather than dismissing it: of the 25 backwardation Fridays in that period, 20 had a *positive* gap (VIX still overpriced what followed), some substantially. Only 5 were negative, and those 5 cluster tightly around the three real volatility shocks of the period -- 2015-08-21 (day before the China-devaluation flash crash), 2018-02-02 (Friday before Volmageddon), 2018-12-07 (before the Dec 2018 selloff) -- with gaps of -3.8 to -10.2. Backwardation correctly flagged all three major crises of the decade, but was heavily outnumbered by false alarms, and the simple mean cannot separate the two.

**Follow-up test, because a hand-picked "it flagged 3 crises" story is exactly the kind of thing that needs checking against the full distribution, not just eyeballing sorted values:** does the *severity* of backwardation (the ratio's level, and separately its 5-day rate of change) have a monotonic relationship with the gap, via Spearman correlation on the full weekly sample?

| Period | n | rho, ratio level | p | rho, 5d change | p |
|---|---|---|---|---|---|
| 2008-2012 | 250 | -0.014 | 0.824 | -0.030 | 0.635 |
| 2013-2019 | 354 | **0.155** | **0.003** | 0.107 | 0.044 |
| 2020-2026 | 330 | 0.100 | 0.068 | 0.011 | 0.847 |
| full-sample | 934 | **0.126** | **<0.001** | 0.034 | 0.294 |

The hypothesis predicts a *negative* correlation (deeper backwardation -> smaller gap). What's measured is **positive and significant in the full sample** -- deeper backwardation is weakly associated with a *larger* gap, the opposite sign. The vivid three-crisis story from the sorted table was a true fact about three specific weeks, but not the dominant pattern across the full distribution; a proper rank correlation, not a hand-picked subset, is what settles this.

**Interpretation:** three independent tests -- binary mean comparison, autocorrelation-corrected full-sample, and continuous severity correlation -- agree the VIX/VIX3M term structure does not reliably predict weekly SPY option overpricing on 19 years of real data. This is treated as a genuine negative result for H1 as specified, the same class of finding as Experiment 10's direction-prediction null: real, checked three ways, not a bug or bad luck. It does not rule out a smarter construction of the same underlying idea (e.g. a wider or different reference tenor, a longer trailing window for the "severity" baseline, or combining term structure with another regime variable), but the specific, literature-motivated version tested here is killed.

**Scripts:** `pipeline/vol/vrp.py` (`build_dataset`, `mechanism_test`, `severity_test`), `pipeline/vol/data_sources.py` (VIX3M splice and its cross-check), `pipeline/vol_extract.py` (yfinance fetch). Full output: `output/data/vol_mechanism_test.csv`, `output/data/vol_severity_test.csv`.

**Coordination note, updated after reading the concurrent session's Experiment 12d:** that entry independently tested a related but distinct question -- not "does the term structure predict the weekly overpricing gap" (this entry's question, answered no), but "does a walk-forward VIX3M/VIX9D percentile filter improve a full portfolio backtest's Sharpe and drawdown" (2016-2026 reconstruction, portfolio basis). Their answer: yes on risk (Sharpe 0.03 -> 0.17, max drawdown 21.24% -> 5.63%), but the entire benefit concentrates in two crisis years (2018, 2020) while the filter *costs* Sharpe in 7 of 10 years -- their own framing, "insurance, not an edge."

**These two results are not in tension, they corroborate each other from different angles.** This entry's own severity investigation found the identical shape directly in the mean-gap data: 20 of 25 backwardation weeks in 2013-2019 were false alarms (gap still positive), while the 5 real ones clustered exactly on 2015, 2018 (x2), and by extension the years the portfolio test independently found the benefit concentrated in. A signal that is statistically unreliable at predicting the typical week's overpricing (what this entry tested and rejected) can still be economically valuable at flagging rare tail events (what Experiment 12d measured and found real) -- those are different claims, and the data supports the second while rejecting the first. **Combined, honest conclusion: the VIX term structure should not be used as a signal to select which weeks are more profitable to trade (H1 as originally specified, killed), but there is real, independently-replicated evidence it is useful as a crisis-avoidance / drawdown-reduction filter (consistent with Experiment 12d's live-measured result).** Flagged back to the concurrent session so both write-ups reflect this reconciliation rather than reading as two disconnected, seemingly-contradictory findings.

---

### Experiment 14 — Does a HAR volatility forecaster beat naive, and does fitting it by QLIKE instead of OLS matter? (H2/H3, first positive result of this track)

**Hypotheses, pre-registered:** (H3) estimating HAR by minimizing QLIKE directly, rather than the classical OLS-on-log-vol specification, materially improves out-of-sample QLIKE, per a 2026 *Journal of Forecasting* result. (H2, deferred to a future entry) downside semivariance should further improve on plain HAR-RV, per Patton & Sheppard (2015).

**Data:** real SPY realized volatility, 2016-07-01 to 2026-08-31 (2,555 trading days), computed from real 1-minute Alpaca bars -- confirmed available on this feed from roughly mid-2016 onward (2015-06-01 returned empty, 2016-06-01 returned 726 real bars; checked directly before building on it). Daily realized variance = sum of squared 1-minute log returns within regular trading hours (13:30-20:00 UTC), the standard Andersen-Bollerslev construction, annualized to match VIX's units. Distribution is sane: mean 10.8%, min 2.3%, max 89.2% (a plausible COVID-era spike), no flat or repeated values.

**What we did:** four forecasters of next-day log realized vol, all walk-forward validated (expanding window, 500-day minimum training, refit every 63 days, so every number below is genuinely out-of-sample, never fit on data it's scored against):
1. **Naive** -- tomorrow's vol = today's vol.
2. **EWMA** -- RiskMetrics-style exponential weighting (lambda=0.94).
3. **HAR-RV (OLS)** -- Corsi's classical specification: daily/weekly/monthly lagged log-vol averages, fit by ordinary least squares.
4. **HAR-RV (QLIKE)** -- same three features, fit by directly minimizing QLIKE loss via numerical optimization instead of OLS.

Evaluated on the common out-of-sample window (2018-06-27 to 2026-07-07, n=2,016 days) all four models share, using QLIKE (primary, the field-standard loss that penalizes under-forecasting harder than over-forecasting), MSE on log-variance, and Mincer-Zarnowitz R². Every scoring function was first calibrated against known cases before trusting it on real output: QLIKE reads exactly 0 at a perfect forecast and confirmed higher for under- vs over-forecasting by the same ratio; Mincer-Zarnowitz R² reads exactly 1.0 at a perfect forecast; Diebold-Mariano confirmed to correctly detect an obviously-better series (t=-47.7, p~0) and to read ~0 on two identical series.

**Results:**

| Model | n | mean QLIKE | mean MSE(log) | MZ R² |
|---|---|---|---|---|
| **HAR-RV (QLIKE)** | 2016 | **0.194** | 0.384 | **0.619** |
| HAR-RV (OLS) | 2016 | 0.221 | 0.358 | 0.605 |
| Naive | 2016 | 0.251 | 0.428 | 0.583 |
| EWMA | 2016 | 0.332 | 0.678 | 0.296 |

Diebold-Mariano (Newey-West HAC): HAR-OLS beats naive, t = -4.62, p < 0.0001. HAR-QLIKE beats HAR-OLS, t = -6.70, p < 0.0001. **90% Model Confidence Set retains only HAR-RV (QLIKE)** -- it is not just nominally best, it is the single model that cannot be statistically ruled out at 90% confidence once all four are compared together (Hansen-Lunde-Nason 2011 style block-bootstrap elimination), which is the right multi-model comparison tool for exactly this "which of several models is best" question rather than a series of uncorrected pairwise tests.

**Why the QLIKE fit wins, checked directly rather than assumed:** OLS-fit HAR is systematically biased low on the variance scale -- its mean forecast variance is only 77% of mean realized variance, and it under-predicts realized variance on 49% of out-of-sample days, essentially a coin flip. This is the textbook consequence of fitting in log-space and exponentiating back (Jensen's inequality: E[exp(X)] > exp(E[X])), not a bug in this implementation. QLIKE-fit HAR corrects most of this bias directly (94% of mean realized variance) and under-predicts on only 37% of days. This matters economically, not just statistically: under-predicting volatility is the dangerous direction for a strategy that sells options against it, since it means underestimating the risk actually being taken on.

**Interpretation:** this is the first positive, literature-confirming result of the volatility research track (H1's term-structure timing signal was killed in the entry above). Both the ranking (naive < HAR-OLS < HAR-QLIKE) and the *reason* HAR-QLIKE wins (correcting a known retransformation bias, verified directly rather than inferred from the metric alone) match the cited research and have a clear economic interpretation, not just a lower number on a chart.

**Scripts:** `pipeline/vol/rv.py` (`fetch_intraday_daily_rv`, real 1-min bar aggregation), `pipeline/vol/har.py` (`HARModel`, both loss specifications), `pipeline/vol/walkforward.py` (`run_walk_forward`), `pipeline/vol/forecast_eval.py` (`qlike`, `mse_log`, `mincer_zarnowitz_r2`, `diebold_mariano`, `model_confidence_set`), `pipeline/vol/experiment14_forecast.py` (the driver). Output: `output/data/vol_spy_intraday_rv.csv`, `output/data/vol_experiment14_results.csv`.

**Known limitation, stated rather than hidden:** the OOS window (2018-2026) is one continuous stretch, the same single-window limitation flagged in Experiment 6d for the equity track and Experiment 13 above for the term-structure test. The walk-forward re-splitting means the model is genuinely never trained on its own test data, but it doesn't fully answer whether HAR-QLIKE's advantage is stable across sub-periods the way Experiment 13's sub-period check was applied to the width finding -- worth doing before this result is used to size anything.

**Next steps:** H2 (downside semivariance / SHAR, using the same real intraday bars this entry already fetched) as a direct extension; H4 (does this forecast convert to money against the real 126-week options backtest) as the economic test this forecasting accuracy result does not, by itself, answer -- per the plan's own standing caveat that "a more accurate volatility forecast does not promise better trading performance."

---

### Experiment 15 — Does Experiment 14's forecast convert to money? (H4, and a real design flaw caught before trusting the result)

**Hypothesis, pre-registered:** comparing the QLIKE-HAR forecast against the market's implied breach probability (`credit / width`, already in the backtest data, no option-pricing model needed) should identify which weekly distance to sell, beating the fixed baseline established in Step 0 (3% distance, $5 width -- the realistic-cost-robust choice, not the $1-width cell that fails under cost). Per the plan's design discipline: this varies WHICH CELL is sold rather than skipping weeks, keeping n near the full 126-week sample rather than collapsing to ~50 weeks and inflating every standard error ~1.58x.

**Two design attempts failed before reaching a trustworthy one -- logged because catching this mattered more than the final number:**

1. **First attempt:** let the signal choose freely among distance AND width, picking whichever cell had the largest raw probability edge (`implied_prob - forecast_prob`). Result looked like a strong, significant loss (paired t = -2.75, p = 0.007) -- but the picks were suspicious: width $1 was chosen 92 of 125 weeks, the exact cell Step 0 already established is the *worst* performer after realistic cost. The metric was comparing probabilities across cells with very different dollar stakes -- a 2-percentage-point edge means far less in dollar terms on a $1-wide spread than a $10-wide one, so raw probability comparison collapses onto whichever width happens to look best in probability space, independent of the forecast's actual information content.
2. **Second attempt:** multiply the edge by width to convert it to dollar terms. This just inverted the bias -- width $10 was chosen 63 of 125 weeks, because expected value scales linearly with width while risk scales with it too, so an unconstrained dollar-edge maximization degenerates into "always pick the biggest position," not a genuine read of the forecast.
3. **Final design:** hold width FIXED at the Step 0 baseline ($5) and let the signal choose only among eligible distances (1-4%, restricted per Defect B's missing-data mitigation). At a fixed width, probability edges represent identical dollar stakes, so comparing them across distances is valid -- this also matches the plan's original, narrower design intent (the signal chooses distance, not width).

**Result, final design, real 125-126 weeks (one week's baseline cell itself has missing data, correctly excluded from the paired comparison rather than imputed):**

| Slippage | n | Mean P&L, adaptive | Mean P&L, baseline | Diff | Paired t | p-value |
|---|---|---|---|---|---|---|
| $0.00 | 125 | 0.163 | 0.196 | -0.032 | -0.80 | 0.42 |
| $0.02 | 125 | 0.143 | 0.176 | -0.032 | -0.80 | 0.42 |
| $0.05 | 125 | 0.113 | 0.146 | -0.032 | -0.80 | 0.42 |

(The diff is identical across slippage levels by construction -- the same flat per-share charge applies to exactly one leg-pair in both the adaptive and baseline series every week, so it cancels in the paired difference. Not a bug.)

Adaptive distance picks skew toward 4% (75 of 126 weeks) -- the forecaster is choosing to sell further out-of-the-money more often than the fixed 3% baseline does.

**Interpretation:** the forecast-based distance selection does not beat the fixed baseline -- the difference is small, slightly negative, and not statistically distinguishable from zero (p=0.42). This is a real negative result for H4 as specified, joining H1 as a killed hypothesis this session, consistent with the plan's own standing caveat, quoted from the literature before this was ever run: "a more accurate volatility forecast does not promise better trading performance." Experiment 14's forecaster is real and validated; using it this way to pick a strike does not, on this sample, produce a better trade.

**Scripts:** `pipeline/vol/overlay.py`. Output: `output/data/vol_experiment15_overlay.csv`.

---

### Experiment 16 — Does downside semivariance (SHAR) beat plain HAR-RV? (H2)

**Hypothesis, pre-registered:** Patton & Sheppard (2015) found future volatility is far more strongly predicted by the volatility of past *negative* returns than positive ones. SHAR replaces HAR's plain daily term with two separate terms -- realized semivariance from up-minutes and down-minutes -- keeping weekly/monthly terms as plain total RV (their own finding was that the sign split matters most at the shortest horizon).

**Data:** the same real 1-minute SPY bars fetched for Experiment 14, extended in one pass (no second fetch) to also compute signed semivariance (RS+, RS-) and bipower variation. Verified before use: on real data, RS+ (88.58) + RS- (86.72) reconstructs total RV (175.30) exactly, and bipower variation (169.17, jump-robust) sits below total RV as required -- both checked first on a synthetic series with a known injected jump (recovered the injected jump size almost exactly) before trusting the real-data numbers.

**What we did:** fit both plain HAR-RV and SHAR by QLIKE (Experiment 14's established winner, so this isolates the effect of the feature split alone, not a re-test of the loss function), same walk-forward discipline, same out-of-sample window (2018-06-27 to 2026-07-07, n=2,016).

| Model | Mean QLIKE | MSE (log) | MZ R² |
|---|---|---|---|
| SHAR (QLIKE) | 0.19436 | 0.3824 | 0.6222 |
| HAR-RV (QLIKE) | 0.19446 | 0.3839 | 0.6192 |

Diebold-Mariano: mean difference -0.0001, t = -0.20, p = 0.84 -- not remotely significant.

**Interpretation:** SHAR is nominally marginally better on every metric, but the difference is statistically indistinguishable from zero. This is a genuine null result for H2 as specified on this data -- the downside-semivariance split does not measurably improve on an already QLIKE-fit HAR-RV for SPY at daily/weekly/monthly horizons. Plausible reasons, not tested further here: Patton-Sheppard's asymmetry effect is typically stronger for individual stocks than for a broad index like SPY (their own paper found smaller index-level effects too), and ~8 years of daily observations may simply be too short a sample to resolve an effect this small. Logged as a real negative result, the same discipline as H1 and H4 above -- not every literature-motivated hypothesis needs to pan out to be worth testing properly.

**Scripts:** `pipeline/vol/rv.py` (`fetch_intraday_full`), `pipeline/vol/har.py` (`build_shar_features`), `pipeline/vol/experiment16_shar.py`. Output: `output/data/vol_spy_intraday_full.csv`, `output/data/vol_experiment16_shar_results.csv`.

---

### Experiment 17 — Does XGBoost beat HAR, with or without exogenous information? (H5, pre-registered hypothesis only half-confirmed)

**Hypothesis, pre-registered:** per "HARd to Beat" (arXiv 2406.08041) and the Financial Innovation review, XGBoost given only HAR's own inputs should NOT beat HAR (HAR wins when the information set is limited); it should only have a chance once given genuinely exogenous information HAR structurally cannot see. Two such features, both already on disk from the equity-direction track and otherwise unused this session: market-wide cross-sectional dispersion (std of daily returns across the 40 tracked stocks -- a known leading indicator of index volatility) and total daily news volume across those same 40 symbols (Experiment 9's `news_count`, which ranked dead last of 18 features for predicting *direction* but whose own research check found news volume predicts volatility better than direction -- right feature, wrong target the first time).

**A real bug caught before trusting the first run:** the 40-stock dispersion feature only exists from 2020-02-13 (the panel data's own start date), 910 of the realized-vol series' 2,555 days earlier. The walk-forward's default 500-day minimum training window put the first several training windows entirely before that date, so after dropping rows with missing features, XGBoost was fit on an **empty** training set -- caught directly from XGBoost's own "Empty dataset at worker" warning and a nonsensical mean QLIKE of 62 (every other model scores ~0.19-0.25). Fixed by raising the minimum training window to 950 days so the first split already contains real exogenous data, not by silently working around the warning.

**Results, corrected, common out-of-sample window 2020-04-13 to 2026-07-20 (n=1,575, shorter than Experiments 14/16's window because exogenous data starts later):**

| Model | Mean QLIKE | MSE (log) | MZ R² |
|---|---|---|---|
| HAR-RV (QLIKE) | **0.1908** | 0.3813 | 0.3086 |
| XGBoost (exogenous features) | 0.2252 | 0.4078 | 0.2287 |
| XGBoost (HAR components only) | 0.2256 | 0.3671 | 0.2718 |

Diebold-Mariano: XGB(HAR-only) vs HAR-QLIKE, t = 5.93, p < 0.0001, HAR wins -- confirms the predicted null half exactly. XGB(exogenous) vs HAR-QLIKE, t = 4.83, p < 0.0001, **HAR still wins**. XGB(exogenous) vs XGB(HAR-only), t = -0.06, p = 0.95 -- the exogenous features made essentially no difference to XGBoost at all. 90% Model Confidence Set retains only HAR-QLIKE.

**Interpretation, reported honestly against what was predicted:** the null half of H5 is confirmed cleanly -- XGBoost does not beat HAR on HAR's own inputs. But the hypothesis's positive half is **not** confirmed: XGBoost was predicted to have a real chance once given dispersion and news volume, and it didn't -- those features added no measurable value to XGBoost either (t=-0.06 between the two XGBoost variants), and HAR-QLIKE remains the sole survivor of the model confidence set in both configurations. This is a stronger, more definitive result than the pre-registered hypothesis anticipated, not a weaker one: it isn't just that ML needs richer information to compete with HAR here, it's that neither the model class nor these two exogenous features move the needle on this specific target, on real data, checked directly. `panel.py`'s cross-sectional dispersion and `news_count` do not, on this evidence, earn a place in the volatility forecast -- consistent with `news_count`'s own history in this project (Experiment 9: ranked dead last of 18 features for direction; here, ranked no better for volatility either).

**Scripts:** `pipeline/vol/exogenous.py` (`build_market_dispersion`, `build_news_count`, reusing `output/data/engineered_*.csv` and `raw_news.csv` from the equity track), `pipeline/vol/experiment17_ml.py`. Output: `output/data/vol_experiment17_ml_results.csv`.

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
