# Submission checklist -- what's left before Fri Sep 4, 2026

Written as a standalone file rather than added to PROGRESS.md directly, since
this session doesn't own that file's edits right now. Fold the unchecked items
into PROGRESS.md's own "tick only when verified" list when convenient -- don't
tick anything here just by writing it down.

Refreshed 2026-09-03 (third pass): flagged as stale by a peer session's
review -- several items below had already been resolved by pushed commits
(15249a8) but were still shown as open. Corrected against the actual repo
state rather than left stale -- a checklist that claims outstanding work
already done is worse than no checklist.

## Resolved since the last refresh

- [x] **Reproducibility data files committed.** `raw_SPY_long.csv`,
      `vix9d.csv`, `vix3m.csv` are in `HEAD` (`249a93e`). Confirmed via a
      genuinely fresh clone + fresh venv + no `.env`, by two independent
      sessions: `python -m pipeline.falsify.audit`,
      `python -m pipeline.backtest.reconstruct`,
      `python -m pipeline.backtest.vrp_measure` all run clean.
- [x] **`pipeline/vol/` and `pipeline/vol_extract.py` are committed.**
      Confirmed via `git ls-files pipeline/vol/` (27 tracked files).
- [x] **This session's work is committed and pushed.** `origin/main` is at
      `15249a8` (confirmed via `git fetch` + `git log -1 origin/main`),
      8 commits: `pipeline/falsify/` (Experiment 29), `tests/` (committed
      for the first time, ever), `.github/workflows/`,
      `pipeline/backtest/vrp_measure.py`, `EXPERIMENT_28_VRP.md`,
      `pipeline/extract.py`'s import-time-credential-crash fix, plus
      stock-4f's ML re-verification (Experiment 30).
- [x] **`.env.example` committed and readable.** Was also silently caught
      by `.gitignore`'s blanket `.env*` rule (same failure mode as the CSVs
      above) -- `scripts/security_preflight.py` crashed on a fresh clone
      trying to read it. Fixed (`e839791`); confirmed passing on a fresh
      clone by a peer session.
- [x] **Citations split with the write-up session**, my half done: Bailey
      & López de Prado 2014/2012, Goetzmann et al. 2007, and the CBOE
      PutWrite methodology doc are in `SOURCES.md`. stock-66's three
      (Bakshi & Kapadia 2003, Carr & Wu 2009, CBOE PUT index) are still
      outstanding -- theirs to add, not blocked on anything here.
- [x] **README.md lines 29/43/49 replacement text delivered and applied**
      (stock-4f, commits `81abe8a`/`9a9dffc`). Includes a real correction
      caught mid-flight: the first draft I sent had an uncomputed "0.49
      unfiltered Sharpe" (true value 0.350) and a wrong "4x smaller
      drawdown" (true ~3x) -- caught, fixed, independently re-derived by
      stock-4f before applying. Full account in `PROGRESS.md`'s "Notes and
      failures".
- [x] **ML figures re-run against corrected data** (stock-4f, Experiment
      30, commit `15249a8`). The `-0.457%`/`t=-3.12` figures this item used
      to flag are superseded; re-run confirmed the null-signal conclusion
      holds (t=-0.27 to -0.35) even on corrected data.

## Still open

- [ ] **README's DSR/trial-count figures need updating: N moved 30 -> 31.**
      Experiment 30 landing (above) increments this project's own trial
      count -- see `pipeline/falsify/trial_count.py`'s docstring for why
      that one counts as a trial and Experiment 29's own collateral-bug fix
      doesn't. Paste-ready replacement text for README's two "N=30"
      references prepared and ready to send; headline DSR values move
      0.205->0.201 (variant B) / 0.200->0.197 (variant C), small moves,
      same conclusion. `EXPERIMENT_29_SHARPE_AUDIT.md` and
      `pipeline/falsify/audit.py` already updated and pushed (`ca626d6`).
- [ ] **Four README figures flagged by stock-66 with no source in the
      repo, not this session's area:** "cut the worst drawdown by 77%"
      (stock-66 computed 74.8%; `track_record.json`'s own
      `equity_headline` says 75% -- README and the live dashboard
      disagree publicly), "2018 lost 43% of the decade" (actual 41.1%),
      "skipping 63%", and "p = 0.03". Flagging for whoever owns that
      section of README -- outside `pipeline/falsify/`, `pipeline/backtest/`,
      `tests/`.
- [ ] **Confirm CI is actually green on GitHub**, not just passing
      locally/on a scratch clone. Could not check from here --
      `gh run list` fails with "no GitHub remote configured" in this
      working copy. Someone with the actual GitHub remote/auth needs to
      check the Actions tab on `15249a8`.
- [ ] **Get a few more real, timestamped entries into
      `pipeline/audit/log.py`'s `decisions.jsonl`** during actual market
      sessions before Friday. Not re-verified this pass.
- [ ] **Move Experiment 21 (the randomization null / reconstruction-gate
      story) to the top of README.md**, ahead of the 40-stock ML section.
      Not re-verified this pass whether this happened.
- [ ] **Fold `EXPERIMENT_28_VRP.md` into `EXPERIMENT.md`** as Experiment
      28. Checked this pass: `EXPERIMENT.md` still has no "## Experiment
      28" heading, so this has not happened yet.
- [ ] **Double-check `.env` never ends up in a zip export, screen share,
      or Codespaces snapshot** shown to a judge. `security_preflight.py`
      confirms it's untracked/out of history on every run, but it still
      sits in plaintext in the project root on disk. Not re-verified this
      pass.
- [ ] **`pipeline.risk.false_trip` needs Alpaca credentials to run**, so a
      judge cannot re-run the false-trip test directly (found by stock-66's
      fresh-clone check). Not `pipeline/falsify/`'s territory to fix;
      citing `track_record.json`'s artifact instead is the agreed
      workaround.

## Reference: what `pipeline/falsify/` (Experiment 29) actually is, current as of `ca626d6`

- `tests/`: **64 fast tests** (`pytest tests/`, ~1.5-2s, no API keys, no
  network) + **13 slow tests** (`pytest tests/ -m slow`, ~17-19s, excluded
  from the default run via `pyproject.toml`'s `[tool.pytest.ini_options]`)
  that reproduce `pipeline/falsify/audit.py`'s published figures end to
  end. Verified passing on a genuinely fresh clone + fresh venv + no
  `.env`, independently, twice.
- **`pipeline/falsify/`**: Deflated Sharpe Ratio, Minimum Track Record
  Length, a bootstrap SE diagnostic, and a manipulation-proof performance
  measure (Goetzmann et al. 2007), all reproducible via
  `python -m pipeline.falsify.audit` (no credentials/network,
  byte-identical across runs). Found and fixed a real bug in its own first
  version (collateral crediting was asymmetric with the Sharpe benchmark).
  Current headline: Sharpe +0.574 (single position) / +0.563 (2
  concurrent, corroborating `EXPERIMENT.md` 12d's vol and README's max
  drawdown within noise), **DSR = 0.201 at N=31**. Four hypothesis tests on
  whether any remedy makes it statistically provable: two rejected
  (bootstrap SE, monthly/quarterly aggregation), two adopted (the
  non-gameable measure, publishing DSR as a curve over N).
- `pipeline/backtest/vrp_measure.py`: Experiment 28's analysis (renumbered
  from 21), runnable via `python -m pipeline.backtest.vrp_measure`.
- `EXPERIMENT_28_VRP.md`: the full writeup (renamed from
  `EXPERIMENT_21_VRP.md` to resolve a numbering collision), including the
  equity-curve comparison and false-trip test that led to rejecting
  `vrp_edge` as a live filter despite it beating the existing filter on
  raw total P&L.
- `.github/workflows/tests.yml`: CI running the offline test suite on every
  push, no secrets required (local pass confirmed; GitHub Actions status
  not independently confirmed -- see "Still open" above).
- `pipeline/extract.py`: fixed to fetch with `Adjustment.ALL` instead of no
  adjustment at all, plus a permanent `assert_no_split_artifacts` guard;
  also fixed to build its live Alpaca client inside `fetch_and_save()`
  rather than at module-import time, which used to crash test collection
  on any machine without a `.env` file.
