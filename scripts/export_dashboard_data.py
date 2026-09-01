"""
Computes the four static JSON files the public/ dashboard reads. No new
computation logic lives here -- every number is produced by the same
functions already built and verified for pipeline/ui/app.py (evidence gate,
validate_reconstruction, false_trip_rate_term_structure, read_log, the
positions-enrichment join). This script is serialization, run manually today
(chainable after run_agent.py later) with its output committed and pushed --
Vercel's git integration redeploys on push, same mechanic already proven with
Streamlit Cloud.

Only pipeline/execution/broker.py's live account/positions call is
deliberately NOT here -- that's what api/account.py fetches fresh on every
page view. Everything else only changes once a day at most, so freezing it
here is correct, not a shortcut.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from pipeline.audit.log import read_log
from pipeline.execution.positions import open_spread_positions
from pipeline.options.contracts import parse_occ_symbol

OUT_DIR = Path(__file__).resolve().parents[1] / "public" / "data"

# Fitted once via calibrate_skew_multiplier's grid search (confirmed by
# re-running it directly: ~21s, too slow for a live path). These are the
# SAME constants already baked into the committed reconstruction CSV --
# using them here keeps this export consistent with what's already shipped,
# not a new assumption. Not imported from pipeline.backtest.reconstruct
# because that file is being actively edited by a concurrent session
# (Experiment 21) -- these two functions are stable and cheap to call
# directly, so importing just them avoids any collision.
FITTED_A = 1.18
FITTED_B = -0.95


def _clean(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def _status_from_row(latest_row) -> dict:
    if latest_row is None:
        return {"cls": "neutral", "word": "Not yet run", "rest": "no decisions logged today.", "timestamp": ""}
    outcome = _clean(latest_row.get("outcome"))
    ts = str(latest_row.get("timestamp", ""))
    if outcome in ("SOLD", "FILLED"):
        n = _clean(latest_row.get("proposed_contracts"))
        return {"cls": "good", "word": "Trading",
                "rest": f"opened {latest_row.get('short_symbol')} / {latest_row.get('long_symbol')}, {n if n is not None else '?'} contract(s).",
                "timestamp": ts}
    if outcome == "DRY_RUN":
        return {"cls": "neutral", "word": "Dry run",
                "rest": f"would have opened {latest_row.get('short_symbol')} / {latest_row.get('long_symbol')}. No real order sent.",
                "timestamp": ts}
    if outcome == "SKIPPED":
        reasons = latest_row.get("guards_failed")
        rest = "; ".join(str(r) for r in reasons) if isinstance(reasons, list) and reasons else "no reason recorded."
        return {"cls": "bad", "word": "Declined to trade", "rest": rest, "timestamp": ts}
    if outcome == "CLOSED":
        return {"cls": "neutral", "word": "Position closed", "rest": str(latest_row.get("close_reason", "")), "timestamp": ts}
    if outcome == "EMERGENCY_CLOSE_ORPHAN":
        return {"cls": "bad", "word": "Emergency close", "rest": str(latest_row.get("close_reason", "")), "timestamp": ts}
    return {"cls": "neutral", "word": str(outcome), "rest": "", "timestamp": ts}


def _decision_path(gate_df, gate_choice, latest_row) -> list[dict]:
    rows = []
    if gate_df is None:
        rows.append({"stage": "1. Evidence", "cls": "neutral", "detail": "not computed"})
    elif gate_choice is None:
        rows.append({"stage": "1. Evidence", "cls": "bad", "detail": "no cell currently clears the 2-SE bar"})
    else:
        rows.append({"stage": "1. Evidence", "cls": "good",
                     "detail": f"{gate_choice['distance']:.0%} / ${gate_choice['width']:.0f} clears, cushion {gate_choice['cushion_se']:.2f} SE"})

    if latest_row is None:
        rows.append({"stage": "2. Guards", "cls": "neutral", "detail": "no decision logged today"})
        rows.append({"stage": "3. Reviewer", "cls": "neutral", "detail": "n/a"})
        rows.append({"stage": "4. Order", "cls": "neutral", "detail": "n/a"})
        return rows

    guards_checked = _clean(latest_row.get("guards_checked"))
    guards_failed = latest_row.get("guards_failed")
    has_failures = isinstance(guards_failed, list) and len(guards_failed) > 0
    if guards_checked is None:
        rows.append({"stage": "2. Guards", "cls": "neutral", "detail": "not reached today"})
    elif has_failures:
        rows.append({"stage": "2. Guards", "cls": "bad",
                     "detail": f"{int(guards_checked)} checked, blocked: "
                               + "; ".join(_humanize_guard_reason(str(g)) for g in guards_failed)})
    else:
        rows.append({"stage": "2. Guards", "cls": "good", "detail": f"all {int(guards_checked)} passed"})

    reviewer_decision = _clean(latest_row.get("reviewer_decision"))
    if reviewer_decision is None:
        rows.append({"stage": "3. Reviewer", "cls": "neutral", "detail": "not reached today"})
    else:
        reviewer_reason = _clean(latest_row.get("reviewer_reason")) or ""
        r_cls = "good" if reviewer_decision == "APPROVE" else ("bad" if reviewer_decision == "VETO" else "neutral")
        rows.append({"stage": "3. Reviewer", "cls": r_cls, "detail": f"{reviewer_decision}: {reviewer_reason}"})

    outcome_map = {
        "SOLD": ("good", "sent live"),
        "FILLED": ("good", "sent live, filled"),
        "DRY_RUN": ("neutral", "dry run, no order sent"),
        "SKIPPED": ("bad", "never reached, blocked upstream"),
        "CLOSED": ("neutral", "position closed"),
        "EMERGENCY_CLOSE_ORPHAN": ("bad", "emergency close"),
    }
    outcome = _clean(latest_row.get("outcome"))
    o_cls, o_detail = outcome_map.get(outcome, ("neutral", str(outcome) if outcome else "no decision today"))
    rows.append({"stage": "4. Order", "cls": o_cls, "detail": o_detail})
    return rows


def _category(row) -> str:
    outcome = row.get("outcome")
    if outcome in ("SOLD", "FILLED"):
        return "Traded"
    if outcome == "DRY_RUN":
        return "Dry run"
    if outcome == "SKIPPED":
        reasons = row.get("guards_failed")
        if isinstance(reasons, list) and any(str(r).startswith("REVIEWER_VETO") for r in reasons):
            return "Reviewer-vetoed"
        return "Guard-blocked"
    return "Other"


# Some SKIPPED rows carry raw internal identifiers (run_agent.py's pre-flight
# checks, logged before the real per-trade guards ever run) rather than a
# human sentence -- guards.py's own check_* functions already return readable
# text like "market closed", so only these pre-flight literals need
# translating for the public decision log.
_REASON_TRANSLATIONS = {
    "check_market_open": "Market was closed",
    "check_evidence_gate": "No trade shape cleared the evidence gate today",
    "no viable proposal from selector": "No (distance, width) combination cleared the evidence gate today",
}
_CLOSE_REASON_TEXT = {
    "profit_target": "Closed at profit target",
    "day_before_expiry": "Closed the day before expiry (assignment-risk protection)",
    "hard_drawdown": "Closed on a hard drawdown stop",
    "emergency_close_orphan": "Emergency-closed an unrecognized or orphaned leg",
}


def _humanize_guard_reason(raw: str) -> str:
    if raw in _REASON_TRANSLATIONS:
        return _REASON_TRANSLATIONS[raw]
    if raw.startswith("get_clock failed"):
        return "Could not confirm market hours (clock check failed)"
    if raw.startswith("data/account fetch failed"):
        return "Could not fetch live account or market data"
    if raw.startswith("RECONCILE_MISMATCH"):
        return "Broker holds a position the audit log doesn't recognize; blocked pending review"
    if raw.startswith("REVIEWER_VETO"):
        detail = raw.split(":", 1)[1].strip() if ":" in raw else ""
        return f"AI reviewer vetoed: {detail}" if detail else "AI reviewer vetoed the proposal"
    if raw.startswith("ORDER_NOT_FILLED"):
        return "Order did not fill in time and was cancelled"
    return raw


def _describe_spread(row) -> str:
    short_sym, long_sym = row.get("short_symbol"), row.get("long_symbol")
    try:
        short_info = parse_occ_symbol(short_sym)
        long_info = parse_occ_symbol(long_sym)
        desc = f"{short_info['root']} {short_info['strike']:.0f}/{long_info['strike']:.0f}{short_info['right']}"
    except (ValueError, TypeError):
        desc = f"{short_sym} / {long_sym}"
    contracts = _clean(row.get("proposed_contracts"))
    n = f"{contracts:.0f}" if contracts is not None else "?"
    credit = _clean(row.get("proposed_credit"))
    credit_text = f" at ${credit:.2f}/contract" if credit is not None else ""
    human_action = _clean(row.get("human_action"))
    suffix = f" ({human_action})" if isinstance(human_action, str) and human_action else ""
    return f"Opened {desc}, {n} contract(s){credit_text}{suffix}"


def _reason(row) -> str:
    outcome = row.get("outcome")
    if outcome in ("SOLD", "FILLED"):
        return _describe_spread(row)
    if outcome == "SKIPPED":
        reasons = row.get("guards_failed")
        if isinstance(reasons, list) and reasons:
            return "; ".join(_humanize_guard_reason(str(r)) for r in reasons)
        return "No reason recorded"
    if outcome in ("CLOSED", "EMERGENCY_CLOSE_ORPHAN"):
        raw = str(row.get("close_reason", "") or "")
        return _CLOSE_REASON_TEXT.get(raw, raw or "No reason recorded")
    return ""


def build_overview() -> dict:
    log_df = read_log()
    latest_row = log_df.sort_values("timestamp", ascending=False).iloc[0] if not log_df.empty else None
    status = _status_from_row(latest_row)

    market, volatility, market_error = None, None, None
    try:
        from pipeline.data.vix import contango_ratio, current_contango_and_threshold, load_cached_vix, refresh_vix_cache
        from pipeline.options.chain import get_spot
        from pipeline.options.vol import fetch_recent_closes, realized_vol

        spot = get_spot()
        closes = fetch_recent_closes()
        refresh_vix_cache()
        vix9d = load_cached_vix("VIX9D")
        vix3m = load_cached_vix("VIX3M")
        _, contango_threshold = current_contango_and_threshold()
        vix9d_decimal = float(vix9d.iloc[-1]) / 100.0
        rv10d = realized_vol(closes, 10)
        ratio = vix9d_decimal / rv10d if rv10d else None
        market = {
            "spot": spot,
            "yesterday_move_pct": float(closes.pct_change().iloc[-1]),
            "contango": float(contango_ratio(vix9d, vix3m).iloc[-1]),
            "contango_threshold": contango_threshold,
        }
        if ratio is not None:
            if ratio > 1.15:
                v_cls, v_text = "good", "Rich: selling is well compensated right now"
            elif ratio < 0.85:
                v_cls, v_text = "bad", "Thin: selling isn't well compensated right now"
            else:
                v_cls, v_text = "neutral", "Fair: normal compensation"
            volatility = {
                "vix9d_decimal": vix9d_decimal, "rv10d": rv10d, "ratio": ratio,
                "verdict_class": v_cls, "verdict_text": v_text,
                "rich_threshold": 1.15, "thin_threshold": 0.85,
            }
    except Exception as e:
        market_error = str(e)

    gate_df, gate_choice, gate_error = None, None, None
    try:
        gate_path = "output/data/evidence_gate_results.csv"
        if os.path.exists(gate_path):
            gate_df = pd.read_csv(gate_path)
            from pipeline.options.selector import choose_distance_width

            gate_choice = choose_distance_width(gate_df)
    except Exception as e:
        gate_error = str(e)

    open_positions = []
    try:
        spreads = open_spread_positions(log_df)
        today = date.today()
        for spread in spreads:
            short_sym, long_sym = spread["short_symbol"], spread["long_symbol"]
            try:
                short_info = parse_occ_symbol(short_sym)
                long_info = parse_occ_symbol(long_sym)
                strike, right = short_info["strike"], short_info["right"]
                room_pct = (market["spot"] - strike) / market["spot"] if (market and right == "P") else \
                    (strike - market["spot"]) / market["spot"] if market else None
                expires_days = (short_info["expiry"] - today).days
                strikes_text = f"SELL ${strike:.2f}{right} / BUY ${long_info['strike']:.2f}{right}"
                underlying = short_info["root"]
            except ValueError:
                room_pct, expires_days, strikes_text, underlying = None, None, f"{short_sym} / {long_sym}", "?"
            open_positions.append({
                "short_symbol": short_sym, "long_symbol": long_sym, "underlying": underlying,
                "strikes": strikes_text, "room_pct": room_pct, "expires_days": expires_days,
                "qty": spread["contracts"],
                "collected": spread["credit_per_contract"] * spread["contracts"],
                "max_loss": spread["max_loss_total"],
            })
    except Exception:
        pass

    return {
        "status": status,
        "market": market, "market_error": market_error,
        "volatility": volatility,
        "decision_path": _decision_path(gate_df, gate_choice, latest_row),
        "open_positions": open_positions,
        "narrative": _narrative(status, market, volatility, open_positions, gate_choice),
    }


def _narrative(status, market, volatility, open_positions, gate_choice) -> list[dict]:
    """A short, plain-English readout of today's state as {label, cls,
    detail} lines -- label carries the color (the one verdict word), detail
    is the plain-language explanation. This is what a reader should be able
    to read top-to-bottom and understand "what's going on" without parsing
    the metric cards below, which stay as the supporting detail."""
    lines = []

    if open_positions:
        p = open_positions[0]
        extra = f" (and {len(open_positions) - 1} more)" if len(open_positions) > 1 else ""
        lines.append({
            "label": "Open position", "cls": "neutral",
            "detail": f"{p['underlying']} {p['strikes']}, {p['qty']} contract(s), ${p['collected']:.0f} collected{extra}.",
        })
    else:
        lines.append({"label": status.get("word", "Unknown"), "cls": status.get("cls", "neutral"), "detail": status.get("rest", "")})

    if market:
        move = market["yesterday_move_pct"]
        direction = "up" if move >= 0 else "down"
        would_block_move = abs(move) > 0.02
        would_block_term = market.get("contango_threshold") is not None and market["contango"] < market["contango_threshold"]
        would_block = would_block_move or would_block_term
        lines.append({
            "label": "Would block a new trade" if would_block else "Nothing blocks a new trade", "cls": "bad" if would_block else "good",
            "detail": f"SPY ${market['spot']:.2f}, {direction} {abs(move):.1%} from yesterday"
                      + (f", term structure at {market['contango']:.3f}" if would_block_term else "") + ".",
        })

    if volatility:
        verdict_word = volatility["verdict_text"].split(":", 1)[0]
        lines.append({
            "label": verdict_word, "cls": volatility["verdict_class"],
            "detail": f"VIX9D {volatility['vix9d_decimal']:.1%} vs. realized {volatility['rv10d']:.1%}, ratio {volatility['ratio']:.2f}.",
        })

    if not open_positions:
        if gate_choice is not None:
            lines.append({
                "label": "Would trade", "cls": "good",
                "detail": f"{gate_choice['distance']:.0%}-OTM, ${gate_choice['width']:.0f}-wide spread clears the evidence bar "
                          f"({gate_choice['cushion_se']:.2f} SE cushion), if guards and reviewer also clear it.",
            })
        else:
            lines.append({"label": "Won't trade", "cls": "bad", "detail": "No trade shape currently clears the evidence bar."})

    return lines


def build_track_record() -> dict:
    result = {"equity_curve": None, "stats": None, "validation": None, "false_trip": None, "errors": {}}

    curve_path = "output/data/equity_curve.csv"
    try:
        curve_df = pd.read_csv(curve_path, parse_dates=["entry"])
        curve_df = curve_df.sort_values("entry")

        def _max_dd(s: pd.Series) -> float:
            return float((s.cummax() - s).max())

        def _worst_year(df: pd.DataFrame, col: str) -> dict:
            by_year = df.groupby(df["entry"].dt.year)[col].sum()
            return {"year": int(by_year.idxmin()), "pnl": float(by_year.min())}

        dd_u, dd_f = _max_dd(curve_df["cum_pnl_unfiltered"]), _max_dd(curve_df["cum_pnl_filtered"])
        result["equity_curve"] = {
            "dates": curve_df["entry"].dt.strftime("%Y-%m-%d").tolist(),
            "cum_pnl_unfiltered": curve_df["cum_pnl_unfiltered"].round(3).tolist(),
            "cum_pnl_filtered": curve_df["cum_pnl_filtered"].round(3).tolist(),
            "spy_indexed": curve_df["spy_indexed"].round(2).tolist(),
            "cash_indexed": curve_df["cash_indexed"].round(2).tolist(),
        }
        result["stats"] = {
            "dd_unfiltered": dd_u, "dd_filtered": dd_f,
            "worst_year_unfiltered": _worst_year(curve_df, "pnl_unfiltered"),
            "worst_year_filtered": _worst_year(curve_df, "pnl_filtered"),
            "weeks_traded": int(curve_df["traded"].sum()), "weeks_total": int(len(curve_df)),
        }
    except Exception as e:
        result["errors"]["equity_curve"] = str(e)

    try:
        from pipeline.backtest.reconstruct import _load_real_flagship_weeks, validate_reconstruction

        real_weeks = _load_real_flagship_weeks()
        d = real_weeks.copy()
        from pipeline.backtest.reconstruct import _spread_credit

        d["modelled"] = d.apply(lambda r: _spread_credit(r, FITTED_A, FITTED_B), axis=1)
        correlation = float(np.corrcoef(d["modelled"], d["credit"])[0, 1])
        report = validate_reconstruction(real_weeks, FITTED_A, FITTED_B)
        quartiles = [
            {"bucket": idx, "n": int(row.n), "vix9d_mean": float(row.vix9d_mean),
             "real_credit": float(row.real_credit), "model_credit": float(row.model_credit),
             "ratio": float(row.model_over_real)}
            for idx, row in report.iterrows()
        ]
        result["validation"] = {"correlation": correlation, "quartiles": quartiles, "band": [0.95, 1.05]}
    except Exception as e:
        result["errors"]["validation"] = str(e)

    try:
        from pipeline.backtest.spread_backtest import _load_spy_closes
        from pipeline.io_utils import coerce_win_column
        from pipeline.risk.false_trip import false_trip_rate_term_structure

        results = coerce_win_column(pd.read_csv("output/data/spread_backtest_results.csv"))
        r = false_trip_rate_term_structure(results, 0.03, 5.0)
        by_regime = [
            {"regime": idx, "n": int(row.n), "blocked": int(row.blocked), "blocked_pct": float(row.blocked_pct)}
            for idx, row in r["by_regime"].iterrows()
        ]
        result["false_trip"] = {
            "blocked": r["blocked"], "n_winners": r["n_winners"], "blocked_pct": r["blocked_pct"],
            "by_regime": by_regime, "bar": 0.30,
        }
    except Exception as e:
        result["errors"]["false_trip"] = str(e)

    return result


def build_decisions() -> dict:
    log_df = read_log()
    if log_df.empty:
        return {"summary": {"total": 0, "traded": 0, "guard_blocked": 0, "reviewer_vetoed": 0, "dry_run": 0}, "rows": []}

    log_df = log_df.copy()
    log_df["category"] = log_df.apply(_category, axis=1)
    log_df["reason"] = log_df.apply(_reason, axis=1)
    log_df = log_df.sort_values("timestamp", ascending=False)

    # A reprice (submit_with_retry) logs both a SOLD proposal row and a
    # FILLED confirmation row for the same pair -- one real trade, two rows.
    # Count distinct pairs, not rows, so a reprice doesn't inflate "Traded".
    traded_pairs = log_df[log_df["category"] == "Traded"][["short_symbol", "long_symbol"]].dropna().drop_duplicates()
    summary = {
        "total": len(log_df),
        "traded": len(traded_pairs),
        "guard_blocked": int((log_df["category"] == "Guard-blocked").sum()),
        "reviewer_vetoed": int((log_df["category"] == "Reviewer-vetoed").sum()),
        "dry_run": int((log_df["category"] == "Dry run").sum()),
    }
    rows = log_df[["timestamp", "mode", "outcome", "category", "reason"]].head(200).to_dict(orient="records")
    return {"summary": summary, "rows": [{k: _clean(v) for k, v in row.items()} for row in rows]}


def build_evidence() -> dict:
    gate_path = "output/data/evidence_gate_results.csv"
    if not os.path.exists(gate_path):
        return {"current_pick": None, "rows": []}
    gate_df = pd.read_csv(gate_path)
    from pipeline.options.selector import choose_distance_width

    choice = choose_distance_width(gate_df)
    current_pick = None
    if choice is not None:
        current_pick = {
            "distance": float(choice["distance"]), "width": float(choice["width"]),
            "cushion_se": float(choice["cushion_se"]),
            "n_survivors": int(gate_df["passes_gate"].sum()), "n_total": int(len(gate_df)),
        }
    rows = []
    for _, row in gate_df.iterrows():
        rows.append({
            "distance": float(row["distance"]), "width": float(row["width"]), "n": int(row["n"]),
            "win_rate": float(row["win_rate"]), "required_win_rate": float(row["required_win_rate"]),
            "cushion_se": float(row["cushion_se"]), "mean_net_pnl": float(row["mean_net_pnl"]),
            "passes_gate": bool(row["passes_gate"]),
        })
    return {"current_pick": current_pick, "rows": rows}


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    overview = build_overview()
    print(f"overview: status={overview['status']['word']!r}, market_error={overview.get('market_error')}, "
          f"open_positions={len(overview['open_positions'])}")
    assert overview["status"]["word"], "status word must never be empty"

    track_record = build_track_record()
    print(f"track_record: errors={track_record['errors']}")
    if track_record["validation"] is not None:
        lo, hi = track_record["validation"]["band"]
        for q in track_record["validation"]["quartiles"]:
            assert lo <= q["ratio"] <= hi, f"validation quartile {q} outside band -- should have raised upstream"
        print(f"  validation correlation={track_record['validation']['correlation']:.3f}, "
              f"{len(track_record['validation']['quartiles'])} quartiles all inside {track_record['validation']['band']}")
    if track_record["false_trip"] is not None:
        assert track_record["false_trip"]["blocked_pct"] <= track_record["false_trip"]["bar"], \
            "false-trip rate exceeds its own bar -- should be flagged, not silently shipped"
        print(f"  false-trip blocked_pct={track_record['false_trip']['blocked_pct']:.3f} (bar {track_record['false_trip']['bar']})")

    decisions = build_decisions()
    print(f"decisions: {decisions['summary']}")

    evidence = build_evidence()
    print(f"evidence: current_pick={evidence['current_pick']}, {len(evidence['rows'])} rows")

    for name, data in [("overview", overview), ("track_record", track_record), ("decisions", decisions), ("evidence", evidence)]:
        path = OUT_DIR / f"{name}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"wrote {path}")
