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
from pipeline.execution.orders import submit_open_order
from pipeline.execution.positions import open_spread_positions
from pipeline.options.chain import fetch_chain, get_spot
from pipeline.options.contracts import expiries_in_window
from pipeline.options.selector import select_spread
from pipeline.data.vix import current_contango_and_threshold, is_vix_cache_stale, refresh_vix_cache
from pipeline.options.vol import fetch_recent_closes, realized_vol
from pipeline.reviewer.reviewer import review_proposal
from pipeline.risk import options_config as risk_cfg
from pipeline.risk.guards import run_all_guards

GATE_PATH = "output/data/evidence_gate_results.csv"


def _already_decided_today() -> bool:
    """Rule: at most one new position per session. A crash-and-restart must
    reconcile to 'already handled today', not open a second position.

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
    # NB: DRY_RUN must be included here -- an earlier version only checked
    # SOLD/SKIPPED, which meant every accepted-but-not-yet-live proposal
    # (the entire dry-run build/test period) was NOT recognized as already
    # decided, so a second same-day run would re-evaluate and log a second
    # accepted proposal. Confirmed by running twice in sequence before this
    # fix: two DRY_RUN rows were written for one session instead of one.
    return any(o in ("SOLD", "SKIPPED", "DRY_RUN") for o in todays_rows.get("outcome", []))


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

    order_result = submit_open_order(get_trading_client(), proposal, dry_run=dry_run)

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
        "outcome": "DRY_RUN" if dry_run else "SOLD",
    })
    print(f"{'[DRY RUN] ' if dry_run else ''}Proposal accepted and logged: {proposal['short_symbol']}/{proposal['long_symbol']}, "
          f"{proposal['contracts']} contracts, credit ${proposal['credit_per_contract']:.2f}/contract "
          f"(Reviewer: {proposal['reviewer_decision']})")
    return {"outcome": "DRY_RUN" if dry_run else "SOLD", "proposal": proposal, "order_result": order_result}


if __name__ == "__main__":
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
