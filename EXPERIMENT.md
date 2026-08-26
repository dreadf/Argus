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

## Running Synthesis (as of last entry)

The project has now been tested end-to-end across baseline → linear model → nonlinear model → single-symbol feature ablation → multi-symbol generalization check, with consistent diagnostic rigor at each step (leakage checks, chronological splitting, overfitting checks, cross-validation, multiple-testing awareness). The honest conclusion at this stage: **AAPL-specific patterns (`A+D`) do not generalize; `B+D` shows a partial, sector-limited pattern (KO/XOM) that is the best lead so far but far from a robust cross-market signal.**

**Next steps under consideration:**
- Investigate `B+D`'s KO/XOM-specific consistency further — is there a sector-level (defensive/traditional vs. tech/growth) explanation, or is 2/5 still within the range of chance given multiple testing?
- Test whether ensembling separately-trained models (rather than concatenating features into one model) produces a more robust combined signal.
- Group E (market context, e.g. SPY) from the plan remains untried and is a genuinely new information source.
- Alternatively, treat "no robust cross-stock signal from price/volume technicals alone" as the project's current, legitimate Phase 2 finding, and pivot toward either a different feature source (Group E) or a different, more tolerant research question (e.g., per-symbol tuned models rather than one general model).
