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
