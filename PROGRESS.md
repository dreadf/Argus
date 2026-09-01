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
- [x] `options/contracts.py` OCC symbols, expiry calendar, round-trip build/parse verified across integer and half-dollar strikes, both rights; expiry window verified against a real Monday anchor. No holiday awareness (see note below); relies on the live chain fetch to catch a listed-but-nonexistent expiry.
- [x] `options/chain.py` fetches a real chain with retry and liquidity filter, verified live against the real market: spot $769.28, 200 SPY puts across the two Sep 9/11 expiries in the 7-11 DTE window, prices rise monotonically with strike, 70/100 pass the liquidity filter at the Sep 11 expiry. Found and fixed a real bug: Alpaca's `get_option_contracts` and `get_option_chain` both silently default to calls only when `type` is omitted, an unfiltered request returned 200 calls and 0 puts.
- [x] `options/vol.py` annualized realized vol on log returns -- self-checks pass (zero vol on flat/pure-drift series, sane range against `raw_SPY.csv`, live fetch matches the CSV's overlapping window: 10-day RV 0.0789 stale vs 0.0790 live). Found the account's data subscription rejects recent SIP bars ("does not permit querying recent SIP data"); fixed by requesting the IEX feed explicitly, which is free-tier eligible and sufficient for daily closes.

### 5. The backtest (the long pole)
- [x] `backtest/spread_backtest.py` replays expired contracts -- 128 candidate Fridays from 2024-02-01, real historical option closes fetched live, settled at intrinsic value against real SPY closes
- [x] Sweeps distance **and** width -- 6 distances x 4 widths = 24 cells, 2,921 of 3,072 with valid data (rest missing due to zero-volume deep-OTM contracts, not a defect)
- [x] Self checks pass: prices rise with strike (58/2921 cells with small negative credit, all concentrated at illiquid 4-6% distances, immaterial to the 3% result); real session dates only (entry/expiry dates come from `raw_SPY.csv`'s own index)
- [x] `backtest/evidence_gate.py` computes SE cushion per distance -- 3 cells clear 2 SE, all at 3% distance (widths $1/$2/$5, cushions 3.28/2.97/2.28 SE). **These cushions assume zero slippage/trading cost** -- `EXPERIMENT.md`'s Experiment 11 entry has the full sensitivity table; the $1-width result does not survive a realistic $0.02/share haircut, and real quoted spreads on these contracts run $0.01-$0.05 wide.
- [x] Result recorded in `EXPERIMENT.md` as **Experiment 11** (renumbered the volatility ML ladder from 11-15 to 12-16 to make room, since this backtest reproduction slots in chronologically before Wednesday's volatility forecasting experiment)
- [x] **Provisional numbers confirmed or corrected** -- confirmed and stronger than the provisional estimate: real cushion is 2.28-3.28 SE at 3% distance, versus the hand-computed provisional estimate of 1.8 SE (which was below the bar). 1% and 2% distances confirmed underpaid, matching the provisional finding.

### 6-9. Decision path
- [x] `risk/options_config.py` -- found and fixed a real inconsistency while wiring it up: the plan's Guard #8 credit/width floor (0.08, a judgment call per Part 9B) would have blocked **every** cell the Experiment 11 evidence gate approved (the 3% distance survivors measure 0.055-0.068 credit/width). Lowered to 0.04.
- [x] `risk/guards.py` (14 guards) -- pure functions on plain dicts, unit-tested against fake account states: clean proposal passes all 14; exactly at the 5%/8% drawdown lines blocks, one dollar under passes; at the 4-position cap blocks; IV=None blocks on data-sanity grounds.
- [x] `options/selector.py` (9 picker rules) -- resolved the tie-break the plan left open (three cells cleared the evidence gate at 3% distance): picks the highest cushion_se, not the highest P&L, decided in advance rather than after seeing which paid more. Ran live end to end: picked 3%/$1 width, real strikes $746/$745 (2026-09-09 expiry), credit $7.00/contract, sized 32 contracts -- then correctly **blocked by the liquidity guard** (real open interest on the $746 strike is 22, far below the 500 minimum). The system declining a real trade it can't defend is the design working, not a bug.
- [x] `audit/log.py` schema first -- append-only JSONL, 21 fixed fields, unknown fields rejected loudly (schema drift must be a deliberate edit, not a typo). Self-checks: missing log file reads back as an empty but correctly-shaped DataFrame (cold-open requirement), append creates the file/dir, two entries append in order rather than overwriting.
- [x] `execution/broker.py` + `orders.py`, dry run default -- broker.py reads live account/position/clock state (verified live: $100,000 equity, options level 3, market closed, next open correctly shown). orders.py builds the real two-legged MLEG order (SELL_TO_OPEN short / BUY_TO_OPEN long) and defaults to dry_run=True everywhere; self-check confirms nothing is sent. **Net-price sign convention is explicitly flagged as unverified** in the module docstring and printed prominently in dry-run output -- Alpaca's docs don't state it, so it can only be confirmed on Tuesday's first live 1-contract fill (Verification #7), not assumed here.

### 10-12. Manage and show
- [x] `execution/monitor.py` 15 minute loop -- the four exit checks in priority order (one-leg orphan, day-before-expiry, profit target, hard drawdown). Self-checks: fresh position holds; profit target fires at <=50% buyback; day-before-expiry forces a close even when the profit target isn't hit (priority ordering verified); orphaned short leg triggers emergency close; hard drawdown triggers halt; build_close_order/build_emergency_single_leg_close carry the correct BUY_TO_CLOSE/SELL_TO_CLOSE intents.
- [x] `ui/app.py` renders from files with zero positions -- reads the (now committed, no longer gitignored) evidence gate CSV, the audit log, and live account state if reachable, each wrapped so a missing file or broker error renders a plain message instead of a stack trace. Ran live via `streamlit run`: HTTP 200, no exceptions. Cold-open drill run directly (temporarily removed the evidence gate CSV): falls through to the "not yet computed" warning cleanly, no crash. Found and fixed the evidence-gate/backtest CSVs being gitignored, which would have left a fresh Streamlit Cloud deploy with nothing to show -- added `.gitignore` exceptions for those two specific result files.
- [ ] Deployed to Streamlit Cloud with `CONTROLS_ENABLED=false`

### Tonight, 20:30 WIB
- [ ] Decision point: smoke test tonight, or print the spread and wait

---

## Tue Sep 1 - go live

### Code hardening, done before market open (see `EXPERIMENT.md` Experiment 12 for full detail)
- [x] Strike rounding fixed to a $5 increment (`options/config.py:LIQUID_STRIKE_INCREMENT`) -- the live-blocked $746/OI-22 strike from Monday's run is now $745/OI-386 on the same live re-check, strictly more OTM than the raw target, never less
- [x] `choose_expiry` restricted to Friday only -- found it was silently able to select a Wednesday expiry the backtest never tested (`_fridays_between` is Friday-only); confirmed live, the untested Wednesday's identical strike quoted OI 386 vs the Friday's OI 35,231. Combined with the strike fix, took the live pipeline from BLOCKED to **PASS (all 15 guards)** on real market data, same day
- [x] Evidence gate's cost model actually fed a real number -- `DEFAULT_SLIPPAGE_PER_SHARE` was always 0.0 in practice despite the formula supporting it. Measured live (not guessed): every liquid candidate strike quoted the $0.01 minimum tick both legs, giving $0.01/spread via the half-spread convention. Selector's tie-break moved from raw `cushion_se` (favored 3%/$1, which costs destroy) to cost-adjusted `mean_net_pnl` (now picks 3%/$5, the width with real depth)
- [x] Risk-limit ordering fixed -- `CRASH_DAY_BUDGET_PCT` 0.12 exceeded `DRAWDOWN_HARD_PCT` 0.08, meaning the hard stop could never actually bind. Set to 0.06 (room for 2 positions at the 3% cap); verified with a new guards.py self-check that fully-committed budget cannot exceed the hard stop
- [x] Reviewer stage built (`pipeline/reviewer/reviewer.py`) -- Picker -> Guard -> **Reviewer** -> order, wired into `run_agent.py`. Gemini may APPROVE/SHRINK/VETO a Guard-passed proposal; the "never raise size, never originate a proposal" property is enforced by a pure, network-free function (`apply_reviewer_decision`), not the prompt. 9 offline self-checks including adversarial cases (a simulated 5x-size-up response is clamped to 1.0x; a simulated network failure fails closed to VETO without crashing the run) plus one live end-to-end call (real MCP account fetch + real Gemini call, decision APPROVE)
- [x] SPY history extended to 2016 for reconstruction work, **without touching `raw_SPY.csv`** or `config.py` (a concurrent session's ML track depends on that file staying untouched) -- `fetch_spy_history.py` writes a separately-named `raw_SPY_long.csv`. Found the SIP feed rejects a single request spanning the full 2016-2026 range ("does not permit querying recent SIP data", reproduced 3x, not transient) but succeeds when the same total range is split into ~2-year chunks; confirmed against an independent earlier fetch (2675 overlapping days, mean abs diff $0.005)
- [x] VIX/VIX9D/VIX3M cached from CBOE (`pipeline/data/vix.py`) with a fetch-timestamp meta file; a stale or missing cache fails closed rather than silently proceeding (5 self-checks, including an artificially-backdated cache and a genuinely-missing one)
- [x] Ten-year reconstruction built (`pipeline/backtest/reconstruct.py`) with a **regime-split validation gate that fails the build**, not just a formality -- an earlier informal version of this same reconstruction (trailing RV instead of VIX9D) had aggregate correlation 0.649 but priced calm weeks at 3% of reality and volatile weeks at 125%, producing a false finding that had to be retracted before reaching this file. The corrected VIX9D model passes per-quartile at 0.98-1.03. Found and corrected a real discrepancy against that same earlier informal analysis: the reconstruction must use the SAME $5-increment strike rule the live system trades, which moves 2018's total from -16.40 to **-9.89** and the full-period total from +38.28 to **+24.03** -- both now the authoritative figures
- [x] `check_term_structure` guard built and wired -- blocks when VIX3M/VIX9D falls below its own trailing 33rd percentile (walk-forward, never a full-sample constant), fails closed on stale data, replaces the RV(10d) leg of the old volatility-regime guard. False-trip tested **split by VIX9D quartile with bucket counts printed** (30-31 weeks per bucket, not the 4 the old guard's aggregate-only test rested on): 0% blocked in the two calmest quartiles, 16.7%/64.5% in active/most-volatile -- the shape a correctly-targeted guard should have, aggregate 20.3% comfortably under the 30% false-trip bar
- [x] Audit log integrity: two accidental test-contaminated rows (written while verifying the above end-to-end, market genuinely closed at the time) found and removed from `output/audit/decisions.jsonl`, restoring it to only genuine same-day decisions
- [x] Missing dashboard visualization found and built: `app.py` only ever rendered Account/evidence-gate/decision-log -- the plan's own "single most persuasive image the project can produce" (S1, the ten-year equity curve) was never wired in. Added `build_equity_curve()` (walk-forward VIX-filter mask, same 33rd-percentile rule the live guard uses) plus the chart, drawdown/worst-year/weeks-traded metrics, and a clearly-labeled separate SPY/cash shape-comparison panel
- [x] `execution/recovery.py` built -- the module the plan calls "the one that must be correct even if everything else is rough." Three jobs, all wired in: (1) `reconcile_positions()` treats the broker's real positions as truth, blocks opening a new position if it holds an option leg the audit log doesn't recognize; wired into `run_agent.py` before every new open. (2) `verify_fill_or_emergency_close()` confirms both legs filled equally right after a LIVE submission (not waiting up to 15 min for the next monitor cycle) -- a mismatch triggers an immediate market close of the excess and halts for the day. (3) heartbeat wired into `monitor.py`'s 15-minute loop on every cycle including no-ops, fixing a real gap between that module's docstring and its actual code. 8 self-checks

### Still ahead today
- [x] **T-LIVE: first live order, AUTO, 6 contracts** -- SPY 735/730 put credit spread, 3%/$5, run via `run_agent.py --live`. Found and fixed a real bug first: `_already_decided_today()` treated any SKIPPED row as "today is decided," including a pre-market "check_market_open" bounce logged hours earlier -- without the fix, the system would have refused to ever evaluate today even after the market opened. Added `_is_real_decision()` to distinguish pre-flight bounces (market closed, transient fetch failures) from real evaluations, with 4 self-checks
- [x] First submission (net -0.27) sat unfilled 28 minutes as the market moved the mid down to -0.22 -- cancelled, refreshed the mid, resubmitted at -0.22
- [x] Fill confirmed: **filled at -0.23**, both legs present (`SHORT -6 SPY735P @ 0.93`, `LONG +6 SPY730P @ 0.70`), account cash increased by $137.70 (~0.23 x 100 x 6)
- [x] **Net limit price sign convention CONFIRMED**: negative = net credit -- cash going up on a negative fill price is only consistent with that reading. Updated `orders.py`'s docstring and all four UNVERIFIED markers to record the confirmation (order id `ae5cf304-5837-418f-b5c6-54e5d1fab767`)
- [ ] Switch to AUTO -- mode is already logged as AUTO for this fill; still need to confirm the monitor cron picks this position up correctly for exit management
- [ ] Discovered gap, not yet fixed: `orders.py`'s own docstring describes a "wait 5 min -> improve $0.01 -> cancel and skip" retry rule that was never actually implemented in `run_agent.py` -- today's stuck order had to be handled manually. Worth building before relying on this unattended.
- [ ] Deploy to Streamlit Cloud (`CONTROLS_ENABLED=false`)

## Wed Sep 2 - buffer
- [ ] Experiment 12 if there is room (naive vs HAR-RV vs XGBoost)
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
- [x] Dry run end to end sends nothing -- built `pipeline/run_agent.py` (the daily entry point tying Picker/Guard/orders together, was missing entirely). Ran the accepted-path end to end: prints the bet, writes one audit row, and a direct account check confirms zero orders exist on the account. Also ran the real blocked-path live (market genuinely closed, then genuinely blocked by the liquidity guard) -- both logged correctly.
- [x] Run twice, second run submits nothing -- found and fixed a real bug: the idempotency check compared the audit log's UTC timestamps against the local machine's date (WIB, UTC+7), which disagree for most of the day, so a second same-day run was writing a duplicate row instead of no-op'ing. Fixed to compare UTC dates on both sides; re-verified two consecutive runs produce exactly one log row.
- [x] Partial fill drill -- `execution/recovery.py` self-check simulates a one-legged fill (short filled, long never did) and confirms `verify_fill_or_emergency_close` closes the orphaned short at market and signals halt. Not yet exercised against a real live fill (needs T-LIVE)
- [x] Reconcile drill -- `reconcile_positions` self-check simulates a broker option position the audit log has never logged and confirms it blocks new opens (`safe_to_open: False`); a stale audit-only row (log says open, broker shows nothing) correctly does not block. Not yet exercised by manually opening a position outside the bot on the live account
- [x] Pin risk / expiry-rule drill -- `monitor.py` self-check confirms a position one day from expiry closes unconditionally, overriding even an unmet profit target; DTE<=1 catches both "day before" and "on expiry day" (0 DTE)
- [ ] Public deploy safety drill, controls absent (pending your Streamlit deploy)
- [x] Cold open drill, renders with zero positions -- run locally (file missing, HTTP 200, no exceptions); pending re-verification on the actual deployed URL
- [x] Secrets drill (repo half) -- `git grep` across the tracked repo for key-shaped strings and hardcoded assignments: none found; `.env` confirmed untracked. Page-source half pending your Streamlit deploy.
- [x] **False-trip test** (Part 6, not originally numbered in Part 8's list but the same discipline) -- `pipeline/risk/false_trip.py`. Found Guard #8 (credit/width band) blocked 42-50% of real winning weeks even after the Step 6 fix to 0.04, because the weekly ratio at 3%/$1-$5 has far more variance (std 0.059) than the mean (0.067) suggested. Lowered the floor to 0.0 per Part 6's own instruction to loosen or drop a guard that fails this test; re-verified at 0-1.6% blocked. Guard #12 (volatility regime) passed on first measurement (5.7% blocked, well under the 30% bar). The other 8 guards are not testable against this backtest at all (no historical OI/spread/greeks/account-state data) and remain on structural grounds per Part 9B.

---

## Code review findings (requested review, see chat)

- **Fixed: idempotency check never recognized `DRY_RUN` as an already-decided outcome.** `_already_decided_today` only checked for `SOLD`/`SKIPPED`; the entire dry-run build/test period logs accepted proposals as `DRY_RUN`, so a second same-day run would silently re-evaluate and log a duplicate accepted proposal. Confirmed by running twice before the fix (2 rows), then after (1 row, second run correctly reports `ALREADY_DECIDED`).
- **Fixed: peak equity was never persisted, so Guards #13/#14 (5%/8% drawdown stops) were structurally dead.** `run_agent.py` called `get_account_state()` with no `peak_equity` argument, so `broker.py` defaulted it to current equity on every single run -- drawdown was mathematically always 0%, regardless of real account history. Added `current_equity`/`peak_equity` to the audit log schema, `_load_peak_equity()` derives the running peak from the log's own history, and `run_once` now passes it through. Verified with a simulated two-day scenario: day 1 equity $100,000 logged, day 2 equity $95,000 with the persisted peak correctly computes a 5.00% drawdown instead of 0%.
- **Not yet fixed, flagged for later:** `monitor.evaluate_position`'s one-leg orphan check (`(short_qty > 0) != (long_qty > 0)`) only catches a fully one-sided fill (one leg at 0, the other >0). It does not catch a partial quantity mismatch (e.g. short_qty=6, long_qty=3), which is arguably the more realistic partial-fill failure mode and is not structurally impossible despite Alpaca's per-order coverage guarantee (that guarantee is about order acceptance, not guaranteed equal fills -- Part 8's own "Gotchas" section already flags this as unverified). Needs a quantity-equality check, not just a presence check.
- **Not yet fixed:** `orders.py`'s net-price sign convention remains genuinely unverified (by design -- can only be confirmed against a real fill), and `evidence_gate.py`/`false_trip.py` both repeat an identical ad hoc bool/string coercion for the CSV-loaded `win` column instead of a single shared loader function.

## Notes and failures

*(Record what broke and why. Leave the box unticked.)*

- **The plan's "no market holidays fall inside the window" claim was wrong once building actually started today (Mon Aug 31).** The 7-11 DTE window computed live reaches Sep 7-11, and **Sep 7, 2026 is Labor Day** (first Monday of September). `contracts.expiries_in_window` is a pure weekday filter and has no holiday awareness, so it lists Sep 7 as a candidate -- it will simply come back empty when `chain.py` fetches it live, and Guard #2 (data sanity) skips on empty/stale chain data, so this is not a safety gap. Noted here because the plan stated a false certainty; the actual Picker rule (#6: choose from expiries that exist) already covers it correctly by construction.
