"""
The honest trial count N the Deflated Sharpe Ratio divides by. Computed,
never hardcoded as a single bare number, because staleness here defeats
the entire point of publishing a DSR: any figure derived from N is only as
honest as N itself, and N changes every time a new hypothesis is tested
against this project's data.

N = EXPERIMENT_MD_BASE_COUNT (pinned below, from EXPERIMENT.md's own
    numbered headings)
  + 1  (Experiment 28, EXPERIMENT_28_VRP.md -- renumbered from a collision
        with EXPERIMENT.md's own Experiment 21; not yet folded into
        EXPERIMENT.md itself, so not counted by the grep below)
  + len(hypotheses ledger)  (every hypothesis a future W3 LLM-proposal loop
        tests against this data; 0 until that ledger exists)

Any DSR figure that leaves this repo (a pitch, a slide, a comment reply)
must be regenerated after the most recent trial and quoted with the N it
was computed at ("DSR = x at N = y"), never as a bare number -- see this
session's plan file, W2's "trap" note.

WHAT COUNTS AS A TRIAL, decided by one question: could this have been
reported as THE result had it come out well? Two precedents, both real,
both landed the same week, opposite answers:

  - Experiment 29's own collateral-accounting bug fix (equity_sim.py,
    2026-09-02) does NOT count. Fixing an asymmetric cash-crediting error
    is a deterministic correction with one right answer -- there was
    never a world where "computing it correctly" could have come out two
    different ways depending on new information. No new draw happened;
    an existing draw was mis-transcribed and then correctly transcribed.

  - Experiment 30 (EXPERIMENT.md, 2026-09-03) DOES count. It re-ran
    Experiments 8/9/10's exact methodology against corrected raw price
    data (the split-adjustment fix) -- a genuinely different input, with
    a genuinely uncertain outcome beforehand: mean_ic flipped sign in
    both re-run variants and both t-stats moved substantially toward
    significance (-0.73->-0.35, -1.13->-0.27), i.e. this could
    plausibly have crossed the |t|=2.0 bar and been reported as a real
    signal. It happened not to. That it COULD have is exactly what makes
    it a trial, not a bug fix, even though the underlying hypothesis
    ("does this feature set carry cross-sectional signal") was already
    on the ledger.

  The distinguishing test: does the correction have a single knowable
  right answer that fixing merely reveals (not a trial), or does it
  require a fresh statistical draw against changed evidence whose result
  could not be known in advance (a trial)? A bug in the SCORING of a
  fixed outcome is the former; a bug in the DATA feeding a live
  statistical test is the latter.
"""

from __future__ import annotations

import os

# Pinned 2026-09-03 (revised from 29 on 2026-09-02) by counting
# EXPERIMENT.md's distinct numbered headings: Experiments 0, 1, 2, 2b, 3,
# 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
# 24, 25, 26, 27, 30 -- 30 distinct experiments (Experiment 30 added
# 2026-09-03, see the module docstring's precedent discussion above for
# why it counts).
# (13 appears as two sub-entries, "Step 0" and "Test 13a"; counted once,
# since both are the same numbered experiment, not two different ones.)
# Verified: `grep -c '^#\+ Experiment ' EXPERIMENT.md` returns 32 -- that
# raw count double-counts Experiment 13's two headings and includes one
# malformed bare "# Experiment " title-page heading that isn't a numbered
# entry at all; 32 - 2 = 30 matches the manual count above exactly.
EXPERIMENT_MD_BASE_COUNT = 30

EXPERIMENT_28_COUNT = 1  # EXPERIMENT_28_VRP.md, standalone pending fold-in

HYPOTHESES_LEDGER_PATH = "output/falsify/hypotheses.jsonl"


def hypotheses_ledger_count(path: str = HYPOTHESES_LEDGER_PATH) -> int:
    """Number of lines in the (append-only) hypotheses ledger a future
    W3 LLM-proposal loop writes to -- one line per hypothesis tested, so
    the count IS the increment to N. 0 if the file doesn't exist yet
    (nothing has been proposed), never an error -- matching this
    project's standing cold-start convention (pipeline/audit/log.py)."""
    if not os.path.exists(path):
        return 0
    with open(path) as f:
        return sum(1 for line in f if line.strip())


def total_trial_count(ledger_path: str = HYPOTHESES_LEDGER_PATH) -> int:
    """The N to divide by, computed fresh every call -- never cache this
    across a process that might also be appending to the ledger."""
    return EXPERIMENT_MD_BASE_COUNT + EXPERIMENT_28_COUNT + hypotheses_ledger_count(ledger_path)
