"""
Read-only Alpaca proxy so the published dashboard can show live account
state without ever putting API keys in the page.

WHY THIS EXISTS
public/ is served as plain static files and has no server. For the browser
to poll Alpaca directly, the API keys would have to be embedded in the page
-- readable by anyone who opens it, and sufficient to place trades. This
function holds the keys instead: they live in Vercel's environment, never in
the page, and the browser only ever sees the answer.

WHAT IT WILL AND WILL NOT DO
One GET: account equity/cash/buying-power and open positions. Nothing else.
There is no code path here that places, cancels, or modifies an order, and
it refuses to run against a non-paper configuration for the same reason
run_agent.py does (this system's own paper-trading discipline, not a new one
invented for this function).

It is public, so treat what it returns as public: equity and open positions
are visible to anyone with the URL. That is the accepted trade-off for a
public demo dashboard -- and precisely why nothing here can act on the
account.

Deploy target: Vercel (api/account.py -> /api/account). Stdlib only, no
build step, no dependency on the rest of this repo's pipeline package --
Vercel's Python runtime for a bare function like this doesn't install repo
requirements.txt, so importing pipeline.execution.broker here would fail at
import time in production even though it works locally.
"""

import datetime
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

PAPER_BASE = "https://paper-api.alpaca.markets/v2"
TIMEOUT = 6  # two calls, comfortably inside Vercel's default function limit


def _get(path: str, key: str, secret: str):
    req = urllib.request.Request(
        PAPER_BASE + path,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "User-Agent": "evidence-gate-dashboard/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
        return json.loads(fh.read().decode("utf-8"))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build():
    key = (os.environ.get("ALPACA_API_KEY") or "").strip()
    secret = (os.environ.get("ALPACA_SECRET_KEY") or "").strip()
    if not key or not secret:
        return 503, {"available": False, "reason": "no credentials configured"}

    # PAPER_BASE above is hardcoded, not env-gated -- same discipline as
    # pipeline/execution/broker.py, which passes paper=True directly rather
    # than reading a flag. There is no live-trading branch in this file for
    # an env-var check to be guarding, so unlike the reference this proxy is
    # based on, no ALPACA_PAPER_TRADE flag is required here.

    try:
        acct = _get("/account", key, secret)
        positions = _get("/positions", key, secret)
    except urllib.error.HTTPError as exc:
        return 502, {"available": False, "reason": f"alpaca returned HTTP {exc.code}"}
    except Exception as exc:
        return 502, {"available": False, "reason": type(exc).__name__}

    return 200, {
        "available": True,
        # When the account was actually read -- shown on the page, so a
        # stale answer is visible as stale rather than passed off as current.
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "equity": _num(acct.get("equity")),
        "cash": _num(acct.get("cash")),
        "options_buying_power": _num(acct.get("options_buying_power") or acct.get("buying_power")),
        "positions": [
            {
                "symbol": p.get("symbol"),
                "side": p.get("side"),
                "qty": _num(p.get("qty")),
                "avg_entry_price": _num(p.get("avg_entry_price")),
                "current_price": _num(p.get("current_price")),
                "unrealized_pl": _num(p.get("unrealized_pl")),
            }
            for p in positions
        ],
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        # Never let this return a bare 500 -- a crashed function shows the
        # host's generic error page, which says nothing about what went
        # wrong. Report the failure as JSON so the cause is visible at the
        # URL itself, matching every other part of this system's "log the
        # failure, don't hide it" discipline.
        try:
            status, body = build()
        except Exception as exc:
            status = 500
            body = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
