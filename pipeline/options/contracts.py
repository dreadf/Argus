"""
OCC option symbol construction/parsing and the SPY expiry calendar.

Pure functions, no network calls. Alpaca's option symbols follow the OCC
convention without the underlying's space-padding to 6 characters, e.g.
"SPY260905P00740000" for a SPY $740 put expiring 2026-09-05.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

_SYMBOL_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def build_occ_symbol(root: str, expiry: date, right: str, strike: float) -> str:
    if right not in ("C", "P"):
        raise ValueError(f"right must be 'C' or 'P', got {right!r}")
    strike_thousandths = round(strike * 1000)
    if strike_thousandths <= 0 or strike_thousandths > 99_999_999:
        raise ValueError(f"strike {strike} out of representable range")
    return (
        f"{root.upper()}"
        f"{expiry.strftime('%y%m%d')}"
        f"{right}"
        f"{strike_thousandths:08d}"
    )


def parse_occ_symbol(symbol: str) -> dict:
    m = _SYMBOL_RE.match(symbol)
    if not m:
        raise ValueError(f"not a valid OCC symbol: {symbol!r}")
    root, yymmdd, right, strike_digits = m.groups()
    yy, mm, dd = int(yymmdd[0:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    year = 2000 + yy
    return {
        "root": root,
        "expiry": date(year, mm, dd),
        "right": right,
        "strike": int(strike_digits) / 1000,
    }


def expiries_in_window(
    today: date,
    min_dte: int = 7,
    max_dte: int = 11,
    weekdays: tuple[int, ...] = (0, 2, 4),
) -> list[date]:
    """Calendar dates matching `weekdays` whose DTE from `today` falls in
    [min_dte, max_dte]. Does not account for exchange holidays -- callers must
    still confirm a chosen expiry actually exists via a live chain fetch
    (Guard #2, data sanity) before trading it.
    """
    if min_dte > max_dte:
        raise ValueError("min_dte must be <= max_dte")
    out = []
    for dte in range(min_dte, max_dte + 1):
        d = today + timedelta(days=dte)
        if d.weekday() in weekdays:
            out.append(d)
    return out


if __name__ == "__main__":
    # Self-checks, run with: python -m pipeline.options.contracts
    sym = build_occ_symbol("SPY", date(2026, 9, 5), "P", 740.0)
    assert sym == "SPY260905P00740000", sym
    parsed = parse_occ_symbol(sym)
    assert parsed == {"root": "SPY", "expiry": date(2026, 9, 5), "right": "P", "strike": 740.0}, parsed

    # Round-trip across a range of strikes, including a non-integer one.
    for strike in (1.5, 5.0, 99.5, 740.0, 4999.5):
        for right in ("C", "P"):
            s = build_occ_symbol("SPY", date(2026, 12, 18), right, strike)
            p = parse_occ_symbol(s)
            assert p["strike"] == strike, (s, p)
            assert p["right"] == right

    # Expiry window: SPY lists Mon/Wed/Fri, so a 7-11 DTE window from a Monday
    # anchor should surface exactly the Mon/Wed/Fri dates in that span.
    anchor = date(2026, 8, 31)  # Monday
    exps = expiries_in_window(anchor, 7, 11)
    assert all(d.weekday() in (0, 2, 4) for d in exps), exps
    assert all(7 <= (d - anchor).days <= 11 for d in exps), exps
    print("expiries_in_window(2026-08-31, 7, 11) ->", exps)

    print("All contracts.py self-checks passed.")
