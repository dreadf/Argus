# Build Log

Alpaca AI Trading Agents Hackathon. Deadline Fri Sep 4 2026, 11:00 ET (22:00 WIB).

Rules for this file, from `OPTIONS_SYSTEM_PLAN.md` Part 0C:

1. Tick only when **verified**, not when written. "Code exists" is not "works."
2. When something fails, add a one line note and leave it unticked. The failures are the interesting part of the log.
3. Update at the end of each work block, not the end of the day.
4. Every unticked box at Friday 09:00 is either cut or a known gap. Nothing gets silently dropped.

---

## Mon Aug 31 - build day

### 0. Plan into the repo
- [x] `OPTIONS_SYSTEM_PLAN.md` written
- [x] `VOLATILITY_ML_PLAN.md` written
- [x] `PROGRESS.md` seeded
- [x] `LICENSE` (MIT) added
- [x] `.gitignore` fixed so the plan docs are tracked
- [x] Committed (8227f43, c0e517e)

### 1. Accounts and access
- [x] Alpaca paper account confirmed (account PA3LRFJ9JMVX, $100,000 equity, zero positions, zero orders on record)
- [x] Options level 3 confirmed on the account (`options_approved_level: 3`, verified live via `get_account()`)
- [x] Keys in `.env` as `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (kept the pipeline's existing names rather than `ALPACA_PAPER_KEY` -- same account already used read-only for market data, never traded)
- [x] `GEMINI_API_KEY` in `.env`
- [x] MCP server running, read-only toolset confirmed -- `pipeline/mcp/reviewer_server.py` builds the server from a hand-picked operation allowlist rather than the package's `ALPACA_TOOLSETS` env var, because its "trading" toolset bundles safe reads (positions, orders) with dangerous writes (close position, exercise, and the order-placement overrides) under one name. 47 tools registered, all `get_*`/`list_*`/`search_*`/`fetch_*`.
- [x] `place_option_order` verified **absent** from the Reviewer's tools -- confirmed programmatically (not present in the 47 registered tools, and never even defined since `register_order_tools` is never called). Also ran the account-state drill: `get_account_info` through MCP returned the same account number, equity, and options level as the direct `alpaca-py` call.

### 2-4. Read path
- [x] `options/contracts.py` OCC symbols, expiry calendar -- round-trip build/parse verified across integer and half-dollar strikes, both rights; expiry window verified against a real Monday anchor. No holiday awareness (see note below); relies on the live chain fetch to catch a listed-but-nonexistent expiry.
- [x] `options/chain.py` fetches a real chain with retry and liquidity filter -- verified live against the real market: spot $769.28, 200 SPY puts across the two Sep 9/11 expiries in the 7-11 DTE window, prices rise monotonically with strike, 70/100 pass the liquidity filter at the Sep 11 expiry. Found and fixed a real bug: Alpaca's `get_option_contracts` and `get_option_chain` both silently default to calls only when `type` is omitted -- an unfiltered request returned 200 calls and 0 puts.
- [ ] `options/vol.py` annualized realized vol on log returns

### 5. The backtest (the long pole)
- [ ] `backtest/spread_backtest.py` replays expired contracts
- [ ] Sweeps distance **and** width
- [ ] Self checks pass: prices rise with strike, real session dates only
- [ ] `backtest/evidence_gate.py` computes SE cushion per distance
- [ ] Result recorded in `EXPERIMENT.md`
- [ ] **Provisional numbers confirmed or corrected**

### 6-9. Decision path
- [ ] `risk/options_config.py`
- [ ] `risk/guards.py` (14 guards)
- [ ] `options/selector.py` (9 picker rules)
- [ ] `audit/log.py` schema first
- [ ] `execution/broker.py` + `orders.py`, dry run default

### 10-12. Manage and show
- [ ] `execution/monitor.py` 15 minute loop
- [ ] `ui/app.py` renders from files with zero positions
- [ ] Deployed to Streamlit Cloud with `CONTROLS_ENABLED=false`

### Tonight, 20:30 WIB
- [ ] Decision point: smoke test tonight, or print the spread and wait

---

## Tue Sep 1 - go live
- [ ] Anything unfinished from Monday
- [ ] `execution/recovery.py`
- [ ] **First live order, MANUAL, 1 contract**
- [ ] Fill confirmed, both legs present, audit row written
- [ ] Net limit price sign convention verified
- [ ] Switch to AUTO

## Wed Sep 2 - buffer
- [ ] Experiment 11 if there is room (naive vs HAR-RV vs XGBoost)
- [ ] Otherwise start submission assets early

## Thu Sep 3 - submission assets
- [ ] Pitch video, MP4, under 5 minutes
- [ ] Slide deck, PDF
- [ ] Cover image, 16:9
- [ ] One page write up: AI logic, risk gates, Alpaca infrastructure
- [ ] README
- [ ] Repo made public
- [ ] Close anything at 50% profit

## Fri Sep 4 - submit
- [ ] Submission form dry run, every field
- [ ] Final trade 20:45 WIB
- [ ] Freeze 21:15, screenshots of equity, positions, audit log
- [ ] **Submit 21:30 WIB**

---

## Verification drills (Part 8)
- [ ] Dry run end to end sends nothing
- [ ] Run twice, second run submits nothing
- [ ] Partial fill drill
- [ ] Reconcile drill
- [ ] Pin risk drill
- [ ] Public deploy safety drill, controls absent
- [ ] Cold open drill, renders with zero positions
- [ ] Secrets drill, no keys in repo or page source

---

## Notes and failures

*(Record what broke and why. Leave the box unticked.)*

- **The plan's "no market holidays fall inside the window" claim was wrong once building actually started today (Mon Aug 31).** The 7-11 DTE window computed live reaches Sep 7-11, and **Sep 7, 2026 is Labor Day** (first Monday of September). `contracts.expiries_in_window` is a pure weekday filter and has no holiday awareness, so it lists Sep 7 as a candidate -- it will simply come back empty when `chain.py` fetches it live, and Guard #2 (data sanity) skips on empty/stale chain data, so this is not a safety gap. Noted here because the plan stated a false certainty; the actual Picker rule (#6: choose from expiries that exist) already covers it correctly by construction.
