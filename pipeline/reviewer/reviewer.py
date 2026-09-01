"""
The Reviewer: the third stage of Picker -> Guard -> Reviewer (Build Step
T3). An LLM (Gemini) looks at a proposal that has already cleared every
fixed rule and every guard, and may VETO it, SHRINK it, or APPROVE it
as-is. It may never raise size and never originate a proposal of its own --
those two things are enforced in code below, not by the prompt, because a
prompt is not a safety mechanism.

Reads real (but read-only) account context through the MCP surface built in
pipeline/mcp/reviewer_server.py -- the same server whose entire design
point is that place_option_order is never even defined, so there is no
tool call this process could make that places, cancels, or closes an
order, regardless of what the model decides.
"""

from __future__ import annotations

import asyncio
import json
import math
import os

from fastmcp import Client
from google import genai

from pipeline.mcp.reviewer_server import aclose_reviewer_server, build_reviewer_server

REVIEWER_MODEL = "gemini-2.5-flash"

VALID_DECISIONS = {"APPROVE", "SHRINK", "VETO"}


def _fetch_account_context() -> dict:
    """One real, read-only MCP round trip for account context to hand the
    model -- proves the wiring is live, not simulated. Any failure here
    (network, auth, a changed tool name) degrades to an empty context
    rather than blocking the review: the Reviewer can only shrink/veto on
    top of an already-approved proposal, so losing this extra context
    makes it more conservative at worst, never less safe."""
    async def _run() -> dict:
        server = build_reviewer_server()
        try:
            async with Client(server) as client:
                result = await client.call_tool("get_account_info", {})
                text = result.content[0].text if result.content else "{}"
                payload = json.loads(text)
                return payload.get("data", {})
        finally:
            await aclose_reviewer_server(server)

    try:
        return asyncio.run(_run())
    except Exception as e:
        print(f"  Reviewer: MCP account-context fetch failed ({e}), proceeding with empty context.")
        return {}


def _build_prompt(proposal: dict, guard_result: dict, account_context: dict) -> str:
    return f"""You are the final review step for an automated options-selling agent, AFTER every fixed rule and every hard risk guard has already approved this trade. You are not the primary decision-maker -- the Picker (fixed rules) chose this spread and 14 Guards already checked it. Your only powers are:

1. APPROVE the proposal exactly as sized.
2. SHRINK it: give a multiplier strictly between 0 and 1, applied to contract count. You can never increase size.
3. VETO it entirely: decline to trade this proposal.

You have no other powers. You cannot change the strikes, the expiry, or propose a different trade. You cannot place, cancel, or modify any order -- your only tool access is read-only account data.

PROPOSAL (already Guard-approved):
{json.dumps({k: str(v) for k, v in proposal.items()}, indent=2)}

GUARD RESULTS (all passed, for context on what was already checked):
{json.dumps([r["guard"] for r in guard_result.get("results", [])], indent=2)}

ACCOUNT CONTEXT (read-only, may be incomplete):
{json.dumps(account_context, indent=2, default=str)[:2000]}

Respond with ONLY a JSON object, no other text, in exactly this shape:
{{"decision": "APPROVE" | "SHRINK" | "VETO", "multiplier": <number 0 to 1, only meaningful if SHRINK>, "reason": "<one sentence>"}}
"""


def call_gemini_reviewer(proposal: dict, guard_result: dict, account_context: dict, client: "genai.Client | None" = None) -> dict:
    """Real network call to Gemini. `client` is injectable so
    apply_reviewer_decision's safety properties can be tested without a
    network dependency -- this function is the only part of the module
    that isn't unit-tested against a live API."""
    if client is None:
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = _build_prompt(proposal, guard_result, account_context)
    response = client.models.generate_content(model=REVIEWER_MODEL, contents=prompt)
    text = (response.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):text.rfind("}") + 1]
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Fail closed, not open. An unparseable response means we cannot
        # confirm the model actually reasoned about this trade -- matching
        # the project's existing pattern elsewhere (missing IV, stale
        # data, an empty evidence gate all block rather than proceed on
        # an assumption). A malformed Reviewer response is one more thing
        # that isn't safe to guess about.
        return {"decision": "VETO", "multiplier": 0.0, "reason": f"unparseable reviewer response: {text[:200]!r}"}
    return parsed


def apply_reviewer_decision(proposal: dict, llm_output: dict) -> dict:
    """The actual safety mechanism. Takes whatever the model said and
    produces a new proposal that can only have EQUAL OR FEWER contracts
    than the input, regardless of what llm_output claims. This function
    has no network dependency and no LLM in it -- it is pure, and it is
    what T3's verification checks.

    Never trusts llm_output structurally: an unknown "decision" value, a
    multiplier outside [0, 1], a missing field, or a multiplier that would
    round UP to more contracts than the original are all clamped to the
    safe side (0 contracts, i.e. a de facto veto) rather than passed
    through. Silently accepting an out-of-range value from the model would
    make the prompt the safety mechanism instead of this function.
    """
    original_contracts = proposal.get("contracts", 0)
    decision = llm_output.get("decision")
    reason = llm_output.get("reason", "")

    if decision not in VALID_DECISIONS:
        decision = "VETO"
        reason = f"invalid/missing decision field ({llm_output.get('decision')!r}), failing closed: {reason}"

    if decision == "VETO":
        multiplier = 0.0
    elif decision == "APPROVE":
        multiplier = 1.0
    else:  # SHRINK
        raw_multiplier = llm_output.get("multiplier", 1.0)
        try:
            raw_multiplier = float(raw_multiplier)
        except (TypeError, ValueError):
            raw_multiplier = 0.0
        # Clamp to [0, 1] no matter what the model returned -- this is the
        # line that makes "never raise size" true regardless of the prompt.
        multiplier = min(1.0, max(0.0, raw_multiplier))

    new_contracts = math.floor(original_contracts * multiplier)  # floor, never round up
    new_contracts = min(new_contracts, original_contracts)  # redundant with the clamp above, kept as a second, independent guarantee

    result = dict(proposal)
    result["contracts"] = new_contracts
    if "max_loss_per_contract" in proposal:
        result["max_loss_total"] = proposal["max_loss_per_contract"] * new_contracts
    result["reviewer_decision"] = decision
    result["reviewer_multiplier"] = multiplier
    result["reviewer_reason"] = reason
    result["reviewer_vetoed"] = new_contracts < 1
    return result


def review_proposal(proposal: dict, guard_result: dict, gemini_client: "genai.Client | None" = None) -> dict:
    """Orchestrates: fetch read-only context, ask the model, enforce the
    invariant, return the (possibly shrunk or vetoed) proposal. This is
    the one function run_agent.py calls, and it is guaranteed never to
    raise: any exception from the network call itself (timeout, auth,
    quota, a transient API failure) fails closed to VETO rather than
    propagating up and crashing run_once with no audit row written --
    the same "fail closed, not open, and always log something" discipline
    already applied to malformed JSON above and to the data/account
    fetches in run_agent.py."""
    account_context = _fetch_account_context()
    try:
        llm_output = call_gemini_reviewer(proposal, guard_result, account_context, client=gemini_client)
    except Exception as e:
        llm_output = {"decision": "VETO", "multiplier": 0.0, "reason": f"reviewer call failed: {e}"}
    return apply_reviewer_decision(proposal, llm_output)


if __name__ == "__main__":
    # Self-checks against fake LLM responses -- no network required for
    # these; they exercise apply_reviewer_decision only, which is the
    # actual safety-critical code (Verification for T3).
    base_proposal = {
        "contracts": 6,
        "credit_per_contract": 15.0,
        "max_loss_per_contract": 485.0,
        "max_loss_total": 2910.0,
    }

    # 1. APPROVE leaves contracts untouched.
    out = apply_reviewer_decision(base_proposal, {"decision": "APPROVE", "reason": "looks fine"})
    assert out["contracts"] == 6 and not out["reviewer_vetoed"]
    print("APPROVE: contracts unchanged (6) -- PASS")

    # 2. SHRINK to 0.5 floors to 3 contracts, never rounds up.
    out = apply_reviewer_decision(base_proposal, {"decision": "SHRINK", "multiplier": 0.5, "reason": "elevated risk"})
    assert out["contracts"] == 3, out["contracts"]
    assert out["max_loss_total"] == 485.0 * 3
    print("SHRINK 0.5: 6 contracts -> 3 (floored) -- PASS")

    # 3. VETO forces 0 contracts regardless of any other field.
    out = apply_reviewer_decision(base_proposal, {"decision": "VETO", "reason": "too risky"})
    assert out["contracts"] == 0 and out["reviewer_vetoed"]
    print("VETO: contracts -> 0 -- PASS")

    # 4. THE CRITICAL CASE: a model trying to INCREASE size must be clamped.
    # This is the property the whole module exists to guarantee.
    out = apply_reviewer_decision(base_proposal, {"decision": "SHRINK", "multiplier": 5.0, "reason": "size up"})
    assert out["contracts"] <= 6, f"reviewer was able to increase size: {out['contracts']}"
    assert out["reviewer_multiplier"] == 1.0, "multiplier > 1 was not clamped"
    print(f"Adversarial multiplier=5.0: clamped to 1.0, contracts stay at {out['contracts']} (never exceeds 6) -- PASS")

    # 5. A negative multiplier must not produce negative contracts.
    out = apply_reviewer_decision(base_proposal, {"decision": "SHRINK", "multiplier": -3.0, "reason": "bad input"})
    assert out["contracts"] == 0, out["contracts"]
    print("Adversarial multiplier=-3.0: clamped to 0.0, contracts -> 0 -- PASS")

    # 6. An invalid/unknown decision string fails closed (VETO), not open.
    out = apply_reviewer_decision(base_proposal, {"decision": "DOUBLE_SIZE", "reason": "??"})
    assert out["contracts"] == 0 and out["reviewer_decision"] == "VETO"
    print("Unknown decision string 'DOUBLE_SIZE': fails closed to VETO -- PASS")

    # 7. A malformed (non-JSON) raw LLM response, as call_gemini_reviewer
    # would hand back, also fails closed.
    fake_malformed = {"decision": "VETO", "multiplier": 0.0, "reason": "unparseable reviewer response: 'not json'"}
    out = apply_reviewer_decision(base_proposal, fake_malformed)
    assert out["contracts"] == 0
    print("Malformed upstream response: fails closed to VETO -- PASS")

    # 8. Original proposal dict is never mutated in place.
    before = dict(base_proposal)
    apply_reviewer_decision(base_proposal, {"decision": "VETO", "reason": "x"})
    assert base_proposal == before, "apply_reviewer_decision must not mutate its input"
    print("Input proposal not mutated -- PASS")

    # 9. review_proposal must never raise, even if the LLM call itself
    # throws (network/auth/quota) -- it must fail closed to VETO instead.
    # Patches out the MCP account-context fetch too, so this stays a fully
    # offline test rather than depending on Alpaca connectivity. Patches
    # globals() directly rather than re-importing this module by dotted
    # path -- `python -m` runs this file as __main__, so `import
    # pipeline.reviewer.reviewer` here would load a SECOND, distinct copy
    # of the module with its own separate globals, and patching that copy
    # would silently miss the __main__ copy's own review_proposal (caught
    # while writing this test: the patched fetch never actually took
    # effect, and the real Alpaca call fired anyway).
    class _FakeGenaiClient:
        class models:
            @staticmethod
            def generate_content(*a, **k):
                raise RuntimeError("simulated network failure")

    _original_fetch = globals()["_fetch_account_context"]
    globals()["_fetch_account_context"] = lambda: {}
    try:
        out = review_proposal(base_proposal, {"passed": True, "results": []}, gemini_client=_FakeGenaiClient())
    finally:
        globals()["_fetch_account_context"] = _original_fetch
    assert out["contracts"] == 0 and out["reviewer_decision"] == "VETO", out
    print("Simulated network failure during review_proposal: fails closed to VETO, does not raise -- PASS")

    print("\nAll reviewer.py self-checks passed (no network calls made).")

    # Optional live check: only runs if explicitly requested, since it
    # costs a real API call and needs GEMINI_API_KEY.
    if os.environ.get("REVIEWER_LIVE_TEST") == "1":
        from dotenv import load_dotenv

        load_dotenv()
        print("\nRunning ONE live end-to-end review (MCP fetch + real Gemini call)...")
        result = review_proposal(base_proposal, {"passed": True, "results": []})
        print(f"Live decision: {result['reviewer_decision']}, multiplier={result['reviewer_multiplier']}, "
              f"contracts {base_proposal['contracts']} -> {result['contracts']}")
        print(f"Reason: {result['reviewer_reason']}")
        assert result["contracts"] <= base_proposal["contracts"], "live call must never increase size"
        print("Live call obeys the never-increase-size invariant -- PASS")
