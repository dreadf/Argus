"""
Daily entry point: Picker -> Guard -> Reviewer -> order.
dry_run=True by default (Verification #6: must print the bet, write an
audit row, and send nothing).

Idempotent by design (Part 6, "exact decision logic"): at most one new
position opens per session, and a second run on the same day must find
today's SOLD/SKIPPED entry already in the audit log and do nothing rather
than re-evaluate and potentially double-open (Verification #8).
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timezone

import pandas as pd

from pipeline.audit.log import append_entry, read_log
from pipeline.execution.broker import get_account_state, get_clock, get_trading_client
from pipeline.execution.orders import submit_with_retry
from pipeline.execution.positions import open_spread_positions
from pipeline.execution.recovery import reconcile_positions, verify_fill_or_emergency_close
from pipeline.options.chain import fetch_chain, get_spot
from pipeline.options.contracts import expiries_in_window
from pipeline.options.selector import select_spread
from pipeline.data.vix import current_contango_and_threshold, is_vix_cache_stale, refresh_vix_cache
from pipeline.options.vol import fetch_recent_closes, realized_vol
from pipeline.reviewer.reviewer import review_proposal
from pipeline.risk import options_config as risk_cfg
from pipeline.risk.guards import run_all_guards

GATE_PATH = "output/data/evidence_gate_results.csv"


# Reasons logged before any real evaluation happens -- market closed, a
# transient fetch failure, a missing evidence-gate file. These mean "never
# got to look," not "looked and declined," so they must NOT block a retry
# later the same day once the underlying condition clears. Found live: an
# early run today logged "check_market_open" before the open, and without
# this exclusion _already_decided_today() would refuse to re-evaluate for
# the rest of the day even after the market opened -- the system could go
# an entire trading day without ever actually looking at a trade, if its
# first invocation happened to land before open (which a fixed-time cron
# firing near market open easily could, on any day the open is delayed).
_PRE_FLIGHT_SKIP_PREFIXES = ("check_market_open", "get_clock failed", "check_evidence_gate", "data/account fetch failed")


def _is_real_decision(row) -> bool:
    outcome = row.get("outcome")
    if outcome in ("SOLD", "DRY_RUN"):
        return True
    if outcome == "SKIPPED":
        reasons = row.get("guards_failed")
        if not isinstance(reasons, list) or not reasons:
            return True  # no reason recorded -- can't tell it was pre-flight, treat conservatively as decided
        return not all(any(str(r).startswith(p) for p in _PRE_FLIGHT_SKIP_PREFIXES) for r in reasons)
    return False


def _already_decided_today() -> bool:
    """Rule: at most one new position per session. A crash-and-restart must
    reconcile to 'already handled today', not open a second position --
    but only once the day has produced a REAL decision (see _is_real_decision),
    not merely a pre-flight bounce.

    Compares against the UTC date, not the local machine's date -- audit log
    timestamps are written in UTC (log.py), and this process may run from
    any timezone (WIB in practice). Comparing against a local `date.today()`
    would silently disagree with the log for a large chunk of every day
    (confirmed: running this near local midnight against a naive local-date
    comparison produced two SKIPPED rows for one session instead of one)."""
    log_df = read_log()
    if log_df.empty:
        return False
    log_df = log_df.dropna(subset=["timestamp"])
    if log_df.empty:
        return False
    log_dates = pd.to_datetime(log_df["timestamp"], utc=True).dt.date
    today_utc = datetime.now(timezone.utc).date()
    todays_rows = log_df[log_dates == today_utc]
    return any(_is_real_decision(row) for _, row in todays_rows.iterrows())


def _load_peak_equity() -> float | None:
    """Peak equity must persist across runs to mean anything (Guards #13/#14
    compare current equity against it). The audit log is the only durable
    state this project writes, so peak is derived from the max current_equity
    ever logged; a fresh account with no log rows returns None, which
    broker.get_account_state treats as "peak = current equity", per the
    cold-start table in Part 6."""
    log_df = read_log()
    if log_df.empty or "current_equity" not in log_df or log_df["current_equity"].dropna().empty:
        return None
    return float(log_df["current_equity"].dropna().max())


def run_once(dry_run: bool = True, today: date | None = None) -> dict:
    if today is None:
        today = date.today()

    if _already_decided_today():
        print(f"Already decided today ({today}) -- idempotent no-op, nothing re-evaluated.")
        return {"outcome": "ALREADY_DECIDED", "date": today}

    try:
        clock = get_clock()
    except Exception as e:
        append_entry({"mode": "MANUAL" if dry_run else "AUTO", "outcome": "SKIPPED",
                      "guards_failed": [f"get_clock failed: {e}"]})
        print(f"get_clock failed ({e}). Logged SKIP.")
        return {"outcome": "SKIPPED", "reason": f"get_clock failed: {e}"}
    if not clock["market_open"]:
        row = append_entry({"mode": "MANUAL" if dry_run else "AUTO", "outcome": "SKIPPED",
                             "guards_failed": ["check_market_open"]})
        print(f"Market closed. Logged SKIP. Next open: {clock['next_open']}")
        return {"outcome": "SKIPPED", "reason": "market closed"}

    if not os.path.exists(GATE_PATH):
        append_entry({"mode": "MANUAL" if dry_run else "AUTO", "outcome": "SKIPPED",
                      "guards_failed": ["check_evidence_gate"]})
        print("No evidence gate computed yet. Logged SKIP.")
        return {"outcome": "SKIPPED", "reason": "no evidence gate"}
    gate_df = pd.read_csv(GATE_PATH)

    # None of these are wrapped individually -- a fresh account/date range
    # raises inside realized_vol (fewer than 11 closes), .iloc[-1] raises on
    # 0-1 rows, and every network call here can raise on a transient API
    # failure. Without this try/except, any of those crashes the session
    # with zero audit row written, breaking both the "every day, including
    # failures, gets logged" principle and _already_decided_today()'s
    # ability to recognize the day was handled (item 9).
    try:
        account = get_account_state(peak_equity=_load_peak_equity(), open_positions=open_spread_positions())
        spot = get_spot()
        closes = fetch_recent_closes()
        rv_10d = realized_vol(closes, 10)
        spy_yesterday_move_pct = float(closes.pct_change().iloc[-1])

        exps = expiries_in_window(today, risk_cfg.MIN_DTE, risk_cfg.MAX_DTE)
        chain_df = fetch_chain(exps, spot=spot)
    except Exception as e:
        append_entry({"mode": "MANUAL" if dry_run else "AUTO", "outcome": "SKIPPED",
                      "guards_failed": [f"data/account fetch failed: {e}"]})
        print(f"Data or account fetch failed ({e}). Logged SKIP.")
        return {"outcome": "SKIPPED", "reason": f"fetch failed: {e}"}

    # recovery.py job #1: reconcile before acting. The broker's actual
    # positions are truth, never the audit log alone -- if it holds an
    # option leg this system's own bookkeeping doesn't know about (a
    # manual trade, a crash between fill and log write), opening a new
    # position on top of unknown exposure is unsafe.
    reconcile = reconcile_positions(account["raw_positions"])
    if not reconcile["safe_to_open"]:
        append_entry({
            "mode": "MANUAL" if dry_run else "AUTO", "spy_price": spot, "vol_forecast": rv_10d,
            "current_equity": account["current_equity"], "peak_equity": account["peak_equity"],
            "outcome": "SKIPPED",
            "guards_failed": [f"RECONCILE_MISMATCH: broker holds unrecognized option position(s): {reconcile['broker_only']}"],
        })
        print(f"Reconcile failed: broker holds unrecognized positions {reconcile['broker_only']}. Logged SKIP, not opening.")
        return {"outcome": "SKIPPED", "reason": "reconcile mismatch", "broker_only": reconcile["broker_only"]}

    proposal = select_spread(chain_df, spot, gate_df, account, today=today)
    if proposal is None:
        append_entry({
            "mode": "MANUAL" if dry_run else "AUTO", "spy_price": spot, "vol_forecast": rv_10d,
            "current_equity": account["current_equity"], "peak_equity": account["peak_equity"],
            "outcome": "SKIPPED", "guards_failed": ["no viable proposal from selector"],
        })
        print("Picker found no viable trade today (empty gate, no listed strikes, or budget too small). Logged SKIP.")
        return {"outcome": "SKIPPED", "reason": "no proposal"}

    # VIX term-structure data (W4/check_term_structure) fails closed on
    # its own, independent of the main data fetch above: a CBOE outage
    # should not stop the OTHER 14 guards from evaluating and logging
    # their own reasons -- it should only make check_term_structure
    # itself block, the same way a missing/stale option chain only trips
    # check_data_sanity rather than aborting the whole run.
    try:
        refresh_vix_cache()
        vix_stale = is_vix_cache_stale()
        vix_contango, vix_threshold = current_contango_and_threshold()
    except Exception as e:
        print(f"  VIX refresh/threshold failed ({e}); check_term_structure will block on stale data.")
        vix_stale, vix_contango, vix_threshold = True, None, None

    guard_state = {
        "market_open": True, "data_stale": False, "spot_price": spot, "chain_spot_price": spot,
        "evidence_gate_passed": True, "current_equity": account["current_equity"],
        "peak_equity": account["peak_equity"], "open_positions": account["open_positions"],
        "rv_10d": rv_10d, "spy_yesterday_move_pct": spy_yesterday_move_pct,
        "vix_data_stale": vix_stale, "vix_contango_ratio": vix_contango, "vix_contango_threshold": vix_threshold,
    }
    guard_result = run_all_guards(guard_state, proposal)

    if not guard_result["passed"]:
        reasons = [f"{f['guard']}: {f['reason']}" for f in guard_result["failed"]]
        append_entry({
            "mode": "MANUAL" if dry_run else "AUTO", "spy_price": spot, "vol_forecast": rv_10d,
            "current_equity": account["current_equity"], "peak_equity": account["peak_equity"],
            "gate_distance": proposal["distance"], "gate_cushion_se": proposal["cushion_se"],
            "realized_distance": proposal["realized_distance"],
            "proposed_contracts": proposal["contracts"], "proposed_credit": proposal["credit_per_contract"],
            "proposed_max_loss": proposal["max_loss_total"], "guards_checked": len(guard_result["results"]),
            "guards_failed": reasons, "outcome": "SKIPPED",
        })
        print(f"Blocked by guards: {reasons}")
        return {"outcome": "SKIPPED", "reason": reasons}

    # Reviewer: the third stage (Picker -> Guard -> Reviewer). May only
    # veto or shrink what the Picker chose and every Guard already passed
    # -- it can never raise size and never originate a proposal of its
    # own (enforced in pipeline.reviewer.apply_reviewer_decision, not by
    # the prompt). Never raises: a Gemini/MCP failure fails closed to a
    # veto internally, so this call cannot crash the session and leave
    # today unlogged (item 9's discipline, extended to this stage too).
    reviewed = review_proposal(proposal, guard_result)

    if reviewed["reviewer_vetoed"]:
        append_entry({
            "mode": "MANUAL" if dry_run else "AUTO", "spy_price": spot, "vol_forecast": rv_10d,
            "current_equity": account["current_equity"], "peak_equity": account["peak_equity"],
            "gate_distance": proposal["distance"], "gate_cushion_se": proposal["cushion_se"],
            "realized_distance": proposal["realized_distance"],
            "proposed_contracts": proposal["contracts"], "proposed_credit": proposal["credit_per_contract"],
            "proposed_max_loss": proposal["max_loss_total"], "guards_checked": len(guard_result["results"]),
            "guards_failed": [f"REVIEWER_VETO: {reviewed['reviewer_reason']}"],
            "reviewer_decision": reviewed["reviewer_decision"], "reviewer_multiplier": reviewed["reviewer_multiplier"],
            "reviewer_reason": reviewed["reviewer_reason"], "outcome": "SKIPPED",
        })
        print(f"Vetoed by Reviewer: {reviewed['reviewer_reason']}")
        return {"outcome": "SKIPPED", "reason": f"reviewer veto: {reviewed['reviewer_reason']}"}

    proposal = reviewed  # possibly shrunk (contracts/max_loss_total already recomputed); carries reviewer_* fields onward

    # Rule #9 in full now (orders.submit_with_retry): submit at mid, wait up
    # to 5 min, and if unfilled cancel + reprice once against a fresh mid
    # before giving up -- found live on 2026-09-01 that this was never
    # actually implemented and a stuck order needed manual handling.
    client = get_trading_client()
    submission = submit_with_retry(client, proposal, dry_run=dry_run)
    proposal = submission["proposal"]  # possibly repriced -- the audit log must reflect what was actually submitted, not the stale original quote
    order_result = submission["order_result"]

    if submission["status"] == "SKIPPED":
        append_entry({
            "mode": "MANUAL" if dry_run else "AUTO", "spy_price": spot, "vol_forecast": rv_10d,
            "current_equity": account["current_equity"], "peak_equity": account["peak_equity"],
            "gate_distance": proposal["distance"], "gate_cushion_se": proposal["cushion_se"],
            "realized_distance": proposal["realized_distance"],
            "short_symbol": proposal["short_symbol"], "long_symbol": proposal["long_symbol"],
            "proposed_contracts": proposal["contracts"], "proposed_credit": proposal["credit_per_contract"],
            "proposed_max_loss": proposal["max_loss_total"], "guards_checked": len(guard_result["results"]),
            "guards_failed": [f"ORDER_NOT_FILLED: {submission['reason']}"],
            "reviewer_decision": proposal["reviewer_decision"], "reviewer_multiplier": proposal["reviewer_multiplier"],
            "reviewer_reason": proposal["reviewer_reason"],
            "order_id": None if dry_run else str(order_result.id),
            "outcome": "SKIPPED",
        })
        print(f"Order did not fill: {submission['reason']}. Logged SKIP.")
        return {"outcome": "SKIPPED", "reason": submission["reason"]}

    # recovery.py job #2: confirm both legs actually filled in equal
    # quantity before doing anything else. An orphaned short put has no
    # floor at all -- the one scenario where this system's stated max loss
    # stops being true. Runs AFTER submit_with_retry's own polling has
    # already confirmed a real fill, not immediately post-submission when
    # nothing could possibly have filled yet (the original bug: this check
    # used to run right after submission and always saw 0/0 open contracts,
    # reporting a false "both legs filled equally" before any fill occurred).
    fill_check = verify_fill_or_emergency_close(client, proposal, dry_run=dry_run)
    if fill_check["halt"]:
        print(f"HALT: {fill_check['reason']}")

    append_entry({
        "mode": "MANUAL" if dry_run else "AUTO", "spy_price": spot, "vol_forecast": rv_10d,
        "current_equity": account["current_equity"], "peak_equity": account["peak_equity"],
        "gate_distance": proposal["distance"], "gate_cushion_se": proposal["cushion_se"],
        "realized_distance": proposal["realized_distance"],
        "short_symbol": proposal["short_symbol"], "long_symbol": proposal["long_symbol"],
        "net_delta_share_equiv": proposal["net_delta_share_equiv"],
        "proposed_contracts": proposal["contracts"], "proposed_credit": proposal["credit_per_contract"],
        "proposed_max_loss": proposal["max_loss_total"], "guards_checked": len(guard_result["results"]),
        "guards_failed": [], "reviewer_decision": proposal["reviewer_decision"],
        "reviewer_multiplier": proposal["reviewer_multiplier"], "reviewer_reason": proposal["reviewer_reason"],
        "order_id": None if dry_run else str(order_result.id),
        "outcome": "DRY_RUN" if dry_run else "SOLD",
    })
    print(f"{'[DRY RUN] ' if dry_run else ''}Proposal accepted and logged: {proposal['short_symbol']}/{proposal['long_symbol']}, "
          f"{proposal['contracts']} contracts, credit ${proposal['credit_per_contract']:.2f}/contract "
          f"(Reviewer: {proposal['reviewer_decision']})")
    return {"outcome": "DRY_RUN" if dry_run else "SOLD", "proposal": proposal, "order_result": order_result, "halt": fill_check["halt"]}


if __name__ == "__main__":
    # Self-check for the pre-flight-vs-real-decision split: a day with only
    # pre-flight bounces (market closed, a transient fetch failure) is NOT
    # decided; a day with a real evaluation (a guard actually ran and
    # blocked, a Reviewer veto, a fill) IS decided. Runs before the CLI
    # proceeds, same convention as every other module's self-checks in
    # this project.
    only_preflight = pd.DataFrame([
        {"outcome": "SKIPPED", "guards_failed": ["check_market_open"]},
        {"outcome": "SKIPPED", "guards_failed": ["data/account fetch failed: simulated"]},
    ])
    assert not any(_is_real_decision(r) for _, r in only_preflight.iterrows()), \
        "pre-flight-only skips must not count as a real decision"
    print("Pre-flight-only skips: correctly NOT a real decision")

    real_guard_block = pd.DataFrame([{"outcome": "SKIPPED", "guards_failed": ["check_credit_width_ratio: below floor"]}])
    assert any(_is_real_decision(r) for _, r in real_guard_block.iterrows()), \
        "a real guard block must count as a decision"
    print("Real guard-block skip: correctly IS a real decision")

    sold_row = pd.DataFrame([{"outcome": "SOLD", "guards_failed": []}])
    assert any(_is_real_decision(r) for _, r in sold_row.iterrows())
    print("SOLD row: correctly IS a real decision")

    no_reason_row = pd.DataFrame([{"outcome": "SKIPPED", "guards_failed": None}])
    assert any(_is_real_decision(r) for _, r in no_reason_row.iterrows()), \
        "a SKIPPED row with no reason recorded must be treated conservatively as decided"
    print("SKIPPED with no reason recorded: correctly treated as decided (fails closed)")

    print("\nAll run_agent.py self-checks passed.\n")

    parser = argparse.ArgumentParser()
    # A mutually exclusive group so passing both flags raises an explicit
    # argparse error instead of silently picking whichever was typed last
    # (confirmed via interpreter: the two flags previously wrote to the same
    # dest with no exclusivity, so "--dry-run --live" went live and
    # "--live --dry-run" stayed dry-run -- order alone decided whether real
    # money traded, with no error either way).
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True)
    group.add_argument("--live", dest="dry_run", action="store_false")
    args = parser.parse_args()

    result = run_once(dry_run=args.dry_run)
    print(f"\nResult: {result['outcome']}")
