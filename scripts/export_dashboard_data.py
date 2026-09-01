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
    if outcome == "SOLD":
        n = _clean(latest_row.get("proposed_contracts"))
        return {"cls": "good", "word": "Trading",
                "rest": f"opened {latest_row.get('short_symbol')} / {latest_row.get('long_symbol')}, {n if n is not None else '?'} contract(s).",
                "timestamp": ts}
    if outcome == "DRY_RUN":
        return {"cls": "neutral", "word": "Dry run",
                "rest": f"would have opened {latest_row.get('short_symbol')} / {latest_row.get('long_symbol')} -- no real order sent.",
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
        rows.append({"stage": "3. Reviewer", "cls": "neutral", "detail": "--"})
        rows.append({"stage": "4. Order", "cls": "neutral", "detail": "--"})
        return rows

    guards_checked = _clean(latest_row.get("guards_checked"))
    guards_failed = latest_row.get("guards_failed")
    has_failures = isinstance(guards_failed, list) and len(guards_failed) > 0
    if guards_checked is None:
        rows.append({"stage": "2. Guards", "cls": "neutral", "detail": "not reached today"})
    elif has_failures:
        rows.append({"stage": "2. Guards", "cls": "bad",
                     "detail": f"{int(guards_checked)} checked -- blocked: " + "; ".join(str(g) for g in guards_failed)})
    else:
        rows.append({"stage": "2. Guards", "cls": "good", "detail": f"all {int(guards_checked)} passed"})

    reviewer_decision = _clean(latest_row.get("reviewer_decision"))
    if reviewer_decision is None:
        rows.append({"stage": "3. Reviewer", "cls": "neutral", "detail": "not reached today"})
    else:
        reviewer_reason = _clean(latest_row.get("reviewer_reason")) or ""
        r_cls = "good" if reviewer_decision == "APPROVE" else ("bad" if reviewer_decision == "VETO" else "neutral")
        rows.append({"stage": "3. Reviewer", "cls": r_cls, "detail": f"{reviewer_decision} -- {reviewer_reason}"})

    outcome_map = {
        "SOLD": ("good", "sent live"),
        "DRY_RUN": ("neutral", "dry run, no order sent"),
        "SKIPPED": ("bad", "never reached -- blocked upstream"),
        "CLOSED": ("neutral", "position closed"),
        "EMERGENCY_CLOSE_ORPHAN": ("bad", "emergency close"),
    }
    outcome = _clean(latest_row.get("outcome"))
    o_cls, o_detail = outcome_map.get(outcome, ("neutral", str(outcome) if outcome else "no decision today"))
    rows.append({"stage": "4. Order", "cls": o_cls, "detail": o_detail})
    return rows


def _category(row) -> str:
    outcome = row.get("outcome")
    if outcome == "SOLD":
        return "Traded"
    if outcome == "DRY_RUN":
        return "Dry run"
    if outcome == "SKIPPED":
        reasons = row.get("guards_failed")
        if isinstance(reasons, list) and any(str(r).startswith("REVIEWER_VETO") for r in reasons):
            return "Reviewer-vetoed"
        return "Guard-blocked"
    return "Other"


def _reason(row) -> str:
    if row.get("outcome") == "SOLD":
        return f"{row.get('short_symbol')} / {row.get('long_symbol')}, {row.get('proposed_contracts')} contract(s)"
    if row.get("outcome") == "SKIPPED":
        reasons = row.get("guards_failed")
        return "; ".join(str(r) for r in reasons) if isinstance(reasons, list) and reasons else ""
    if row.get("outcome") == "CLOSED":
        return str(row.get("close_reason", ""))
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
                v_cls, v_text = "good", "Rich -- selling is well compensated right now"
            elif ratio < 0.85:
                v_cls, v_text = "bad", "Thin -- selling isn't well compensated right now"
            else:
                v_cls, v_text = "neutral", "Fair -- normal compensation"
            volatility = {"vix9d_decimal": vix9d_decimal, "rv10d": rv10d, "ratio": ratio, "verdict_class": v_cls, "verdict_text": v_text}
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
    }


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

    summary = {
        "total": len(log_df),
        "traded": int((log_df["category"] == "Traded").sum()),
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
