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
- [ ] `LICENSE` (MIT) added
- [ ] `.gitignore` fixed so the plan docs are tracked
- [ ] Committed

### 1. Accounts and access
- [ ] New dedicated Alpaca paper account created
- [ ] Options level 3 confirmed on the **new** account
- [ ] Keys in `.env` as `ALPACA_PAPER_KEY` / `ALPACA_PAPER_SECRET`
- [ ] `GEMINI_API_KEY` in `.env`
- [ ] MCP server running, read only toolset confirmed
- [ ] `place_option_order` verified **absent** from the Reviewer's tools

### 2-4. Read path
- [ ] `options/contracts.py` OCC symbols, expiry calendar
- [ ] `options/chain.py` fetches a real chain with retry and liquidity filter
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
- [ ] Experiment 10 if there is room (naive vs HAR-RV vs XGBoost)
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
