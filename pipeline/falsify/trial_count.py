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
"""

from __future__ import annotations

import os

# Pinned 2026-09-02 by counting EXPERIMENT.md's distinct numbered headings:
# Experiments 0, 1, 2, 2b, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
# 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27 -- 29 distinct experiments.
# (13 appears as two sub-entries, "Step 0" and "Test 13a"; counted once,
# since both are the same numbered experiment, not two different ones.)
# Verified: `grep -c '^#\+ Experiment ' EXPERIMENT.md` returns 31 -- that
# raw count double-counts Experiment 13's two headings and includes one
# malformed bare "# Experiment " title-page heading that isn't a numbered
# entry at all; 31 - 2 = 29 matches the manual count above exactly.
EXPERIMENT_MD_BASE_COUNT = 29

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
