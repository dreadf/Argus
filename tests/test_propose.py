"""
Tests for pipeline/falsify/propose.py (W3): the LLM-proposes/gauntlet-kills
loop. Every test here injects a fake Gemini client (matching
pipeline/reviewer/reviewer.py's own self-check pattern) -- no network call
is ever made, and MAX_ITERATIONS/GEMINI_API_KEY are never touched.
"""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from pipeline.falsify.propose import (
    HYPOTHESES_LOG_PATH,
    _build_hypothesis,
    _signal_library,
    _validate_proposal,
    call_gemini_proposer,
    run_loop,
)


class _FakeGenaiClient:
    """responses: a list of raw text strings, one per call. If the loop
    calls more times than there are responses, the last one repeats."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.call_count = 0

    class _Models:
        def __init__(self, outer):
            self._outer = outer

        def generate_content(self, model, contents):
            outer = self._outer
            idx = min(outer.call_count, len(outer._responses) - 1)
            outer.call_count += 1
            return SimpleNamespace(text=outer._responses[idx])

    @property
    def models(self):
        return self._Models(self)


def _synthetic_data(seed=1, n_weeks=100):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-03", periods=n_weeks, freq="W-FRI")
    vrp_edge = rng.normal(0, 1, size=n_weeks)
    contango = rng.normal(0, 1, size=n_weeks)
    pnl = rng.normal(0.05, 0.3, size=n_weeks)
    return pd.DataFrame({"vrp_edge": vrp_edge, "contango": contango, "pnl": pnl}, index=dates)


def test_signal_library_has_expected_names_and_correct_transforms():
    data = _synthetic_data()
    lib = _signal_library(data)
    assert set(lib.keys()) == {
        "vrp_edge", "contango", "vrp_edge_minus_contango",
        "vrp_edge_3w_mean", "contango_5w_mean", "vrp_edge_zscore_13w",
    }
    assert (lib["vrp_edge"] == data["vrp_edge"]).all()
    assert np.allclose(lib["vrp_edge_minus_contango"], data["vrp_edge"] - data["contango"])
    assert np.allclose(lib["vrp_edge_3w_mean"], data["vrp_edge"].rolling(3, min_periods=1).mean())


def test_validate_proposal_accepts_a_good_proposal():
    err = _validate_proposal({"signal_name": "vrp_edge", "percentile": 0.33, "reason": "x"}, ["vrp_edge"])
    assert err is None


def test_validate_proposal_rejects_unknown_signal_name():
    err = _validate_proposal({"signal_name": "not_a_real_signal", "percentile": 0.33}, ["vrp_edge"])
    assert err is not None and "not in the pre-registered menu" in err


@pytest.mark.parametrize("bad_percentile", [0.0, 1.0, -0.1, 1.5, "not_a_number", None])
def test_validate_proposal_rejects_bad_percentile(bad_percentile):
    err = _validate_proposal({"signal_name": "vrp_edge", "percentile": bad_percentile}, ["vrp_edge"])
    assert err is not None


def test_validate_proposal_propagates_upstream_parse_error():
    err = _validate_proposal({"error": "unparseable proposer response: 'garbage'"}, ["vrp_edge"])
    assert err == "unparseable proposer response: 'garbage'"


def test_build_hypothesis_uses_the_named_library_signal():
    data = _synthetic_data()
    lib = _signal_library(data)
    hyp = _build_hypothesis({"signal_name": "contango", "percentile": 0.4, "reason": "why not"}, data, lib)
    assert hyp.name == "contango@p0.40"
    assert (hyp.signal == data["contango"]).all()
    assert (hyp.pnl == data["pnl"]).all()


def test_call_gemini_proposer_parses_a_clean_json_response():
    client = _FakeGenaiClient(['{"signal_name": "vrp_edge", "percentile": 0.3, "reason": "test"}'])
    out = call_gemini_proposer([], ["vrp_edge"], client=client)
    assert out == {"signal_name": "vrp_edge", "percentile": 0.3, "reason": "test"}


def test_call_gemini_proposer_strips_code_fences():
    client = _FakeGenaiClient(['```json\n{"signal_name": "vrp_edge", "percentile": 0.3}\n```'])
    out = call_gemini_proposer([], ["vrp_edge"], client=client)
    assert out["signal_name"] == "vrp_edge"


def test_call_gemini_proposer_fails_closed_on_unparseable_text():
    client = _FakeGenaiClient(["this is not json at all"])
    out = call_gemini_proposer([], ["vrp_edge"], client=client)
    assert "error" in out and "unparseable" in out["error"]


def test_run_loop_respects_max_iterations_and_logs_every_call(tmp_path):
    data = _synthetic_data()
    log_path = str(tmp_path / "hypotheses.jsonl")
    client = _FakeGenaiClient(['{"signal_name": "vrp_edge", "percentile": 0.33, "reason": "x"}'])

    history = run_loop(data, max_iterations=3, gemini_client=client, log_path=log_path, n_permutations=20)

    assert len(history) == 3
    assert client.call_count == 3
    lines = (tmp_path / "hypotheses.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        json.loads(line)  # each row is valid, self-contained JSON


def test_run_loop_never_exceeds_the_module_default_max_iterations(tmp_path):
    from pipeline.falsify import propose as propose_module
    assert propose_module.MAX_ITERATIONS == 5

    data = _synthetic_data()
    log_path = str(tmp_path / "hypotheses.jsonl")
    client = _FakeGenaiClient(['{"signal_name": "vrp_edge", "percentile": 0.33, "reason": "x"}'])
    history = run_loop(data, gemini_client=client, log_path=log_path, n_permutations=20)  # max_iterations omitted -> module default
    assert len(history) == 5
    assert client.call_count == 5


def test_run_loop_fails_an_iteration_closed_on_malformed_json_but_continues(tmp_path):
    data = _synthetic_data()
    log_path = str(tmp_path / "hypotheses.jsonl")
    client = _FakeGenaiClient([
        "not json",
        '{"signal_name": "vrp_edge", "percentile": 0.33, "reason": "recovered"}',
    ])

    history = run_loop(data, max_iterations=2, gemini_client=client, log_path=log_path, n_permutations=20)

    assert len(history) == 2
    assert history[0]["error"] is not None and history[0]["verdict"] is None
    assert history[1]["error"] is None and history[1]["verdict"] is not None


def test_run_loop_fails_an_iteration_closed_on_unknown_signal_name_but_continues(tmp_path):
    data = _synthetic_data()
    log_path = str(tmp_path / "hypotheses.jsonl")
    client = _FakeGenaiClient([
        '{"signal_name": "made_up_signal", "percentile": 0.33, "reason": "hallucinated"}',
        '{"signal_name": "vrp_edge", "percentile": 0.33, "reason": "recovered"}',
    ])

    history = run_loop(data, max_iterations=2, gemini_client=client, log_path=log_path, n_permutations=20)

    assert "not in the pre-registered menu" in history[0]["error"]
    assert history[0]["verdict"] is None
    assert history[1]["verdict"] is not None


def test_run_loop_feeds_prior_verdicts_back_into_the_prompt(tmp_path, monkeypatch):
    """The model should see what happened last iteration, not propose blind
    every time -- assert the history it's shown actually grows."""
    data = _synthetic_data()
    log_path = str(tmp_path / "hypotheses.jsonl")
    seen_history_lengths = []

    from pipeline.falsify import propose as propose_module

    real_build_prompt = propose_module._build_prompt

    def _spy_build_prompt(history, available_signals):
        seen_history_lengths.append(len(history))
        return real_build_prompt(history, available_signals)

    monkeypatch.setattr(propose_module, "_build_prompt", _spy_build_prompt)

    client = _FakeGenaiClient(['{"signal_name": "vrp_edge", "percentile": 0.33, "reason": "x"}'])
    run_loop(data, max_iterations=3, gemini_client=client, log_path=log_path, n_permutations=20)

    assert seen_history_lengths == [0, 1, 2]


def test_run_loop_default_log_path_matches_module_constant():
    assert HYPOTHESES_LOG_PATH == "output/falsify/hypotheses.jsonl"
