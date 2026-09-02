# Sources

Every external paper, article, or reference cited anywhere in this project's
research (`EXPERIMENT.md`, `.claude/plans/`, session discussion), in one
place, so a claim can be traced back to what actually supports it and reused
later without re-searching. **Add to this file the same session a source is
first cited — do not let citations live only in chat or in EXPERIMENT.md.**

Format per entry: what it is, where/how it was used in this project, and any
caveat about how strongly it should be trusted (preprint vs. peer-reviewed,
sample period, etc).

---

## Volatility forecasting

- **Corsi, F. (2009), "A Simple Approximate Long-Memory Model of Realized
  Volatility"** (the original HAR paper). Basis for `pipeline/vol/har.py`'s
  daily/weekly/monthly specification (Experiment 14) and the multi-horizon
  (1-day / 1-week / 2-week) target construction tested in Experiment 22.

- **Andersen, T., Bollerslev, T. & Diebold, F. (2007), "Roughing It Up:
  Including Jump Components in the Measurement, Modeling, and Forecasting
  of Return Volatility," REStat.** The HAR-J / HAR-RV-CJ specification:
  decompose realized variance into its continuous (bipower) and jump
  components and enter the jump term separately. Basis for Experiment 25.
  Also the origin of the Andersen-Bollerslev realized-variance construction
  used throughout this track (sum of squared intraday returns), and of
  bipower variation as the jump-robust estimator (Barndorff-Nielsen &
  Shephard). **Partially confirmed on our data:** the jump coefficient came
  out consistently negative across all 32 walk-forward refits, matching the
  documented finding that the jump component is *less persistent* than the
  continuous component — but the forecasting improvement over plain HAR-RV
  was not significant (DM t=-0.16, p=0.875), so the effect is real and
  correctly signed but too small to matter at this sample size.

- **Patton, A. & Sheppard, K. (2015), "Good Volatility, Bad Volatility:
  Signed Jumps and the Persistence of Volatility," REStat.**
  https://public.econ.duke.edu/~ap172/Patton_Sheppard_REStat_2015.pdf
  Basis for the SHAR (signed semivariance) specification tested in
  Experiment 16 (H2) — found downside RV predicts future vol better than
  upside. **Our own test of this on SPY (Experiment 16) came back null**
  (DM t=-0.20, p=0.84) — noted as a real divergence from the cited result,
  not swept aside.

- **2026 Journal of Forecasting paper on QLIKE-direct HAR fitting.**
  https://onlinelibrary.wiley.com/doi/10.1002/for.70114
  Basis for Experiment 14's H3 (fit HAR by minimizing QLIKE directly
  instead of OLS-then-exponentiate). **Confirmed on our data**: QLIKE-fit
  HAR beat OLS-fit HAR, DM t=-6.70, p<0.0001, and the mechanism (Jensen's
  inequality retransformation bias) was independently verified, not just
  assumed from the citation.

- **Kambouroudis et al. (2021) and related, on HAR + VIX ("HAR-X").**
  Basis for Experiment 18 — cited as finding that augmenting HAR with VIX
  "notably improves forecast performance." **Confirmed on our data**:
  DM t=-3.22, p=0.0013 vs plain HAR-RV, VIX coefficient positive across
  all 32 walk-forward refits.

- **"HARd to Beat" (arXiv 2406.08041).**
  https://arxiv.org/pdf/2406.08041
  Found ML (XGBoost etc.) fails to surpass HAR when both use only RV and
  VIX; window length matters more than model choice. Basis for Experiment
  17 (H5)'s prior that XGBoost on HAR-only features would not beat HAR.
  **Confirmed on our data** (both XGBoost configurations lost to HAR-RV).

- **Financial Innovation review on ML vs. HAR.**
  https://link.springer.com/article/10.1186/s40854-025-00809-5
  "HAR wins when the information set is limited" — same prior as above,
  independent source.

- **ScienceDirect 2026 piece on deep learning beating HAR only with macro
  variables.** https://www.sciencedirect.com/science/article/pii/S105905602500334X
  Third independent source for the same H5 prior.

- **Wade, R. (2026), "Do Better Volatility Forecasts Lead to Better
  Portfolios? Evidence from Graph Neural Networks."**
  https://arxiv.org/abs/2605.19278 (code: https://github.com/waderylan/sp500-gnn)
  Central finding: the model with lowest forecast MSE, the model with
  highest cross-sectional ranking accuracy, and the model with the
  highest portfolio Sharpe ratio were **three different models** on 465
  S&P 500 names, 2015-2025. **Directly explains our own Experiment 19
  result** (a significantly better forecaster, HAR-X, produced no better
  economic outcome) as an expected, documented phenomenon rather than a
  diagnosis failure on our part.

## Variance risk premium / VIX term structure (H1, killed)

- **VolRadar, on VIX/VIX3M contango frequency.**
  https://volradar.com/learn/term-structure
  Cited figure: VIX has closed above VIX3M (backwardation) on only ~8% of
  trading days since 2010. Used to size Experiment 13's contango/backwardation
  test. **Caveat we caught ourselves:** a commonly-quoted "~80% contango"
  figure describes VIX *futures* term structure, a different instrument
  from the VIX/VIX3M index ratio used here — do not conflate the two.

- **options.cafe, practitioner guidance on reducing short premium exposure
  in backwardation.** https://options.cafe/blog/vix-term-structure-contango-backwardation/

- **SharpeTwo, on the variance risk premium.**
  https://sharpetwo.com/blog/variance-risk-premium/
  Cited figure: SPY implied vol has averaged ~9% above realized vol
  1-month-forward.

- **AlphaArchitect, "The Variance Risk Premium Is Pervasive."**
  https://alphaarchitect.com/the-variance-risk-premium-is-pervasive/
  Cited for downside ("bad") variance carrying a larger premium than
  upside variance — part of Experiment 14's H2 rationale.

- **macroption.com, VIX3M launch date and history.**
  https://www.macroption.com/vix3m/
  Used to correct an initial factual error (assumed VIX3M started Dec
  2001; actually Dec 4, 2007) before it was used for anything load-bearing
  — logged in the plan's own verification log, item 2.

- **sixfigureinvesting.com, VIX9D (VXST) launch and specification.**
  https://www.sixfigureinvesting.com/2014/02/vxst-index-futures-options-quotes-and-expiration-dates/
  Corrected an initial assumption that VIX9D existed from 2011; actual
  launch was Oct 2013 — plan verification log item 11.

**Experiment 13's overall verdict: H1 (VIX term structure as an overpricing
timing filter) was killed** — not significant, and wrong sign in the
2013-2019 sub-period, despite every cited source above pointing the
expected direction. Recorded as a real negative result, not omitted because
the citations "should have" worked.

## Risk management / breach probability (H4)

- **Barone-Adesi, G., Giannopoulos, K. & Vosper, R. (1999), and the standard
  VaR literature since**, on filtered historical simulation. Basis for
  Experiment 20's skew-aware empirical breach probability
  (`pipeline/vol/skew_breach.py`) — standardize historical returns by
  contemporaneous volatility, use the empirical distribution instead of
  assuming normality. **A genuine methodological improvement on our data**
  (mechanical per-distance bias shrank substantially, within-distance
  timing signal became significant at all 4 distances instead of 2), but
  did not by itself produce a significant trading edge (Experiment 20
  main result, and see Experiment 21 below).

## Position sizing / risk-adjusted use of a volatility forecast

- **Moreira, A. & Muir, T. (2017), "Volatility-Managed Portfolios,"
  Journal of Finance.**
  https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12513
  (working paper: https://www.nber.org/system/files/working_papers/w22208/w22208.pdf)
  Scaling portfolio weight by inverse trailing realized variance raises
  Sharpe ratios across multiple factors — the founding result for
  "volatility forecasts are for *sizing*, not *timing*."

- **Cederburg, S. et al., "On the performance of volatility-managed
  portfolios," Journal of Financial Economics.**
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X2030132X
  Important counterweight to Moreira-Muir: reasonable out-of-sample
  implementations of vol-managed portfolios generally do **not**
  systematically beat the unmanaged portfolio; the improvement is fragile
  to implementation choices. Also: strategies scaled by *downside*
  volatility specifically outperform those scaled by total volatility —
  motivates testing our RS-/RS+ semivariance data (already computed in
  Experiment 16) for sizing rather than only for forecasting.

- **Wysocki, M. (2026), "Harvesting the Volatility Risk Premium: A
  Learning-to-Rank Approach."** https://arxiv.org/abs/2608.24786
  Directly comparable trade to ours (S&P 500 weekly/0DTE short-put
  selection), but with a learned LightGBM LambdaRank cross-sectional
  ranker (including a SKIP candidate ranked *inside* the cross-section)
  and a path-aware Sortino-on-1-minute-bars label instead of terminal
  P&L. Reported out-of-time Sharpe 4.31-5.76 — **treat with real
  suspicion**, that magnitude is a red flag on its own, and their 0DTE
  microstructure is not directly comparable to our 7-day weekly holds.
  What's actually reusable: (1) rank the whole cross-section including a
  SKIP option rather than hand-picking a fixed baseline, (2) score against
  a path-aware risk-adjusted label rather than terminal P&L only. Point of
  origin for Experiment 23's design (testing Sortino/CVaR rather than mean
  P&L as the H4 evaluation metric).

## Statistical methodology (not empirical claims — tools used throughout)

- **Diebold, F. & Mariano, R. (1995), predictive accuracy test.** Standard
  pairwise forecast comparison test with HAC (Newey-West) correction for
  autocorrelated loss differentials. Used throughout Experiments 14/18/19/22.
  Calibrated against synthetic known cases (obviously-better series,
  identical series) before trusting on real output.

- **Hansen, P., Lunde, A. & Nason, J. (2011), "The Model Confidence Set,"
  Econometrica.** Block-bootstrap elimination procedure for comparing
  multiple forecasts at once without inflating false-positive risk from
  repeated pairwise tests. Used in Experiments 14/18/22.

## Performance measurement / Sharpe ratio audit (Experiment 29)

- **Bailey, D. & López de Prado, M. (2014), "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting, and Non-Normality,"
  Journal of Portfolio Management.**
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551 ,
  https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
  Basis for `pipeline/falsify/deflated_sharpe.py`'s DSR: corrects a Sharpe
  ratio for the number of trials tried (this project's own numbered
  `EXPERIMENT.md` ledger supplies a truthful N) and for non-normal
  (skewed/fat-tailed) returns, which weekly options P&L is not exempt from.
  Result: DSR ≈ 0.20 at N=30 -- not statistically distinguishable from a
  lucky draw among 30 tries.

- **Bailey, D. & López de Prado, M. (2012), "The Sharpe Ratio Efficient
  Frontier."** https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf
  Source of the Probabilistic Sharpe Ratio and Minimum Track Record Length
  (MinTRL), both implemented in `deflated_sharpe.py`. MinTRL result: ~932
  weeks (17.9 years) of data would be needed to prove this strategy's
  Sharpe exceeds zero at 95% confidence, against 10.3 years available --
  a direct consequence of the strategy's own extreme negative skew and
  kurtosis (an insurance-shaped payoff is inherently hard to prove with a
  ratio built for symmetric returns).

- **Goetzmann, W., Ingersoll, J., Spiegel, M. & Welch, I. (2007),
  "Portfolio Performance Manipulation and Manipulation-Proof Performance
  Measures," Review of Financial Studies.**
  https://www.ivo-welch.info/research/journalcopy/2007-rfs.pdf
  Proves Sharpe-like measures are gameable by option-like payoffs almost by
  construction, and derives the Manipulation-Proof Performance Measure
  (MPPM) as the alternative that isn't -- basis for `pipeline/falsify/
  mppm.py`. Used as an independent, non-gameable cross-check on this
  project's own DSR result: MPPM (+0.87%/yr, stable across risk aversion
  2-5) independently reproduces `EXPERIMENT.md` 12d's "insurance, not an
  edge" finding for the term-structure filter, and shows the strategy
  loses to plain SPY buy-and-hold once risk-matched to the same volatility.

- **Cboe S&P 500 PutWrite Indices Methodology.**
  https://cdn.cboe.com/api/global/us_indices/governance/Cboe_SP_500_PutWrite_Indices_Methodology.pdf
  The reference convention this project adopted for how uninvested
  collateral is treated in a return series: "fully collateralized," with
  the collateral "invested at the 1- and 3-month Treasury Bill rate" every
  day, traded or not. Fixed a real bug in `pipeline/falsify/equity_sim.py`
  (collateral credited zero interest on traded weeks while the Sharpe
  benchmark still assumed it earned the full rate -- see
  `EXPERIMENT_29_SHARPE_AUDIT.md` for the full account) and is now that
  module's pinned, documented convention.

- **"Life at Sharpe's End"** (notional funding and the Sharpe-ratio
  denominator ambiguity in derivatives strategies).
  https://www.premiacap.com/publications/RR_0901.pdf
  Names the general failure mode Experiment 29's bug turned out to be an
  instance of: a strategy's stated return depends entirely on what capital
  base you assume it's funded against, and that assumption is a choice,
  not a fact -- "returns can be arbitrarily restated to any number of
  levels."

- **Israelov, R. & Tummala, H., "Which Index Options Should You Sell?"**
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2990542 , and
  **Israelov, R. & Nielsen, L., "Covered Calls Uncovered," Financial
  Analysts Journal (2015).**
  https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/Covered-Calls-Uncovered.pdf
  Background on index option-selling return decomposition and risk
  attribution; context for interpreting this strategy's own volatility
  risk premium harvest.

- **Israelov, R., "Pathetic Protection," Journal of Alternative Investments
  (2019).**
  https://images.aqr.com/-/media/AQR/Documents/Journal-Articles/Pathetic-Protection-JAI-Wint19.pdf
  On tail-hedge cost and the standalone-Sharpe trap of judging insurance-shaped
  payoffs by ordinary risk-adjusted metrics -- same underlying issue
  Experiment 29's MinTRL section surfaces on the short side of this
  strategy's payoff.

- **Lo, A. (2002), "The Statistics of Sharpe Ratios," Financial Analysts
  Journal.** Standard error of the Sharpe ratio estimator under non-IID,
  non-normal returns (the Mertens 2002 correction `sharpe_se()` implements
  is the direct descendant of this result).

- **Pezier, J. & White, A. (2006), Adjusted Sharpe Ratio.** Penalizes
  negative skewness and excess kurtosis directly; cited as further context
  for why plain Sharpe misprices a strategy shaped like this one, alongside
  the DSR and MPPM approaches actually implemented here.
