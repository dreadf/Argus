"""
W3: an LLM (Gemini) proposes a falsifiable hypothesis, pipeline.falsify.
engine.falsify() tries to kill it, the verdict -- including which stage
killed it and why -- goes back into the prompt, and the model proposes a
better one. Every attempt, killed or survived, is logged append-only to
output/falsify/hypotheses.jsonl, and that count feeds directly into
pipeline.falsify.trial_count.total_trial_count() (see
hypotheses_ledger_count() there): the whole point of this loop is that
every attempt costs something, the same discipline this project already
applies to its own manually-run experiments in EXPERIMENT.md.

Safety, stated plainly because this is the one module in the project that
lets an LLM's output steer what gets computed next:

  - The model NEVER supplies code, a formula, or anything that gets eval'd
    or exec'd. It picks a `signal_name` from a fixed, pre-registered menu
    (_SIGNAL_LIBRARY below, built once from real data by known, reviewed
    transforms) and a `percentile` (skip threshold, clamped to (0, 1)).
    That is the entire proposal shape. An unrecognized signal_name, an
    out-of-range percentile, or a malformed response all fail the
    iteration closed (logged as an error, loop continues to the next
    iteration) rather than being guessed at or coerced into something
    plausible.
  - MAX_ITERATIONS hard-caps how many times one run calls Gemini,
    regardless of what the model or the gauntlet says.
  - There is no path from here to an order. This module only ever reads
    pre-computed data, calls falsify(), and appends to a log file.

Reuses pipeline/reviewer/reviewer.py's pattern (client setup, ```-fence
JSON parsing, fail-closed on any network/parse error) without importing
from or editing that file -- reviewer.py gates live order review; this
module never touches an order and the two should stay independent.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from pipeline.falsify.engine import Hypothesis, falsify

PROPOSER_MODEL = "gemini-2.5-flash"
MAX_ITERATIONS = 5
HYPOTHESES_LOG_PATH = "output/falsify/hypotheses.jsonl"

# Pinned menu of _signal_library()'s keys -- lets a caller (e.g.
# mcp_tools.falsify()) validate a proposed signal_name against the real
# menu without needing real data loaded first, since load_real_data() is
# comparatively expensive (a full reconstruction replay). _signal_library
# asserts its own keys match this set, so the two can't silently drift.
SIGNAL_NAMES = (
    "contango", "contango_5w_mean", "vrp_edge", "vrp_edge_3w_mean",
    "vrp_edge_minus_contango", "vrp_edge_zscore_13w",
)


def _signal_library(data: pd.DataFrame) -> dict[str, pd.Series]:
    """The fixed, pre-registered menu of candidate skip-filter signals the
    model may choose from. `data` must be date-indexed with at least
    `vrp_edge`, `contango`, and `pnl` columns (vrp_measure.replay()'s
    shape, with add_filter_columns already run, is the intended real
    caller). Every entry here is a known, reviewed transform -- adding a
    new one is a code change, not something the model can do at runtime."""
    library = {
        "vrp_edge": data["vrp_edge"],
        "contango": data["contango"],
        "vrp_edge_minus_contango": data["vrp_edge"] - data["contango"],
        "vrp_edge_3w_mean": data["vrp_edge"].rolling(3, min_periods=1).mean(),
        "contango_5w_mean": data["contango"].rolling(5, min_periods=1).mean(),
        "vrp_edge_zscore_13w": (data["vrp_edge"] - data["vrp_edge"].rolling(13, min_periods=3).mean())
        / data["vrp_edge"].rolling(13, min_periods=3).std(),
    }
    assert set(library.keys()) == set(SIGNAL_NAMES), (
        "_signal_library's keys drifted from the pinned SIGNAL_NAMES menu -- "
        "update SIGNAL_NAMES too, it's what lets callers validate a proposed "
        "signal_name without needing real data loaded first"
    )
    return library


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_prompt(history: list[dict], available_signals: list[str]) -> str:
    history_text = "\n".join(
        f"  iteration {h['iteration']}: proposed {h['proposal'].get('signal_name')!r} "
        f"@ percentile={h['proposal'].get('percentile')} -> "
        f"{'ERROR: ' + h['error'] if h['error'] else ('SURVIVED' if h['verdict']['survived'] else 'KILLED at ' + str(h['verdict']['killed_at']))}"
        f"{': ' + h['verdict']['reason'] if h['verdict'] else ''}"
        for h in history
    ) or "  (none yet -- this is the first iteration)"

    return f"""You are proposing a falsifiable trading hypothesis about whether a candidate signal, used as a walk-forward SKIP FILTER on a weekly options-selling strategy, actually improves realized P&L -- not guessing, testing.

You may choose ONLY from this pre-registered menu of signals (you cannot invent a new one or supply a formula):
{json.dumps(available_signals, indent=2)}

You also choose a `percentile` in (0, 1): weeks where the signal falls below its own trailing `percentile`-quantile (computed walk-forward, no lookahead) get skipped.

Your proposal will be run through a falsification gauntlet: a false-trip check against real historical winning weeks, a randomization null (2000 shuffles of the signal), and a Deflated Sharpe Ratio at this project's current trial count. It will be KILLED at the first stage it fails, and you will be told which stage and why.

History of what you and this gauntlet have already found this run:
{history_text}

Propose the single most promising untried (or worth-refining) combination, given everything above. Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"signal_name": "<one of the menu names above>", "percentile": <number strictly between 0 and 1>, "reason": "<one sentence, why this one, given the history>"}}
"""


def call_gemini_proposer(history: list[dict], available_signals: list[str],
                          client: "object | None" = None) -> dict:
    """Real network call to Gemini. `client` is injectable so run_loop's
    logging/looping/safety logic can be tested without a network
    dependency -- this function is the only part of the module that
    isn't unit-tested against a live API (matches reviewer.py's own
    call_gemini_reviewer split)."""
    from google import genai

    if client is None:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = _build_prompt(history, available_signals)
    response = client.models.generate_content(model=PROPOSER_MODEL, contents=prompt)
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1]
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"error": f"unparseable proposer response: {text[:200]!r}"}
    return parsed


def _validate_proposal(proposal: dict, available_signals: list[str]) -> Optional[str]:
    """Returns an error string if `proposal` is unsafe/malformed, else
    None. The only gate between whatever the model said and code actually
    running -- mirrors reviewer.py's apply_reviewer_decision in spirit:
    never trust the model's output structurally."""
    if "error" in proposal:
        return proposal["error"]
    signal_name = proposal.get("signal_name")
    if signal_name not in available_signals:
        return f"signal_name {signal_name!r} is not in the pre-registered menu {available_signals}"
    percentile = proposal.get("percentile")
    try:
        percentile = float(percentile)
    except (TypeError, ValueError):
        return f"percentile {proposal.get('percentile')!r} is not a number"
    if not (0.0 < percentile < 1.0):
        return f"percentile {percentile} is outside (0, 1)"
    return None


def _build_hypothesis(proposal: dict, data: pd.DataFrame, library: dict[str, pd.Series]) -> Hypothesis:
    signal = library[proposal["signal_name"]]
    return Hypothesis(
        name=f"{proposal['signal_name']}@p{float(proposal['percentile']):.2f}",
        description=proposal.get("reason", ""),
        signal=signal,
        pnl=data["pnl"],
    )


def _log_entry(entry: dict, log_path: str) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def run_loop(data: pd.DataFrame, max_iterations: int = MAX_ITERATIONS,
             gemini_client: "object | None" = None, log_path: str = HYPOTHESES_LOG_PATH,
             n_permutations: int = 2000, percentile_arg_name: str = "percentile") -> list[dict]:
    """The actual iteration loop. `data` must carry the columns
    _signal_library() needs plus `pnl` (real caller: vrp_measure.replay()
    run through add_filter_columns(), see __main__ below; tests inject
    synthetic data of the same shape). Returns the list of logged
    entries, in order, and always writes each one to `log_path` before
    moving to the next iteration -- so a crash mid-loop still leaves a
    truthful, partial log rather than losing everything."""
    library = _signal_library(data)
    available_signals = sorted(library.keys())
    history: list[dict] = []

    for i in range(max_iterations):
        proposal = call_gemini_proposer(history, available_signals, client=gemini_client)
        error = _validate_proposal(proposal, available_signals)

        if error is not None:
            entry = {"iteration": i, "timestamp": _now(), "proposal": proposal, "verdict": None, "error": error}
            _log_entry(entry, log_path)
            history.append(entry)
            continue  # a bad proposal costs an iteration but doesn't stop the loop -- the model gets to see why it failed and try again

        try:
            hyp = _build_hypothesis(proposal, data, library)
            verdict = falsify(hyp, n_permutations=n_permutations)
        except Exception as e:
            entry = {"iteration": i, "timestamp": _now(), "proposal": proposal, "verdict": None,
                      "error": f"falsification failed: {e}"}
            _log_entry(entry, log_path)
            history.append(entry)
            continue

        entry = {"iteration": i, "timestamp": _now(), "proposal": proposal,
                  "verdict": asdict(verdict), "error": None}
        _log_entry(entry, log_path)
        history.append(entry)

    return history


def load_real_data() -> pd.DataFrame:
    """Recomputes the validated reconstruction (same calibration
    reconstruct.py uses) and returns it in the shape _signal_library() and
    run_loop() need: date-indexed, with vrp_edge/contango/pnl columns.
    Shared by this module's __main__ and pipeline.falsify.mcp_tools (W6),
    so the two never load real data two different ways."""
    from pipeline.backtest.reconstruct import _load_real_flagship_weeks, calibrate_skew_multiplier
    from pipeline.backtest.vrp_measure import add_filter_columns, replay

    real_weeks = _load_real_flagship_weeks()
    a, b = calibrate_skew_multiplier(real_weeks)
    result = replay(a, b)
    return add_filter_columns(result).set_index("entry")


if __name__ == "__main__":
    print("Recomputing the validated reconstruction (same calibration reconstruct.py uses)...")
    data = load_real_data()
    print(f"  {len(data)} weeks loaded, running the propose/falsify loop (max {MAX_ITERATIONS} iterations)...")

    history = run_loop(data)
    for h in history:
        status = h["error"] or ("SURVIVED" if h["verdict"]["survived"] else f"KILLED at {h['verdict']['killed_at']}")
        print(f"  iteration {h['iteration']}: {h['proposal'].get('signal_name')} "
              f"@ {h['proposal'].get('percentile')} -> {status}")
    print(f"\nLogged to {HYPOTHESES_LOG_PATH}")
