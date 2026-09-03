# Submission checklist -- what's left before Fri Sep 4, 2026

Written as a standalone file rather than added to PROGRESS.md directly, since
this session doesn't own that file's edits right now. Fold the unchecked items
into PROGRESS.md's own "tick only when verified" list when convenient -- don't
tick anything here just by writing it down.

Refreshed 2026-09-03 (fourth pass, this session): several items below were
resolved by pushed commits since the third refresh (32d975c), including one
NOT previously tracked here at all -- CI had been failing on GitHub since at
least ca626d6 and nobody had checked. Corrected against the actual repo state
and a real GitHub Actions run, not just local pytest.

## Resolved since the last refresh

- [x] **WRITEUP.md exists and is committed.** The literal top-of-list Thursday
      deliverable. Was caught by the same blanket `*.md` gitignore rule that
      hid `EXPERIMENT_28_VRP.md`/`SUBMISSION_CHECKLIST.md`/three CSVs earlier
      -- found during a stress-test pass and fixed same-day (`2fa0305`).
      2,633 words: falsification audit as the lead, positioning, features,
      architecture, Alpaca infrastructure, performance table, the H1-H5
      experiment ladder, limitations, reproduce-it commands. Every figure in
      it re-verified against a live `python -m pipeline.falsify.audit` run,
      not copied from conversation history, and independently re-verified
      again by a second session against `EXPERIMENT.md`/README.md
      cross-references. No em dashes (project style rule).
- [x] **The three deferred citations are in.** Bakshi & Kapadia (2003), Carr
      & Wu (2009), CBOE PUT index -- added to `SOURCES.md` as a new
      "Volatility risk premium (options-selling economic prior)" section,
      committed and pushed (`280c124`). Includes the same "this is the prior,
      not evidence for this specific strategy, different instrument and
      horizon" caveat this project holds itself to elsewhere.
- [x] **README's DSR/trial-count figures updated for N=30 -> 31.** Done
      (`e563f96`) before this pass started; confirmed still current.
- [x] **Four README figures with no source, now sourced and corrected.**
      "77%" -> 74.8%/dashboard's own 75%, "43%" -> 41.1%, and most
      importantly "p = 0.03" -> the actual **p = 0.10** (2018 has 5 losing
      weeks, not 8; 0.627^5, not 0.627^8). The old 8-loser count was traced to
      a superseded $1-strike reconstruction. README now states the weaker,
      honest conclusion outright rather than just swapping the number
      (`15d2be5`).
- [x] **NEW, not previously tracked here: CI was failing on every push,
      GitHub Actions confirmed, not just "unconfirmed."** `numpy==2.5.2`,
      `scipy==1.18.0`, and `xgboost==3.4.1` were pinned against what installs
      on this project's Python 3.14 dev machines; all three require Python
      >=3.12 and CI deliberately runs 3.11 to match the devcontainer. Every
      push since at least `ca626d6` had been failing at the install step,
      before ever reaching `pytest`. Reproduced the exact failure with a real
      Python 3.11.16 interpreter (not just a YAML version string), fixed the
      three pins to the highest version each package publishes for 3.11
      (`numpy==2.4.6`, `scipy==1.17.1`, `xgboost==3.2.0`), verified 64/64
      passing in that exact environment before pushing, then **watched the
      real GitHub Actions run go green** (`34983d1`, run `33705111112`,
      1m10s). This is the first genuinely confirmed-green run this project
      has had.
- [x] **`run_all.py`'s import-time side effect fixed.** Importing the module
      (not calling anything) used to trigger a live 40-symbol Alpaca refetch
      and a full model retrain, the same class of bug `a3f4aa7` fixed in
      `extract.py`. Found live during a sweep, fixed with the same guard
      pattern, confirmed via AST inspection that zero module-level calls
      remain.
- [x] **`requests` pinned in requirements.txt** (`fa63718`) -- was imported
      directly by `pipeline/data/vix.py`, previously present only
      transitively.
- [x] **`.env.example` committed and readable**, ML figures re-run against
      corrected data (Experiment 30), README lines 29/43/49 replacement
      landed, reproducibility CSVs committed, `tests/`/`.github/` committed
      for the first time -- all confirmed still current from the prior pass,
      re-verified against a fresh clone this pass (64 fast tests, 13 slow,
      all passing, before the CI fix above was even needed to add stock-6c's
      new engine.py/test_engine.py work in progress, which brought the fast
      count to 74 -- see "Reference" below).
- [x] **"14 Guards" text fixed to 15 in `reviewer.py`'s live prompt**
      (`e8db5f8`) -- `guards.py` has 15 `check_*` functions, matching the
      real audit log's `guards_checked: 15`; the Reviewer's own prompt was
      the one place still saying 14. A factual error inside text a live LLM
      reads, not just a doc typo.

## Still open

- [ ] **Get a few more real, timestamped entries into
      `pipeline/audit/log.py`'s `decisions.jsonl`** during actual market
      sessions before Friday. Currently 7 rows (was 4 two passes ago, so
      this is progressing) -- not independently re-verified which are real
      trading-session decisions vs. guard-blocked bounces this pass.
- [ ] **Fold `EXPERIMENT_28_VRP.md` into `EXPERIMENT.md`** as a numbered
      Experiment 28. Checked this pass: still no `## Experiment 28` heading
      in `EXPERIMENT.md`, so this has not happened. Lower priority now that
      `WRITEUP.md` links `EXPERIMENT_28_VRP.md` directly and it is committed
      either way.
- [ ] **"Move Experiment 21 to the top of README.md"** -- checked this pass:
      the regime-split validation gate and false-trip test (Experiment 21's
      substance) are present under "The two things here that are actually
      unusual," not literally at the top. Given `WRITEUP.md` now exists and
      leads with the falsification audit instead, whether this still matters
      for README specifically is a call for whoever owns that file next.
- [ ] **Double-check `.env` never ends up in a zip export, screen share, or
      Codespaces snapshot** shown to a judge. `scripts/security_preflight.py`
      confirms untracked/out of git history on every run (and now runs
      cleanly from a fresh clone, per the earlier `.env.example` fix), but
      the file still sits in plaintext in the project root on disk. Not
      re-verified this pass.
- [ ] **`pipeline.risk.false_trip` needs Alpaca credentials to run**, so a
      judge cannot reproduce the false-trip test directly. Agreed workaround
      unchanged: cite `track_record.json`'s artifact (20.3%, 25/123) instead
      of the command. Not this session's fix to make.
- [ ] **W3 (LLM proposes hypotheses, the falsification engine kills them) is
      in progress**, not done -- `pipeline/falsify/engine.py` and
      `tests/test_engine.py` appeared as untracked files during this pass
      (10 new passing tests, fast suite now 74). Not this session's work;
      do not describe it as finished anywhere, and note it will move the
      DSR's trial count N again once it lands, per `trial_count.py`'s own
      counting rule.

## Reference: what actually ships as of `34983d1`

- **`WRITEUP.md`** at repo root -- the submission document itself.
- **CI is green** (`.github/workflows/tests.yml`, confirmed via a real
  GitHub Actions run, not just local pytest) on Python 3.11, no secrets.
- **Tests**: 74 fast (`pytest tests/`, includes stock-6c's new W3 engine
  tests) + 13 slow (`pytest tests/ -m slow`, reproduces every published
  figure in `EXPERIMENT_29_SHARPE_AUDIT.md` end to end). All passing from a
  genuinely fresh clone, fresh venv, no `.env`.
- **`pipeline/falsify/`** (Experiment 29): Deflated Sharpe Ratio, Minimum
  Track Record Length, a bootstrap SE diagnostic, and a manipulation-proof
  performance measure. Current headline: Sharpe +0.574 (single position) /
  +0.563 (2 concurrent), **DSR = 0.20 at N = 31**.
- **`pipeline/backtest/vrp_measure.py`** / **`EXPERIMENT_28_VRP.md`**:
  Experiment 28's analysis, committed and runnable, not yet folded into
  `EXPERIMENT.md`'s own numbering (see "Still open" above).
- **`SOURCES.md`**: all citations from both halves of the split now present.
- **Reproduce it**: `pip install -r requirements.txt && pytest tests/ -q`
  now genuinely works from a bare clone on the Python version CI actually
  runs, which was not true before this pass.
