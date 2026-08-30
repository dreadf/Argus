# Research Note: Pooled (Cross-Sectional) vs. Per-Stock Models vs. Ensemble

## Question being investigated

Before scaling the feature-ablation pipeline from 5 symbols to a much larger universe (e.g. ~300 stocks), we need to decide *how* to use that larger universe:

1. **Individual/per-stock models** — repeat the existing per-symbol ablation independently on many more stocks (what we already did for AAPL/MSFT/JPM/KO/XOM, just at scale).
2. **Pooled/cross-sectional model** — stack all stocks into one panel (`row = one stock on one day`) and train a single model across all of them at once.
3. **Ensemble/hybrid** — some way of combining a pooled (global) model with stock-specific (local) behavior, rather than picking strictly one or the other.

This note summarizes what the literature says about this exact tradeoff, to inform which direction is worth prototyping first.

---

## 1. Evidence in favor of pooling

**Gu, Kelly, and Xiu (2020)** is the most-cited large-scale empirical study of exactly this design choice: they compare machine learning methods (linear, tree-based, neural networks) for predicting the panel of *individual* US stock returns, pooling thousands of stocks into one training set rather than fitting a model per stock. They find tree-based models and neural networks substantially outperform linear models, and trace the gains to nonlinear interactions among firm characteristics that a small, single-stock sample could never estimate reliably. This is effectively confirmation that our own project's XGBoost-over-Logistic-Regression comparison direction is sound, and that pooling is the standard way large-scale empirical asset pricing work is actually done — no serious study in this literature trains one model per stock.

**Sirignano and Cont (2019)** is even more directly relevant to the overfitting problem we've hit throughout this project. They train a single ("universal") deep learning model on a pooled dataset of roughly 500 stocks and compare it against stock-specific models. Their central finding: stock-specific models are more exposed to overfitting because of the mismatch between the number of model parameters and the small size of a single stock's history, while the pooled model generalizes by interpolating across the much richer combined scenario space — they report that one year of pooled data is roughly equivalent to 500 years of single-stock training data, and that the diversity/heterogeneity across stocks *enhances* rather than harms the richness of that training signal. This is a strong, concrete answer to our project's recurring overfitting problem (train/test accuracy gaps of 0.13–0.26 throughout Experiments 2–3): the fix may be more rows via pooling, not more regularization on a small per-stock dataset.

---

## 2. Evidence for the heterogeneity/noise concern

**Döbelt (2026, working paper)** argues that standard architectures which pool all stocks and use identical parameters for each one fail to capture meaningful cross-sectional variation in how different sectors respond to the same signals, contradicting empirical evidence of substantial heterogeneity across industries. The paper's fix is not to abandon pooling, but to add *learnable sector-level structure* on top of it (sector embeddings), and finds the sector-aware pooled model significantly outperforms both a plain pooled LSTM and per-stock-agnostic baselines. This is important: the finding is not "pooling fails," it's "*naive, structure-free* pooling loses information that a smarter pooled design can recover."

**Concrete setup and numbers (Döbelt 2026):** the "plain pooled, structure-free" baseline is a single LSTM (25 hidden units) fed 60 lagged daily returns, with **identical weights shared across every stock** — the model has no way to know which stock (or sector) it's even looking at; every stock is processed as if drawn from the same distribution. The "structured" version keeps the exact same shared LSTM, but concatenates a small **learnable sector embedding** (2 dimensions, one per TRBC sector classification) onto the hidden state before the final classification layer — so the model still shares almost all its parameters across stocks, but gets a small per-sector adjustment term added at the end.

Results: directional accuracy 52.5% (sector-aware) vs. 52.2% (plain pooled) vs. ~51.8% (random forest baseline); annualized Sharpe ratio 1.41 vs. 1.26 vs. ~1.10; mean daily return after transaction costs 0.053% vs. 0.033% vs. ~0.040%. The sector-vs-plain-pooled improvement in accuracy was only marginally significant (Diebold-Mariano p=0.092), but the improvement over random forest was highly significant (p=0.0095). **Takeaway: the "structure-free pooling loses signal" effect here is real but small** — a couple of extra learnable numbers per sector recovered a modest, largely-consistent edge across every architecture depth tested (1–5 LSTM layers).

**Pesaran, Pick, and Timmermann (2024)** address this tension head-on from an econometric forecasting perspective, formally comparing individual, pooled, fixed-effects, and empirical-Bayes estimators across panel forecasting problems. Their key result: which estimator wins depends on the degree of parameter heterogeneity across units, whether that heterogeneity correlates with the predictors, and the overall goodness of fit — and they propose *optimal forecast-combination weights* between the individual and pooled estimates rather than treating it as an either/or choice. This is a direct, methodologically rigorous precedent for your "maybe we can ensemble the two options" instinct — it's not just plausible, it's an established estimation strategy (essentially a data-driven blend between "trust the individual stock's own history" and "trust the pooled cross-section").

---

## 3. Evidence for the ensemble/hybrid middle ground

**Ghosn and Bengio (1996)** is the earliest and most directly on-topic precedent: a multi-task learning framework for stock selection, where a shared (global) representation is learned jointly across many stocks' prediction tasks, while still allowing task-specific (per-stock) output structure. This is conceptually the multi-task-learning ancestor of the "ensemble both" idea — rather than a single global model or independent local models, the shared hidden representation captures cross-stock structure while each stock keeps its own task-specific head. It is a strong historical precedent that blending shared and stock-specific structure was recognized as valuable for exactly this problem from very early in the neural-network literature. **Reported results:** roughly **3–4% relative accuracy improvement** over independent single-stock baseline models, and in a portfolio experiment on Canadian stocks, **annual returns more than 14% above** the benchmarks they compared against.

**Feng and He (2022)** operationalize a similar blend via Bayesian hierarchical modeling: a hierarchical prior pools information across all assets/time periods (the "global" signal), while asset- and time-specific coefficients are still estimated conditional on that shared prior (the "local" signal), rather than either forcing one fixed global coefficient or estimating each asset completely independently. Their hierarchical approach outperforms the alternative estimators they compare against on both point prediction and interval coverage. **Reported results:** in a sector-investing application over roughly the past 20 years, the Bayesian hierarchical strategy delivered **0.92% average monthly return** and a statistically significant **Jensen's alpha of 0.32%**, outperforming the alternative (non-hierarchical) methods they benchmarked against on out-of-sample R² as well. This gives a second, independent methodological path toward the same "ensemble global + local" goal — hierarchical Bayesian pooling, as an alternative to a purely engineering-side model-averaging ensemble.

**Pesaran, Pick, and Timmermann (2026)**, in Monte Carlo simulations plus real applications to house prices and CPI inflation panels, find that **empirical Bayes and forecast-combination methods perform best overall and are rarely the worst performer for any individual series** — whereas the plain "individual" and plain "pooled" estimators each occasionally perform very badly, depending on how much true heterogeneity exists in that specific panel. This is an important, more cautious result: it's not that empirical Bayes/combination always wins outright, it's that it is the most *reliably safe* choice across different heterogeneity conditions, which is exactly the property you want when you don't yet know how heterogeneous your stock universe really is.

---

## Synthesis and recommendation for our pipeline

All three positions have real support, but the strongest and most consistent message across all five sources is:

> **Naive per-stock modeling on a small sample (what we did for AAPL/MSFT/JPM/KO/XOM) is the weakest option, and the literature consensus is that some form of pooling is necessary to get enough statistical power, but *fully unstructured* pooling that ignores cross-stock heterogeneity is also known to leave real, recoverable signal on the table.**

Concretely, for our own next step, this points toward:
1. **First prototype a pooled/panel model** (Gu-Kelly-Xiu / Sirignano-Cont direction) on a modest universe (20–30 stocks) with a correctly-designed date-based train/test split, this directly attacks the overfitting problem that has recurred throughout Experiments 2–3, and is the best-evidenced single change we can make.
2. **Then test whether adding stock/sector-level structure improves it further** (Döbelt's sector-embedding result, or Feng-He's hierarchical Bayesian structure, or Ghosn-Bengio's multi-task shared-representation approach), this is the "ensemble" step, and the literature gives us three different concrete mechanisms to try, not just one.
3. Only fall back to independent per-stock modeling (our current approach) as a baseline comparison, not as the main strategy, the evidence suggests it will keep underperforming for the same overfitting reasons we've already diagnosed.

---

## References

[1] Ghosn, J. and Bengio, Y. (1997). Multi-Task Learning for Stock Selection. In *Advances in Neural Information Processing Systems 9 (NIPS 1996)*, pages 946–952. MIT Press.

[2] Gu, S., Kelly, B., and Xiu, D. (2020). Empirical Asset Pricing via Machine Learning. *The Review of Financial Studies*, 33(5):2223–2273.

[3] Sirignano, J. and Cont, R. (2019). Universal Features of Price Formation in Financial Markets: Perspectives From Deep Learning. *Quantitative Finance*, 19(9):1449–1459.

[4] Feng, G. and He, J. (2022). Factor Investing: A Bayesian Hierarchical Approach. *Journal of Econometrics*, 230(1):183–200.

[5] Pesaran, M. H., Pick, A., and Timmermann, A. (2026). Forecasting with Panel Data: Estimation Uncertainty versus Parameter Heterogeneity. *Quantitative Economics* (forthcoming). arXiv:2404.11198.

[6] Döbelt, J. (2026). Cross-Sectional Heterogeneity in LSTM Networks for Financial Time Series. Technical University of Darmstadt. arXiv:2608.05755. *(preprint, not yet peer-reviewed)*

---

## Open questions still to resolve before implementation

- What universe size is large enough to see the pooling benefit, but small enough to iterate quickly? (Proposed: start at 20–30 stocks, per the earlier plan discussion.)
- How should the train/test split be redesigned for pooled data? (Must be date-based across the whole panel, not row-position-based — flagged previously as a critical bug risk if reused naively from the current per-symbol scripts.)
- Which "local" structure to add first if plain pooling underperforms: sector embeddings (Döbelt), hierarchical Bayesian per-stock coefficients (Feng & He), or a shared-representation multi-task architecture (Ghosn & Bengio)? This should probably be decided empirically, after seeing how much (if any) heterogeneity loss shows up in the plain pooled baseline.
