# Submission checklist -- what's left before Fri Sep 4, 2026

Written as a standalone file rather than added to PROGRESS.md directly, since
this session doesn't own that file's edits right now. Fold the unchecked items
into PROGRESS.md's own "tick only when verified" list when convenient -- don't
tick anything here just by writing it down.

Refreshed 2026-09-02 (twice today): several items below were overtaken by
other sessions' work since this file was first written. Corrected against
the actual repo state rather than left stale -- a checklist that claims
outstanding work already done is worse than no checklist.

- [ ] **NEW TOP BLOCKING ITEM (found 2026-09-02 while verifying Experiment 29's
      own reproducibility claim): commit `output/data/raw_SPY_long.csv`,
      `vix9d.csv`, and `vix3m.csv`.** `.gitignore`'s blanket `output/data/*.csv`
      rule silently caught all three (same failure mode that earlier hid
      `EXPERIMENT_21_VRP.md` and this very file). Every command this project
      tells a judge to run for the 2016-2026 reconstruction track --
      `python -m pipeline.backtest.reconstruct`, `python -m
      pipeline.backtest.vrp_measure`, `python -m pipeline.falsify.audit` --
      calls `reconstruct.replay()`, which needs all three. **On a fresh clone
      today, every one of those commands fails with `FileNotFoundError`,
      contradicting their own "no network, no credentials" claims.**
      `.gitignore` already has the allow-list exceptions added (this session);
      the files themselves (48-72KB total, public market data, no secrets --
      same category as the already-tracked `vix.csv`) still need `git add` and
      a commit. This session does not commit; needs the user or another
      session to do it. **Do this before anything else on this list** -- every
      other reconstruction-track reproducibility claim depends on it.
- [x] **`pipeline/vol/` and `pipeline/vol_extract.py` are committed.**
      Confirmed via `git ls-files pipeline/vol/` (27 tracked files). This was
      the top blocking item; it is resolved.
- [ ] **Commit and push this session's work**, coordinated with whoever else
      is mid-edit. As of this writing: `pipeline/extract.py` (split/dividend
      adjustment fix), `pipeline/backtest/reconstruct.py`, `requirements.txt`
      modified; `.env.example`, `pipeline/backtest/vrp_measure.py`, `scripts/`,
      `tests/`, `.github/workflows/`, `EXPERIMENT_28_VRP.md` (renamed from
      `EXPERIMENT_21_VRP.md` -- see below) untracked. `README.md` also has
      uncommitted edits from another session (broken-link fix) -- do not push
      over it without checking.
- [ ] **Confirm CI is green on the pushed commit**, not just passing locally.
      `.github/workflows/tests.yml` runs `pytest tests/ -q` on every push with
      no secrets configured, proving the suite needs no API keys. Check the
      Actions tab after pushing.
- [x] ~~Verify the Streamlit deploy loads for a stranger~~ -- **superseded.**
      The public dashboard moved to a static site on Vercel (`public/`) with a
      serverless read-only Alpaca proxy (`api/account.py`), not Streamlit
      Cloud. Re-verify *that* deploy loads cold instead: open it in a private
      window with no logged-in session.
- [ ] **Get a few real, timestamped entries into `pipeline/audit/log.py`'s
      `decisions.jsonl`** during actual market sessions before Friday.
      Partially underway: the account has 2 real orders so far (2026-09-01),
      0 before the hackathon's Aug 28 start. Keep going -- more real logged
      decisions strengthens the "proof of live execution" story this project
      is otherwise ahead on.
- [ ] **Move Experiment 21 (the randomization null / reconstruction-gate
      story) to the top of README.md**, ahead of the 40-stock ML failure.
      Still the project's strongest, most specific evidence of rigor, still
      several paragraphs deep as of this writing.
- [ ] **Fold `EXPERIMENT_28_VRP.md` into `EXPERIMENT.md`** once the other
      session's in-progress edits to that file land, numbered as **Experiment
      28**, not 21 -- that number was already taken by EXPERIMENT.md's own
      "Experiment 21, Randomization null for the week-skip filter." This file
      was renamed from `EXPERIMENT_21_VRP.md` to fix the collision; the
      `.gitignore` allow-list entry was updated to match.
- [ ] **Add the deferred citations** (Bakshi & Kapadia 2003, Carr & Wu 2009,
      CBOE PUT index) to the "published research on volatility selling"
      reference in README.md -- deliberately last, per the decision to
      implement first and cite after. (Split with the write-up session:
      they're taking these three; this session already added Bailey &
      López de Prado 2014/2012, Goetzmann et al. 2007, and the CBOE
      PutWrite methodology doc to `SOURCES.md`.)
- [ ] **Hand `README.md` lines 29/43/49 (the Sharpe 0.35/0.24, 4.4%/yr, 5.8%
      drawdown figures) paste-ready replacement text.** This session found
      and fixed a real bug in its own Sharpe reproduction (see
      `EXPERIMENT_29_SHARPE_AUDIT.md`) that independently corroborates
      most of README's existing numbers (vol and max drawdown both match
      within noise once corrected) -- but a residual gap remains on annual
      return (4.83% reproduced vs 3.56% in `EXPERIMENT.md` 12d) that is
      still being investigated before the replacement text is sent. Do not
      edit those lines directly -- coordinated with the sessions that own
      `README.md` (stock-4f) and the write-up (stock-66); both are holding
      those lines until this session's text arrives.
- [ ] **Double-check `.env` never ends up in a zip export, screen share, or
      Codespaces snapshot** shown to a judge. Confirmed untracked and out of
      git history (`scripts/security_preflight.py` checks this on every run),
      but it still sits in plaintext in the project root on disk.
- [ ] **Update `raw_*.csv`-derived ML figures once `pipeline.run_all` is
      re-run.** The 40-stock price data was found not split-adjusted (a 10:1
      NVDA split, 20:1 GOOGL/AMZN, 4:1 AAPL all read as fake ~-90% crash
      days), fixed in `pipeline/extract.py`
      (`adjustment=Adjustment.ALL`), and the 40 symbols refetched -- but the
      ML experiments that consumed the old data have not been re-run. The
      published figures **-0.457% per 5 days** and **t = -3.12** (in
      `README.md` and `EXPERIMENT.md`) describe the contaminated inputs and
      will change. `pipeline/model/` is unowned by any connected session as
      of this writing, so this needs to be assigned before Friday.

## Already done this session (verify these survived the push, nothing more)

- `tests/`: **64 fast tests** (`pytest tests/`, ~1.5-2s, no API keys, no
  network) covering the split/dividend-adjustment guard, the VRP/reconstruct
  math, and the full `pipeline/falsify/` module (Deflated Sharpe Ratio,
  MinTRL, bootstrap SE, MPPM, position sizing incl. the collateral fix
  below) -- plus **12 slow tests** (`pytest tests/ -m slow`, ~17-19s,
  excluded from the default run via `pyproject.toml`'s
  `[tool.pytest.ini_options]`) that reproduce `pipeline/falsify/audit.py`'s
  published figures end to end, including a 2026-09-03 pass that found and
  closed 3 more untested-but-correct claims (skew/kurtosis, the bootstrap
  CI, the monthly/quarterly aggregation table).
- `.env.example` and `scripts/security_preflight.py`.
- **`pipeline/falsify/`** (Experiment 29 -- Deflated Sharpe Ratio audit):
  found and fixed a real bug in its own first version (uninvested
  collateral credited zero interest while the Sharpe benchmark still
  assumed the full cash rate), documented with sources
  (`EXPERIMENT_29_SHARPE_AUDIT.md`, `.gitignore` allow-list exception
  added). Corrected result: Sharpe +0.574 (single position) / +0.563 (2
  concurrent, corroborating `EXPERIMENT.md` 12d's vol and README's max
  drawdown within noise), DSR = 0.205 at N=30. Four hypothesis tests on
  whether any remedy makes it statistically provable: two rejected
  (bootstrap SE, monthly/quarterly aggregation), two adopted (a
  non-gameable performance measure, publishing DSR as a curve over N).
  `python -m pipeline.falsify.audit` reproduces every figure in one
  command, no credentials/network, byte-identical across runs.
- `pipeline/backtest/vrp_measure.py`: Experiment 28's analysis (renumbered
  from 21), runnable via `python -m pipeline.backtest.vrp_measure`.
- `EXPERIMENT_28_VRP.md`: the full writeup (renamed from
  `EXPERIMENT_21_VRP.md` to resolve a numbering collision -- see above),
  including the equity-curve comparison and false-trip test that led to
  rejecting `vrp_edge` as a live filter despite it beating the existing
  filter on raw total P&L.
- `.github/workflows/tests.yml`: CI running the offline test suite on every
  push, no secrets required.
- `pipeline/extract.py`: fixed to fetch with `Adjustment.ALL` instead of no
  adjustment at all, plus a permanent `assert_no_split_artifacts` guard that
  raises on any single-day move beyond 50% (catches both ordinary splits and
  the one surprise this fix turned up -- Alpaca's SPLIT-only adjustment
  applying an incorrect 2x rescale to HON around its June 2026 Aerospace
  spinoff, which ALL avoids). `output/data/raw_*.csv` refetched for all 39
  non-SPY symbols; `raw_SPY.csv` deliberately untouched (confirmed
  byte-identical by hash) since it feeds the options evidence base and has
  never needed adjustment (no SPY splits exist).
