# Options System Plan

Active build plan for the Alpaca AI Trading Agents Hackathon submission.
Supersedes the equity long/short parts of `TRADING_SYSTEM_PLAN.md`.
The volatility research track lives in `VOLATILITY_ML_PLAN.md`.

# Pivot Plan: From Predicting Direction to Selling Market Insurance

---

# PART 0 - The competition rules (verified, keep visible)

**Alpaca AI Trading Agents Hackathon**, co-hosted with lablab.ai. Everything below was checked against the official listing - this section exists so no design decision drifts away from the actual requirements again.

## 🚨 The submission is much bigger than a write-up

**This was nearly missed and would have been fatal.** lablab.ai has platform-wide submission rules on top of Alpaca's, and *"failure to adhere to submission guidelines may result in a lower score or exclusion"* ([submission guidelines](https://lablab.ai/delivering-your-hackathon-solution), [rule book](https://lablab.ai/hackathon-rules)).

## The challenge brief, verbatim - and the four things it asks for

> **Options Alpha Agents.** Build an autonomous AI trading agent designed to generate P&L using Alpaca's trading platform. Develop a **clear, testable trading strategy** and demonstrate how your agent **identifies opportunities**, **makes trading decisions**, **manages positions**, and **performs** over the course of the competition. You may explore options, trading agents, portfolio income, or other approaches supported by Alpaca.

**Four things must each be demonstrated.** The write-up and video should address them in order, explicitly:

| What they ask | Our answer | Status |
|---|---|---|
| **Clear, testable strategy** | Sell defined-risk SPY put spreads at a distance the data supports. Tested on 120 non-overlapping weeks of real expired-contract prices. | ✅ This is our strongest card |
| **Identifies opportunities** | Evidence gate: sweeps every distance, requires a 2-SE cushion, or declines | ✅ |
| **Makes trading decisions** | Picker (fixed rules) → Guard (hard limits) → Reviewer (may only veto/shrink) | ✅ |
| **Manages positions** | 50% profit target, day-before-expiry close, 15-min intraday monitor | ✅ (was the weakest - fixed in Part 8) |
| **Performs** | Live paper P&L, honestly reported as a 4-day sample | ✅ |

**Note the wording:** *"You **may** explore options... or other approaches."* That's softer than the "all strategies must include options" found elsewhere in the rules. The track is named **Options Alpha Agents**, so options remain the safe reading - and our strategy is options either way. No action needed, but don't be confused if the two phrasings differ.

## 🔴 Scope mismatch: they asked for "autonomous," we planned to cut it

The brief opens with **"Build an autonomous AI trading agent."**

Our plan defaulted to **SEMI-AUTO** (human approves exceptions) and put **AUTO mode first on the cut list.** That is cutting the thing the challenge explicitly asked for.

**This was backwards, and the fix is easy - the architecture already supports it.** Autonomy is safe here precisely because the LLM isn't the decision-maker: fixed rules pick the trade, hard limits gate it, and the model can only shrink or veto. There is nothing in AUTO mode that requires a human to be safe.

**Corrected:**

| | Old | **New** |
|---|---|---|
| Default mode | SEMI-AUTO | **AUTO - this is what "autonomous" means** |
| MANUAL / SEMI-AUTO | The normal way to run | **Supervision options, demoed in the video** |
| Cut-list position of AUTO | #1, cut first | **Removed from the cut list** |

Tuesday's launch still starts in MANUAL for the one-contract smoke test - that's a launch procedure, not the product. From Wednesday it runs AUTO, with the modes as a *feature* showing graduated trust rather than a dependency.

**Video framing:** *"It runs unattended. You can put a human in the loop if you want one - but the safety comes from the architecture, not the supervision."*

## Scope check - what the brief asks vs what we cover

| Brief says | Covered? | Where |
|---|---|---|
| Autonomous agent | ✅ **now** (was a gap) | AUTO default, above |
| Generate P&L | ⚠️ Honestly small | Part 4 |
| Clear, **testable** strategy | ✅ Strongest card | 120-week replay, Part 2 |
| Identifies opportunities | ✅ | Evidence gate, Part 2B |
| Makes trading decisions | ✅ | Picker → Guard → Reviewer |
| Manages positions | ✅ **now** | 15-min monitor, Part 8 |
| Performs over the competition | ✅ | Live paper P&L, reported as a 4-day sample |
| "Portfolio income" as an approach | ✅ | Premium selling *is* an income strategy - worth naming it that way in the write-up |

## ⬜ Gaps this scope check exposed

**1. The Social Engagement Awards have no plan.** Two of the prizes are for engagement, and nothing in this plan addresses them. Cheap to fix: post build-progress updates during the week (the negative-result story is genuinely interesting content), tag the sponsors, and share the final demo. **Budget 15 minutes a day**, not a work block.

**2. "What if the agent never trades?"** If the evidence gate finds nothing qualifying, we get zero P&L *and* a video with no action in it. **Contingency:** if by Tuesday nothing has cleared the 2-SE bar, trade the best available distance at **half size**, and make the gate's refusal a demonstrated feature - show it declining on a bad day and accepting on a good one. A system that never acts isn't a compelling demo, however principled.

**3. No benchmark comparison.** Judges instinctively ask "versus just buying SPY?" Plot our equity against **SPY buy-and-hold** and against **flat cash**, over the same sessions. If SPY jumps 3% this week, buy-and-hold beats us - that's expected, not a failure, because we're not a directional strategy. Show it with that context rather than omitting it.

**6. 🔴 The public app may have nothing to show.** The submission requires a working prototype at a URL that judges will open - possibly outside market hours, possibly before we've traded much. **An empty dashboard reads as broken.** Fix: the deployed app must render sensibly with zero positions (show the backtest results, the evidence-gate table, and the decision log), and must never show a blank screen or a stack trace. **Test it logged-out, after hours, before sharing the link.**

**4. Strike availability isn't handled.** Our target distance may not exist as a listed strike. SPY strikes are $1 apart near the money, so **round to the nearest listed strike further out** (never closer - closer means more risk than the gate approved) and log the actual distance used.

**5. Expiry selection isn't specified.** SPY lists expiries Mon/Wed/Fri. The picker must choose from what actually exists within the 7–11 day window, not assume a date is available.

### Alpaca's requirements

| Requirement | Detail | Status |
|---|---|---|
| **Options trading mandatory** | The rule that forced the whole pivot | ✅ The strategy *is* options |
| **New dedicated paper account** | One per email, **$100,000** | ⬜ **TODAY** - paper accounts get level 3 automatically; just confirm |
| **Alpaca Trading API + MCP Server or CLI** | Either is acceptable | ⬜ MCP, CLI as fallback |
| **One-page write-up** | **AI logic**, **risk gates**, **Alpaca infrastructure** | ⬜ Thursday |

### lablab.ai's platform requirements - all mandatory

| Requirement | Detail | Status |
|---|---|---|
| **Public GitHub repo** | **Mandatory.** Must be public and contain the code. | ⬜ `dreadf/trade_stock_ml` - make public, add LICENSE |
| **MIT License** | Submissions must be original work, **open source**, MIT unless stated | ⬜ **No LICENSE file exists yet** |
| **Working prototype at a URL** | For interactive evaluation. **Streamlit explicitly accepted.** | ⬜ **This makes the UI mandatory, not optional** |
| **Pitch video** | **≤5 minutes, MP4** | ⬜ Thursday - needs real time |
| **Slide deck** | **PDF** | ⬜ Thursday |
| **Cover image** | PNG or JPG, **16:9** | ⬜ Quick, but easy to forget |
| **Title + short & long description** | Character/word limits apply | ⬜ Check limits on the form |
| **Technology + category tags** | Proper categorisation | ⬜ Tag: volatility trading |
| **Deadline** | **Sept 4, 2026, 15:00 UTC** = 11:00 ET | ⚠️ Two hours into that session |

### What this changes about the plan

1. **The UI is no longer cuttable.** "Working prototype accessible by URL" is a hard requirement, and Streamlit is named as an acceptable host. It moves from cut-list position 6 to **never-cut**, and needs deploying to Streamlit Cloud, not just running locally.
2. **A full day disappears into submission assets.** Video + slides + cover image + repo cleanup is realistically 6–8 hours. That was nowhere in the schedule.
3. **The repo must be public with an MIT license.** ✅ *Verified: git history contains no hardcoded credentials - the very first commit already used `.env` and `os.getenv`. Safe to publish.*
4. **⚠️ `.gitignore` currently has `*.md`** with exceptions only for `README.md` and `EXPERIMENT.md`. **Our new plan documents would be silently excluded.** Add exceptions for `OPTIONS_SYSTEM_PLAN.md` and `VOLATILITY_ML_PLAN.md` - the research story is the differentiator, and it must be visible in the public repo.

## How it's judged - two rubrics, both apply

**Alpaca's stated criteria:** P&L and creativity/engagement. Two **Social Engagement Awards** sit on top of the placings.

**lablab's platform criteria** ([guide](https://lablab.ai/guide/ai-hackathons)) apply to every hackathon on the site:

| Criterion | What it means | Where we're strong / weak |
|---|---|---|
| **Application of Technology** | How well the models/tools are actually integrated | ✅ Gemini + MCP + Alpaca options, with a defensible restriction design |
| **Presentation** | Clarity of the video and deck | ⚠️ **Entirely down to Thursday's work** - an explicit scored criterion, not a formality |
| **Business Value** | Practical impact | ⚠️ Our honest P&L is small; the value argument is the risk architecture |
| **Originality** | Uniqueness and creativity | ✅ The falsification story and the refusal design |

**Presentation is a scored criterion in its own right.** That is a second, independent reason Thursday's asset day cannot be squeezed.

## Is there a live presentation?

**Probably not - but verify.** lablab's format varies by event: some announce winners on a Twitch stream, some do live on-stage pitching at partner conferences. Nothing found indicates live pitching for *this* hackathon, and the required ≤5-minute video is normally what serves as the presentation.

⬜ **Action: check the event page for any live/demo-day obligation.** Cheap to confirm, expensive to discover late.

Guidance worth heeding from lablab's own advice: *a 4-minute video that shows the solution working beats a polished 5-minute video that buries the demo.* **Lead the video with the working agent, not with the backstory.**

## Prizes and eligibility

1st **$2,500** · 2nd **$1,500** · 3rd **$1,000** · plus 2 Social Engagement Awards

**Can an Indonesian citizen enter and be paid? Almost certainly yes.**

The required **W-8BEN** is precisely the form a non-US person files to establish foreign status and claim tax-treaty benefits - **its presence is evidence that international winners are expected**, not a barrier. lablab operates across [180+ countries](https://lablab.ai/guide/ai-hackathons) and publishes no country restriction list; Indonesia is not on US sanctions lists.

**What to expect on payment:** US-source prize income to a non-resident is subject to **30% withholding** unless a tax treaty reduces it - so $2,500 could arrive as ~$1,750. The US–Indonesia tax treaty is where a lower rate would come from, and W-8BEN is where you claim it.

⬜ **Verify:** the event page for any country restrictions, and the treaty rate for prize/other income. *(Not tax advice - confirm before relying on a number.)*

Documents needed before payment: **W-8BEN, government photo ID, bank details.** Worth having ready rather than scrambling if you place.

## Tracks

Options alpha · **volatility trading** ← ours · hedging · portfolio overlays

## Timeline reality - as of today

```
Aug 28  hackathon opened
Aug 29  Sat  CLOSED   ✗ spent planning
Aug 30  Sun  CLOSED   ✗ spent planning
Aug 31  Mon  ← TODAY. Build day. Market opens 20:30 WIB.
Sep 01  Tue  SESSION 1  ← go live
Sep 02  Wed  SESSION 2
Sep 03  Thu  SESSION 3  ← submission assets during your daytime
Sep 04  Fri  partial - deadline 11:00 ET / 22:00 WIB
```

**Three full trading sessions, not four.** The two planned build days went into planning. Everything below is shaped by that - see Part 7's rebased schedule.

## What these rules imply, that's easy to forget

- **A bot that refuses to trade scores zero P&L.** Research honesty is our differentiator, but it can't be the whole submission.
- **Presentation and originality are scored directly** and are the parts we control - P&L over three sessions is close to a coin flip at safe size.
- **The write-up's three required topics map exactly onto our three layers**: AI logic → the Reviewer + volatility model; risk gates → the guard; Alpaca infrastructure → MCP + options API.
- **Two rubrics apply, not one** (Alpaca's and lablab's). Address both in the write-up.

---

# PART 0B - Submission copy (draft now, paste Friday)

Drafted early rather than Friday morning, because form fields under time pressure are where good projects get let down.

## Title

> **Evidence Gate**

Short, specific, and names the mechanism that makes the project unusual. *(Check the form's character limit before committing.)*

## Short description

> An options agent that sells S&P 500 volatility premium only when the measured edge clears a statistical bar - and refuses to trade when it doesn't.

> **⚠️ Do not paste the long description below until Tuesday's rebuilt backtest confirms its numbers.** It currently states the premium-is-negative finding and the stop-loss result as established fact. Those came from an unreproduced script. **If the rebuild gives different figures, update this copy before submitting.** Publishing a number we cannot reproduce would undo the exact credibility this project is built on.

## Long description

> We spent ten documented experiments trying to predict whether stocks would go up or down. They failed. Pooled model AUC landed at 0.498, and one experiment found the model was reliably *wrong*: momentum's cross-sectional information coefficient flipped sign between training and test (+0.0095 to −0.0422). Our last two attempts appeared to improve on AUC, so we built calibrated measurement tooling and re-measured them properly. Both came back indistinguishable from zero. The improvement had been noise the whole time. We published the negative result instead of shipping it.
>
> Then we noticed we had been asking the wrong question. An insurance seller doesn't care which way the market moves - only how far. So we rebuilt around selling defined-risk S&P 500 put spreads, where every position's maximum loss is fixed before entry.
>
> We held that strategy to the same standard. Using real prices of expired option contracts, we replayed 120 non-overlapping weeks and compared what the market charged against what actually happened. The result was uncomfortable: **at 1% and 2% out of the money - where most premium sellers operate - the premium is negative.** You are paid less than the risk you take. It only turns positive further out. We also found that adding a stop-loss to a defined-risk spread *triples* how often you realize a loss, because the S&P touches a level 2.6× more often than it closes below it.
>
> So the agent trades only the configuration that survived testing, at a size where all open positions are capped as a single correlated event, and refuses otherwise. A Gemini model reviews each proposed trade through Alpaca's MCP server - configured so the order-placing tools are not merely unused but absent. **The AI can veto a trade or shrink it. It can never choose one, and never make one bigger.**

## Tags

**Technology:** `Alpaca` · `Google Gemini` · `MCP` · `Python` · `Streamlit` · `XGBoost` · `pandas`
**Category:** Volatility trading · Autonomous agents · FinTech

## Cover image (16:9, PNG/JPG)

Simplest credible option: a clean screenshot of the dashboard with the four headline numbers, or the payoff table from Part 1B showing the loss flattening at −$473. **The flat-loss table is the more distinctive image** - it visually states the entire safety argument.

---

# PART 0C - Tracking progress

## The mechanism: `PROGRESS.md` at repo root

A single checklist file, grouped by day, updated as work completes. Chosen over GitHub Issues or a project board because it is zero-setup, lives in the public repo, and doubles as evidence of method - which lablab scores under *Presentation* and *Originality*.

```markdown
# Build Log

## Mon Aug 31 - Setup & read path
- [x] New paper account created
- [x] Options level 3 verified on the NEW account
- [ ] MCP server running, read-only toolset confirmed
- [ ] options/chain.py fetching a real chain
...
```

**Rules for it:**
1. **Tick only when verified**, not when written. "Code exists" is not "works."
2. **Add a one-line note when something fails**, and leave it unticked. The failures are the interesting part of the log.
3. **Update at the end of each work block**, not at the end of the day.
4. Every unticked box at Friday 09:00 is either cut or a known gap - **no box gets silently dropped.**

## Where the checklists live

| List | Location | Purpose |
|---|---|---|
| Daily build tasks | `PROGRESS.md` | What's done, what's left |
| Submission requirements | Part 7's final checklist | Ticked Friday morning |
| Experiment results | `EXPERIMENT.md` | Unchanged - experiments 10+ append here |
| Verification drills | Part 8's verification list | Ticked as each drill passes |

---

# PART 0D - The MIT License

**Required**, and no `LICENSE` file currently exists in the repo.

**Task:** create `LICENSE` at repo root, standard MIT text, `Copyright (c) 2026 Orlando`. GitHub's "Add file → Choose a license template" does this in about a minute.

**Two things to check alongside it:**

1. **`.gitignore` currently excludes `*.md`** (exceptions only for `README.md` and `EXPERIMENT.md`). Add exceptions for `OPTIONS_SYSTEM_PLAN.md`, `VOLATILITY_ML_PLAN.md`, and `PROGRESS.md` - the research story is the differentiator and must be visible.
2. **MIT means anyone may reuse this.** That's fine for our code. It does *not* extend to anything Alpaca or lablab own, so don't vendor their code into the repo - depend on it.

✅ **Already verified safe to publish:** git history contains no hardcoded credentials. The first commit already used `.env` + `os.getenv`. Nothing to rotate, no history rewrite needed.

---

## Documents this creates (the old ones are not overwritten)

This is a different system from the one in `TRADING_SYSTEM_PLAN.md`, so it gets its own documents. Nothing existing is deleted or edited - the equity work stays intact as the record of how we got here.

| File | Status | Contents |
|---|---|---|
| **`OPTIONS_SYSTEM_PLAN.md`** | 🆕 new | Parts 1–10 of this plan: the strategy, risk rules, architecture, schedule |
| **`VOLATILITY_ML_PLAN.md`** | 🆕 new | Part 11: the volatility research track, Experiments 12 to 16 |
| `EXPERIMENT.md` | ✏️ appended | Continues unbroken. Experiments 0 to 10 are the equity track; 11 onward lands here in the same format. |
| `TRADING_SYSTEM_PLAN.md` | 📦 unchanged | Kept as-is. Its Layer 0/1 code and design ideas are reused; the equity long/short parts are superseded. |
| `ML_Experiment_Plan.md` | 📦 unchanged | The direction question is closed with a documented negative answer. Superseded by `VOLATILITY_ML_PLAN.md`. |
| `Project_Context_and_Plan_Updated.md` | 📦 unchanged | Its gating criteria and risk table are the source material we translated. |

---

# PART 1 - What we are building

A bot that takes small, capped bets that **the S&P 500 won't crash this week**, and gets paid a fee for taking them.

## One bet, in real numbers

SPY was around **$763** when these examples were written. **Every figure below is illustrative** and will differ from live prices.

| | |
|---|---|
| **The bet** | SPY won't fall below **$740** by next Friday (that's a 3% drop) |
| **They pay us** | **$27** |
| **We put down** | **$473** deposit |
| **If SPY stays above $740** | We keep the $27 **and** our deposit back |
| **If SPY falls past $735** | They keep our $473 |

> **⚠️ Every number in this table is a placeholder, not a decision.** The 3% distance, the $5 gap between $740 and $735, the $27 fee - all of these are *parameters we choose*, and choosing them by eye is exactly the mistake this project spent ten experiments learning to avoid. SPY strikes are listed $1 apart, so the gap could be $1, $2, $5, or $10, and each choice changes the fee, the max loss, and the capital tied up. **The backtest sweeps distance AND gap width together**, and the evidence gate (Part 2B) picks the combination - or reports that none qualify. Read this table as "here's the shape of a bet," not "here's the bet."

Three things to notice:

1. **We don't need SPY to go up.** Sideways is fine. Slightly down is fine. We only lose if it drops hard.
2. **The $473 is the worst case, ever.** Not "probably." The deposit is the maximum. A −20% crash costs us the same $473 as a −4% dip.
3. **We know both numbers before we enter.** The market has no say in how much we can lose.

---

# PART 1A - Vocabulary (every term this plan uses)

Defined once here, used consistently everywhere after. If a word appears later that isn't in this list, that's a bug in the writing.

## Options terms

| Term | Meaning |
|---|---|
| **Put** | A contract giving someone the right to sell SPY at a fixed price. We sell these. |
| **Strike price** | The fixed price in that contract. In our example, **$740**. *(Earlier drafts called this "our line" - that was made-up wording. It's the strike price.)* |
| **Contract** | One unit. Always covers **100 shares**. |
| **Leg** | One of the two contracts in our bet. **Leg 1** = the one we sell at $740. **Leg 2** = the one we buy at $735. |
| **Spread** | The two legs together. This is our whole position. |
| **Width** | Distance between the two strike prices. $740 − $735 = **$5**. |
| **Credit** | Cash we receive for opening the spread. In our example, **$27**. |
| **Collateral** | Money Alpaca freezes until the bet resolves. Equals our maximum loss: **$473**. |
| **Expiry / expiration** | The date the contracts end. Ours run 7–11 days out. |
| **DTE** | "Days to expiry." |
| **Assignment** | When the contract we sold gets exercised and we're handed **actual SPY shares**. Only realistically happens at or near expiry. |
| **OTM ("out of the money")** | The strike price is below the current price, so the contract is currently worthless. All our bets start this way. |
| **IV (implied volatility)** | How much movement the market **expects**, baked into option prices. A forward-looking guess. |
| **RV (realized volatility)** | How much SPY **actually** moved. A backward-looking fact. |
| **Premium** | Here: the gap between IV and the RV that followed. Our source of profit. |

## Terms specific to this system

| Term | Meaning |
|---|---|
| **Distance** | How far below today's price we set our strike price, as a percent. We use 3%. |
| **The Picker** | Plain code that chooses which spread to sell, using rules fixed by the backtest. No AI involved. |
| **The Guard** | Plain code that checks every limit before an order goes out. Cannot be overridden by anything. |
| **The Reviewer** | The LLM component. Reads the proposed spread and account state, then may **approve, shrink, or reject** it - and writes the plain-English explanation for the log. *(Earlier drafts called this "the narrator." Same thing, clearer name.)* |
| **Evidence gate** | The statistical test in Part 2B that decides which distance is tradable. |
| **Cushion** | How far our measured win rate sits above the break-even win rate, counted in standard errors. |
| **Crash-day budget** | Total money at risk across all open spreads, treated as one number because they all fail together. |
| **Structural rule** | A rule that makes our loss limits *true* (e.g. "always buy leg 2"). Distinct from a numeric limit, and not editable. See Part 10B. |

---

# PART 1B - How options actually work (read this first if anything below is confusing)

This section is the foundation. It's also worth putting in the write-up, because most judges won't know this either.

## What a "put" is

A put is a contract. Someone pays for **the right to sell SPY at a fixed price**, no matter what the real price is.

Say the fixed price is **$740**, and SPY is trading at roughly **$763** (illustrative).

- **Today it's worthless.** Nobody would sell at $740 when the market pays $763.
- **If SPY crashes to $700**, it's worth **$40 per share** - the holder can force someone to buy at $740 when it's really worth $700.
- **We're that someone.** We sold it. We owe the $40/share.

One contract covers **100 shares** (standard unit), so $40/share = **$4,000** owed.

We sold that obligation for a fee. **That's the insurance.**

## Why selling only that would be reckless

| SPY falls to | We owe |
|---|---|
| $740 | $0 |
| $700 | $4,000 |
| $600 | $14,000 |
| $500 | $24,000 |

**There is no bottom.** Real insurers can write policies like this because they hold billions in reserve. We hold $100,000.

## So we buy insurance for ourselves

We buy the same kind of contract at **$735**. Now:

| SPY at expiry | Leg 1: we owe | Leg 2: we're owed | **Net** | Outcome |
|---|---|---|---|---|
| $763 | $0 | $0 | $0 | **Keep $27** ✅ |
| $745 | $0 | $0 | $0 | **Keep $27** ✅ |
| $738 | $200 | $0 | −$200 | −$173 |
| **$735** | $500 | $0 | −$500 | **−$473** ← floor |
| $700 | $4,000 | $3,500 | −$500 | **−$473** |
| $600 | $14,000 | $13,500 | −$500 | **−$473** |
| $400 | $34,000 | $33,500 | −$500 | **−$473** |

**Look at the bottom four rows.** Below $735 both contracts grow at exactly the same rate - one against us, one for us. They cancel out. The gap stays locked at **$500 forever**.

We are not insured against SPY falling. We're insured against it falling **past $735**. Below that, someone else's contract pays our bill.

> **In one line: we sell insurance, and buy cheaper insurance for ourselves. We keep the difference in premiums and carry only the risk in between.**

## Where the $27 comes from

| | |
|---|---|
| Leg 1 - sell the $740 protection | **+$45** received |
| Leg 2 - buy the $735 protection | **−$18** paid |
| **Net** | **+$27** |

Leg 2 costs less because $735 is *further* from today's $763 - it only pays out in a bigger crash, so it's less likely, so it's cheaper. **That price difference is our entire profit.**

## Where the $473 deposit comes from

Nothing to do with owning SPY or how much anyone invested. Pure arithmetic:

```
Gap between our two prices:   $740 − $735  =  $5 per share
× 100 shares per contract:                 =  $500
− the fee we already collected:            −  $27
                                           ─────────
Most we can ever lose:                     =  $473
```

Alpaca freezes exactly that much until the bet resolves. **It isn't extra risk** - it's the same $473 we could lose anyway, just held aside instead of spendable.

Change the gap, change everything: a **$10** gap → $1,000 max loss → bigger deposit. A **$1** gap → $100 max loss → tiny deposit. This is why gap width gets swept in the backtest rather than guessed.

## Which distance are we using - 1%, 2%, or 3%?

"Distance" means how far below today's price we set our **strike price** - the fixed price in the contract we sell. We tested three:

| Distance | Line (SPY at $763) | Fee | Verdict |
|---|---|---|---|
| 1% | ~$755 | biggest | ❌ underpaid for the risk |
| 2% | ~$748 | medium | ❌ underpaid for the risk |
| **3%** | **~$740** | smallest | ✅ **overpaid - this one** |

Closer to today's price = more likely to get hit = bigger fee. Further = safer = smaller fee. **3% is where the fee finally exceeded the real danger.**

**We pick one and keep it.** The evidence gate (Part 2B) re-confirms it against rebuilt numbers, then it's fixed. We're not adjusting it day to day.

## IV vs RV - why the gap is the entire game

| | What it is | Type |
|---|---|---|
| **IV** (implied volatility) | How much the market **expects** SPY to move. Baked into option prices. | Forward-looking **guess** |
| **RV** (realized volatility) | How much SPY **actually** moved. | Backward-looking **fact** |

Option prices come from IV. Nervous market → high IV → expensive options → **we collect a bigger fee.**

But whether we *keep* it depends on RV - what actually happened.

**We profit when IV was higher than the RV that followed.** The market was more scared than it needed to be, and paid us for the fear.

### Why a perfect forecast still isn't enough

Suppose you know for certain SPY will move **2%** this week.

- **Market priced 3% of movement** (nervous) → options expensive → fat fee → SPY moves only 2% → **we win**
- **Market priced 1% of movement** (relaxed) → options cheap → thin fee → SPY moves 2%, more than they expected → **we lose**

**Same forecast. Opposite outcomes.** Being right about SPY isn't what pays. Being right about *the gap between what was priced and what happened* is.

That's why forecasting volatility alone isn't sufficient, and why Experiment 14 targets the gap itself.

## How we get OUT of a position (and why it isn't breaking a promise)

A natural objection: *"We promised someone we'd buy their shares at $740. How can we just walk away before the deal ends?"*

**Because options are traded like shares, not signed like contracts.** Nobody knows who's on the other side, and it doesn't matter - a clearing house sits in the middle. Our obligation is to the system, not to a person.

**To exit, we buy an identical policy** - same $740 strike, same expiry - from whoever is selling one:

| | Position |
|---|---|
| Monday: we **sold** one | **−1** |
| Thursday: we **buy** an identical one | **+1** |
| Net | **0 - we're out** |

For a moment we're both the insurer and the insured. A claim would mean paying out on one and collecting on the other, so they cancel exactly. The clearing house removes both. Whoever bought our original contract still has it - someone else carries it now.

### Where the profit actually comes from

**"Don't we just pay back the $27?"** No - and this is the whole business.

**Policy prices fall as expiry approaches.** A policy with 10 days left is worth more than one with 2 days left, because there's more time for something bad to happen.

**The good case:**

| | |
|---|---|
| Mon - sell a **10-day** policy | **+$27** |
| *8 quiet days pass* | |
| Thu - the same policy now has **2 days** left, so it's cheap | |
| Thu - buy an identical 2-day policy | **−$8** |
| **Net kept** | **+$19** |

We sold expensive and bought back cheap. **That is the source of profit** - time passing while we're on the selling side.

**The bad case:**

| | |
|---|---|
| Mon - sell a 10-day policy | +$27 |
| Thu - SPY has fallen, everyone's nervous, policies are expensive | −$200 |
| **Net** | **−$173** |

Same mechanism, wrong direction. **Leg 2 is what caps how expensive that buy-back can ever get.**

**So closing early is not a penalty or an escape - it's the same trade in reverse, at that day's price.** Usually cheaper than we sold it for, which is exactly what we're betting on.

### And this is why the day-before-expiry rule works

The $444,000 assignment scenario can only hit someone who **still holds the obligation when expiry day arrives**. Buy an identical policy on Thursday, and our position is zero. Friday's 6:00 PM auto-exercise looks for our obligation and finds nothing.

We aren't dodging a consequence. **We left the trade before the consequence could exist.**

## Why we have no stop-loss

A stop-loss says "if this falls to X, get out." But our loss **already stops at $473** - structurally, because of leg 2. It cannot be exceeded.

So a stop-loss wouldn't lower our worst case. It would only make us bail out early on scary dips that recover. Measured: SPY *finishes* 3% down **16%** of the time, but *dips* below 3% at some point **42%** of the time. A stop-loss converts those temporary dips into permanent losses - firing ~2.6× more often, for zero reduction in maximum loss.

**Leg 2 is our stop-loss.** We bought it upfront, on day one, at a known price.

---

## "Legs" - what the bet is actually made of

The bet above isn't one contract. It's **two**, placed at the same moment. Each one is called a **leg**.

| Leg | What we do | Effect |
|---|---|---|
| **Leg 1 - the sold leg** | Sell protection at $740 | **Pays us money.** Creates the risk. On its own, the loss has no floor. |
| **Leg 2 - the bought leg** | Buy protection at $735 | **Costs a little.** Caps the risk. This is what makes $473 a real number. |

The $27 is the net: what leg 1 paid us, minus what leg 2 cost us.

**Leg 2 is the entire safety design.** Without it, a crash to $600 would cost us roughly $14,000 instead of $473. That's why "capped loss" isn't a policy we chose to follow - it's a structural fact created by owning leg 2.

Both legs must exist for the bet to be safe. Which is exactly why one leg filling without the other is the most dangerous failure in the system (Part 10C).

---

# PART 2 - How we know it works

We don't guess. We replayed it.

Alpaca stores the real prices of option contracts that have already expired, going back to **Feb 2024**. So we ran the actual bet, week after week:

```
  Take a real Friday in the past
        ↓
  Look up what the bet ACTUALLY paid that day
        ↓
  Fast-forward one week
        ↓
  Look up where SPY ACTUALLY closed
        ↓
  Win or lose? Record it.
        ↓
  Next Friday. Repeat 120 times.
```

Real prices and real outcomes, across 120 non-overlapping weeks.

> **⚠️ Two honesty corrections to that sentence, because earlier drafts overstated it.**
>
> **1. There ARE assumptions.** Entry priced at the day's bar close, settlement computed at intrinsic value against the SPY close, and the base case assumes no slippage. The cost sweep exists precisely because that last one is unrealistic. Calling this "no assumptions" was wrong.
>
> **2. These numbers are NOT yet reproduced.** They came from a research agent's throwaway script and **are not in the repo.** Rebuilding that as committed code is build item #5 and the single most important task of the day. **Until it runs, every figure in this section is provisional.**

## What it found (this is the interesting part)

The fee tells you the market's own odds. If they pay you $50 on a $500 deposit, they're pricing a 10% chance of losing.

So: compare the odds they charged against what actually happened.

| How far below we bet | Odds they charged us | What actually happened | Are we overpaid? |
|---|---|---|---|
| 1% below | 18.1% | 22.5% | ❌ **Underpaid** |
| 2% below | 9.8% | 11.7% | ❌ **Underpaid** |
| **3% below** | **5.4%** | **2.5%** | ✅ **Overpaid** |

**At the distances most people sell, you get paid less than the risk you're taking.** The premium is only real further out.

We also tested 2-day bets - the tempting way to make money fast in a short window. **They lose at every distance.**

**Important caveat before you trust that "3%" row:** it comes from about 120 non-overlapping weeks. That is not a lot of crashes to have observed. The next section turns this table into an actual decision rule, instead of us eyeballing "3% looks like the winner" and betting real money on it.

---

# PART 2B - Turning "looks good" into a rule (the evidence gate)

You asked the right question: a $27 gain against a $473-$3,000 loss doesn't look like it "ratios." Let's actually check, instead of assuming 3% is fine because its row had a checkmark.

## The real math on the 3% bet, at the size in this plan (6 contracts, $3,000 at risk)

- Fee collected: **$162**
- To break even, we need to win **at least 94.9%** of the time (3000 ÷ (3000+162))
- Provisional measurement: **97.5%** win rate
- Cushion: **2.6 percentage points**

**The arithmetic, done properly** (an earlier draft quoted a margin of error that was wrong):

```
  SE = sqrt(0.975 × 0.025 / 120) = 0.0143  =  1.43 percentage points
  cushion in SE units = 2.62 / 1.43        =  1.8 SE
```

**So the cushion is 1.8 standard errors, which is BELOW our own 2.0 bar.** An earlier version of this section said the margin of error was "±6 to 8 points," which came from a different measurement entirely (21-day breach probabilities on ~78 windows) and made the result look far weaker than it is. The honest figure is ±2.9 points at 95%, and a cushion that lands just short of the threshold.

**That is the whole reason the gate exists.** By eye, 97.5% versus 94.9% looks like a comfortable edge. Run the arithmetic and it does not clear the bar we set before looking. This is the same trap Experiment 6 flagged for the stock model.

**One conservatism worth noting:** the breakeven formula assumes every loss is a *maximum* loss. In reality a spread that finishes only slightly in the money loses less than the full width, so the true breakeven is somewhat below 94.9% and the real cushion is somewhat wider than 1.8 SE. The backtest computes actual per-trade P&L rather than this simplification, so **the gate should use the backtest's own numbers, not this formula.** The formula is here to show the shape of the problem, not to be the decision rule.

There's a well-known name in finance for a strategy shaped like this - small steady wins, rare large losses, run at a size where the edge is thinner than it looks: **"picking up pennies in front of a steamroller."** ([sharpetwo.com](https://www.sharpetwo.com/p/picking-up-pennies-in-front-of-a)) It's not a slur, it's a specific, documented failure pattern: the trade works for months or years, and people mistake "hasn't broken yet" for "safe" ([steadyoptions.com](https://steadyoptions.com/articles/selling-options-premium-myths-vs-reality-r433/)). The canonical real example is **"Volmageddon"** in February 2018, where a popular short-volatility fund (XIV) lost **over 90% of its value overnight** ([Forbes](https://www.forbes.com/sites/dereksaul/2023/03/08/what-is-volmageddon-why-record-options-trading-could-risk-another-20-stock-crash/)) - years of small collected fees erased in hours, because the strategy was exactly this shape at too much size.

## The fix: don't pick a distance by eye - require a real statistical margin

**Rule: only trade a distance where the measured win-rate cushion is at least 2 standard errors above the required breakeven rate.** Not "positive." Not "looks better than the others." A cushion big enough that noise alone is unlikely to explain it.

Tuesday's build computes this for every distance in the sweep (1%, 2%, 3%, 4%, 5%, 6%...), not just the one row we happened to like:

| For each distance, compute | Why |
|---|---|
| Required breakeven win rate | From the actual credit and width at that distance |
| Measured win rate | From the 120-week replay |
| Standard error of that measurement | From `n_eff`, the same non-overlapping-count discipline as `eval.py:38` |
| Cushion in SE units | (measured − required) ÷ SE |

**If a distance clears 2 SE → it's tradable. If none do → we don't trade, and we say so.** That's not a failure of the plan - refusing to trade an edge that can't be told apart from noise is exactly what `Project_Context_and_Plan_Updated.md:261-273`'s gating criteria already established for the stock model: *"failing these means not trading. That is a legitimate outcome."* Same standard, new domain.

## The other thing your instinct caught: the "worst case" math was wrong

Part 4 originally listed "$12,000 worst case, everything" as if 4 bets failing were 4 separate unlucky events. **They're not independent.** Every bet is the same wager - SPY won't crash - so if it crashes, **all open bets lose on the same day, from the same cause.** That's not four bad rolls. It's one bad day.

**Fixed rule:** treat every open bet as **one combined position**, sized so that a single crash day costs no more than a fixed, small share of the account - not the sum of each bet's individual "worst case" as if they were unrelated coin flips.

---

# PART 2C - The competition's own reference architecture (and how we differ)

Alpaca published [Building a Multi-Agent AI Trading System on Alpaca](https://alpaca.markets/learn/building-a-multi-agent-ai-trading-system-on-alpaca). **Assume judges are familiar with it and that some entrants have followed it.** That is an assumption, not a fact, but it is the safe one to design against.

## What their reference architecture does

```
Alpaca OHLCV + Finnhub + yfinance + FRED
    ↓
Market snapshot (SQLite)
    ↓
5 agents in parallel - Momentum · Macro · StatArb · Contrarian · Exotic
    ↓
Critic agent (validates against an investment memo)
    ↓
Human gate (approve / reject / revise)
    ↓
Risk Guard (deterministic Python, no LLM)
    ↓
Execution + position monitor (15-min checks)
```

Their deterministic limits: 10% per position, 30% per sector, 1.0× gross leverage, drawdown halts at **5% daily / 10% weekly / 15% total**.

## ⚠️ The uncomfortable part

**"An LLM proposes, a deterministic guard it cannot override decides" is Alpaca's own published pattern.** So is the human approval gate. So is full decision logging.

Our architecture is **not** novel. It is the reference implementation. Any submission pitching "we separated the AI from the risk layer" as its big idea is describing the article's Figure 1.

## How we actually differ - and it's sharper than novelty

Their five agents exist to **generate more trade proposals**. We ran the experiment that asks whether such proposals are worth generating at all, and for our feature set the answer was no - ten documented experiments, AUC 0.498, a model that was reliably *wrong*.

So we inverted the same architecture:

| | Alpaca's reference | Ours |
|---|---|---|
| LLM's job | **Propose** trades | **Review** a trade plain code already chose |
| Direction of LLM influence | Adds candidates | **Can only remove or shrink** |
| What justifies trading | An agent's thesis + confidence score | **A statistical bar the historical data must clear** |
| Response to no good trade | Agents still propose; critic filters | **The system declines to trade, by design** |
| Tools given to the LLM | Full toolset | **Order-placing tools not exposed at all** |

**The pitch line for the video:** *"Alpaca's reference architecture has five agents proposing trades and a guard filtering them. We tested whether our proposals were worth making, found they weren't, and inverted it - the model can now only make us trade less."*

That engages with the reference design instead of accidentally reinventing it, and it's a claim only a team with nine failed experiments can make.

## What we should borrow from it

| Their pattern | Take it? |
|---|---|
| **Standardised JSON output from the LLM** | ✅ Already in the plan (approve/shrink/reject schema) |
| **SQLite snapshot before acting** | ✅ **Adopt** - one consistent view per cycle, avoids re-fetching and rate-limit races |
| **Position monitor on a timer (theirs: 15 min)** | ✅ **Adopt** - our profit-target and assignment rules need checking intraday, not once a day. This was a real gap. |
| **Full decision logging** | ✅ Already in the plan |
| Bracket / OCO orders for exits | ❌ **Cannot** - verified: Alpaca's multi-leg options orders accept MARKET and LIMIT only (`requests.py:243-252`). No broker-side brackets on a spread. **We must poll.** This is exactly why the position monitor matters more for us than for them. |
| Their drawdown numbers (5% daily / 10% weekly / 15% total) | 📌 Useful calibration - **ours are tighter** (5% stop-opening, 8% halt). Worth noting we're more conservative than the reference, not less. |
| Finnhub / FRED / yfinance | ❌ Out of scope in four days, and our thesis doesn't need more data sources |

---

# PART 3 - What makes this ours

The strategy above is what any honest person lands on once options are mandatory. It is not, by itself, distinctive.

**This is:**

Ten experiments asked *"will SPY go up or down?"* The answer was a documented, rigorous **no**: coin flip, one experiment showed the model reliably *wrong*, and Experiment 10 then re-measured the two most promising results with cross-sectional IC and found both indistinguishable from zero.

But an insurance seller **does not care which way the market moves.** We only care **how far**.

And that question has a different answer. **Volatility clusters** - calm weeks follow calm weeks, wild weeks follow wild weeks. It's one of the most reliable patterns in finance. Direction is unpredictable. Magnitude is not.

> **We spent ten experiments answering the wrong question. The right one was sitting next to it the whole time.**

**One honest tempering, checked against real research before we oversell this:** the standard baseline for volatility forecasting - literally just "average yesterday's swing, last week's, and last month's" - is already very hard to beat. Published comparisons find it consistently **beats GARCH models** and holds up against more complex approaches ([ScienceDirect](https://www.sciencedirect.com/science/article/am/pii/S0927539824000598)). So "predict how far it moves" is a much better *question* than "predict which way," but that doesn't guarantee XGBoost adds anything on top of the simple average, especially on a few years of daily SPY data. Experiment 12 (below) might well conclude "ML doesn't beat the simple baseline" - which, by this project's own standard, is still a legitimate, loggable result, not a failure.

## What the volatility layer actually does

Same pipeline, new target. Instead of predicting *up or down*, predict **how far SPY moves over the next 7-11 days**.

Then it makes two decisions:

| Prediction | Bot's response |
|---|---|
| Calm week expected | Sell normally at 3% out |
| Choppy week expected | Sell **further** out - more safety margin |
| Wild week expected | **Don't sell at all today** |

So the ML isn't picking trades. It's answering the one question that determines whether our bet is safe: *how much is this thing going to move?*

## The honesty gate (Experiment 12)

There's an obvious cheap baseline: **"however much it moved last week, assume the same next week."** That's what volatility clustering means, and it's already a strong forecast.

So before any ML goes in, we run the same test as Experiment 0:

> **Does XGBoost beat "assume it stays the same"?**

If yes → ML goes in. If no → we use the simple version and say so. Either way the system works. Either way it's an honest result, and either way it's a documented experiment.

This is your existing method applied to a new question, which is exactly the point.

---

# PART 4 - The money

## What we charge

The $27-per-contract, 3%-distance example in Part 1 was illustrative, to explain the mechanics. **The actual distance and size are not fixed here - they come out of Tuesday's evidence gate (Part 2B).** If 3% clears the 2-SE bar, we use it. If a different distance clears it more convincingly, we use that instead. If nothing clears it, we don't trade with real (paper) capital and the write-up says so.

Using the 3% example as a stand-in until Tuesday's numbers are in:

- ~6 contracts per bet → ~$162 collected, ~$2,840 at risk on that one bet
- Up to 4 open at once, **subject to the $12,000 crash-day budget** (Part 5). With only 3–4 sessions, expect **2–4 total**, not a full book.

## What we expect to make

| | |
|---|---|
| **Timeframe** | **3 sessions** (Tue Sep 1 → Thu Sep 3) + a partial Friday |
| **Expected profit** | **~$150–350** over 3–4 sessions, illustrative pending the gate |
| **Best realistic case** | ~$650 (everything expires clean) |
| **Worst case, one bet** | −$2,840 |
| **Worst case, a crash day** | **−$12,000 (12%)** - one event, not four separate ones, because a crash hits every open bet at once |

On a $100,000 paper account that's roughly **+0.3% to +0.45% in four days**, if the gate approves trading at all.

Three honest notes:

**It's a paper account.** Losing paper money costs nothing but the contest, which is why we're willing to size larger than the 1% that would be right for real money. The max loss is still a known, fixed number on every single trade - and Part 2B's fix means the *combined* worst case is capped too, not just each bet individually.

**Four days is very short.** Annualized, this pace is roughly 20-30%/year - but four days is far too small a sample to claim that. Two bad days could erase it. We say this rather than projecting.

**If the gate finds nothing clears 2 SE, this whole section reads as "$0 expected, because we chose not to trade."** That is a real possible outcome, not a bug in the plan.

---

# PART 5 - How we avoid losing badly

## The structural rule

**Every bet has a deposit, and the deposit is the maximum loss.** We never take a bet without one. There is no scenario where the market decides how much we lose.

That single rule does more than every other safeguard combined.

## The limits

| Rule | Limit | Plain English |
|---|---|---|
| Max loss, one bet | **3% of current equity** (~$3,000 at $100k) | Recalculated each cycle, not fixed at the starting balance |
| **Max loss, a crash day (all bets combined)** | **12% of current equity** (~$12,000 at $100k) | The real binding limit. All bets fail together, so this is ONE number for the whole book. |
| Max bets open | **4** | Only reachable if each is small. See the budget rule below. |
| Market exposure | **±150 share-equivalents (~$115,000 notional)** | How much we move when SPY moves. See the note below. |
| How far out we bet | **Whatever distance clears the 2-SE evidence gate (Part 2B)** | Not fixed in advance - data decides, same as the equity gating criteria |
| Days to expiry | **7–11** | Not a coin flip, not dead money |
| Liquidity | Heavily-traded contracts only | Never buy what you can't sell |

### The budget rule (this resolves an inconsistency)

An earlier draft of this plan said "$3,000 per bet, up to 4 bets, $5,000 combined." **Those three numbers cannot all be true** - 4 × $3,000 is $12,000, not $5,000.

The fix: **treat it as a budget, not a per-bet allowance.**

```
  Crash-day budget:  12% of current equity   (~$12,000 at $100k)
  Each new bet:      up to 3% of current equity, AND must fit remaining budget
```

**Both figures track current equity, not the starting balance** (see Part 6's decision logic). Every dollar amount in this section is the value at $100,000 and shrinks as equity does.

So you might hold **4 bets of $3,000**, or **2 of $3,000 plus 2 of $1,500**, or one large one and nothing else. The bot sizes each new bet against **what's left**, not against a fixed per-bet number. When the budget's spent, it stops opening regardless of how many slots are free.

**Why $12,000 and not $5,000:** you chose 3% per trade knowing the tail was ~$15,000, so $12,000 is consistent with that decision. It is 12% of the account in a genuine crash - that's the number, stated plainly, not hidden behind four separate caps that each look small.

### Market exposure, defined properly (an earlier number here was wrong)

Two different figures appeared in earlier drafts, "±20 delta" and "±$45,000", with no stated units and no arithmetic connecting them. Neither survives a check.

**Units, fixed:** exposure is measured in **share-equivalents**. One share-equivalent means we gain or lose the same as owning one SPY share.

```
  Net delta per spread  ≈ +0.05   (short put ~0.10, long put ~0.05)
  Per contract          = 0.05 × 100 shares = 5 share-equivalents
  6 contracts           = 30
  4 positions of 6      = 120 share-equivalents ≈ $92,000 notional
```

**Cap: ±150 share-equivalents**, roughly $115,000 of notional exposure, which a full book approaches but does not exceed.

**That is more market exposure than the account is worth, and saying so matters.** It is normal for a short-put book and it is not the same as risk (loss is still capped at $12,000), but "defined risk" must never be read as "market-neutral." Part 9's admissions already flag this; the number now matches the arithmetic.

## When we stop

| If... | We... |
|---|---|
| Down **5%** from peak (peak = highest account value since launch) | Stop opening new bets |
| Down **8%** from peak | **Close everything. Halt. Human review.** |
| Volatility model says wild week | Skip today |
| Data stale or broken | Don't open. Still close what's expiring. |

**Why these aren't tighter:** one maximum-size loss is $3,000 = 3% of the account. If "stop opening" fired at −2%, a *single* expected loss would shut the system down - and losing sometimes is the normal operation of this strategy, not a malfunction. The triggers are set so one bad bet is survivable and **two** get our attention. A kill-switch that fires on ordinary outcomes isn't protection, it's a hair trigger - which is exactly what the false-trip test exists to catch.

## Three rules that sound wrong but aren't

**1. No stop-loss.**

Sounds reckless. Here's the measurement: over 21 days SPY *ends* more than 3% down **16%** of the time - but it *dips* below −3% at some point **42%** of the time.

A stop-loss turns temporary dips into permanent losses. And our deposit **already is** the stop. Adding another one doesn't lower the max loss; it just triggers it **2.6× more often**.

**2. Close at half profit.**

Once we've earned about half the fee, take it. The last few dollars carry the worst risk-to-reward in the trade.

**3. Never hold into expiry day.**

```
  Close EVERY position no later than the day BEFORE expiry.
  Never hold an option position into its expiration day.
```

**Why.** SPY options settle in **actual shares**, and Alpaca **auto-exercises anything in the money by $0.01**.

If SPY closes at **$739.99**, one cent below our strike but well above our $735 protection, the short leg is assigned while the long leg expires worthless. At 6 contracts that means being forced to buy **600 shares at $740 = $444,000 of stock in a $100,000 account.**

Economic loss: about $6. Position: $444,000. Immediate margin call.

**This is the one gap the capped-loss structure does not cover**, because between the two strikes only one leg is live. Exiting a full day early removes the scenario entirely, since we hold nothing when auto-exercise runs.

**Cost:** the last day of time decay, small and quantifiable. **Benefit:** assignment risk goes to approximately zero.

No contradiction with rule 1: early in a position's life we hold through dips, and we exit before expiry day rather than gambling on where it lands.

*(Two earlier drafts of this rule used a "close if within 0.5% of the strike" test instead. Both left us exposed in exactly the $735 to $740 band where pin risk lives, and the first also silently reintroduced the dip-closing behaviour rule 1 argues against. Recorded here so neither version gets reimplemented by accident.)*

## Testing the safety rules themselves

A safety rule that fires too often loses money on its own - it keeps pulling you out of bets that would have been fine.

So before any limit goes live, we replay it across the 120 backtested weeks and count how often it would have blocked a **winner**. Anything blocking >30% of winners is set wrong and gets loosened.

Your `Project_Context_and_Plan_Updated.md:359` already demands this test. In the equity project it wasn't computable. Here it takes an hour.

---

# PART 6 - How the app works

```
              Alpaca market data
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
  SPY price history           Live option prices
  (already have it)                (new)
        │                           │
        ▼                           │
 ┌──────────────────┐               │
 │ VOLATILITY MODEL │               │
 │ "how far will    │               │
 │  SPY move?"      │               │
 │ (your ML, new    │               │
 │  target)         │               │
 └────────┬─────────┘               │
          │  calm / choppy / wild   │
          └─────────────┬───────────┘
                        ▼
              ┌───────────────────┐
              │   THE PICKER      │  Fixed rules from
              │   (plain code)    │  the backtest.
              └─────────┬─────────┘
                        ▼
              ┌───────────────────┐
              │   ⛔ THE GUARD ⛔  │  Every limit.
              │   (plain code)    │  Cannot be argued with.
              └─────────┬─────────┘
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
          PLACE BET              SKIP
             │                     │
             ▼                     │
      ┌─────────────┐              │
      │ THE REVIEWER│  May say NO  │
      │             │  or SMALLER. │
      │             │  Never YES,  │
      │             │  never BIGGER│
      └──────┬──────┘              │
             ▼                     │
     Alpaca → paper order          │
             │                     │
             └──────────┬──────────┘
                        ▼
                WRITE IT DOWN
          every decision, including
          every time we chose not to bet
```

## The Picker's rules - everything it decides

Plain code. No AI. Every value comes from the backtest or the evidence gate.

| # | Rule | Value |
|---|---|---|
| 1 | Underlying | **SPY only** |
| 2 | Structure | Put credit spread - sell higher strike, buy lower |
| 3 | Distance below current price | **Whatever cleared the evidence gate** (target 3%) |
| 4 | Strike selection | **Nearest listed strike at or beyond target - always round AWAY from price, never closer.** Log actual distance. |
| 5 | Width between strikes | Whatever cleared the gate (e.g. $5) |
| 6 | Expiry | 7–11 days out, **chosen from expiries that actually exist** (SPY lists Mon/Wed/Fri) |
| 7 | Contract count | Largest that fits *both* the per-trade cap and remaining crash-day budget |
| 8 | Order type | **LIMIT at mid.** Never market. |
| 9 | Fill discipline | Wait 5 min → improve $0.01 once → cancel and skip. Never chase. |

## The Guards - everything that can block a trade

Each returns `(pass/fail, reason)`. **Any single failure stops the trade.** The reason is logged either way.

| # | Guard | Blocks if |
|---|---|---|
| 1 | **Market open** | `get_clock` says closed |
| 2 | **Data sanity** | Chain stale, quote older than 15 min, IV missing on the chosen leg, spot disagrees with chain by >0.5% |
| 3 | **Evidence gate** | No distance clears the 2-SE cushion |
| 4 | **Per-trade cap** | Max loss on this spread > **3% of current equity** (~$3,000 at $100k) |
| 5 | **Crash-day budget** | Total risk across all open positions would exceed **12% of current equity** (~$12,000 at $100k) |
| 6 | **Concurrent positions** | Already 4 open |
| 7 | **Net delta** | Book would exceed **±150 share-equivalents** (~$115,000 notional). Units defined in Part 5. |
| 8 | **Credit/width ratio** | Below 0.08 (not paid enough) or above 0.35 (too close - the negative-premium zone) |
| 9 | **Expiry window** | Fewer than 7 or more than 11 days |
| 10 | **🔴 Expiry-day rule** | Any position would be held into its expiration day |
| 11 | **Liquidity** | Open interest < 500, bid-ask > 15% of mid, or either leg unquoted |
| 12 | **Volatility regime** | Annualized RV(10d) > 25%, or SPY moved >2% yesterday |
| 13 | **Drawdown - soft** | Account down 5% from peak → stop opening new positions |
| 14 | **Drawdown - hard** | Account down 8% → close everything, halt, human review |

**"Peak" means the highest account equity recorded since launch**, stored in the audit log and updated each monitor cycle. Not the starting $100,000, and not the day's opening value.

## The exit rules - what `monitor.py` checks every 15 minutes

| # | Trigger | Action |
|---|---|---|
| 1 | Spread can be bought back for **half or less of the credit received** (measured on mid) | Close it, take the profit |
| 2 | **Tomorrow is expiry day** (fires at the first cycle after 15:00 ET) | **Close regardless of profit or loss** |
| 3 | Only one leg is held | Emergency close of the orphan, halt everything |
| 4 | Hard drawdown breached (8% from peak) | Close everything, halt |

Nothing else closes a position. Alpaca offers no broker-side exits on multi-leg options, so if it isn't in this table, it does not happen.

**On trigger 3's timing:** the one-leg check runs **immediately after every order submission** *and* on every monitor cycle. The first catches a bad fill within seconds; the second catches anything that drifts out of sync later, for instance after a crash and restart. Checking in only one of those two places would leave a real window open.

## ⭐ Every rule gets a baseline (ablation, applied to trading)

Your instinct is right, and it's the same method as Experiment 3's feature ablation: **a rule that isn't measured against its own absence is just an opinion.**

So every rule that *can* be tested this way is: **run the 120-week backtest with the rule, and without it.** If removing it doesn't hurt, the rule isn't earning its place.

**⚠️ But not every rule is testable on historical bar data, and an earlier draft implied they all were.** The expired-contract data gives us prices and outcomes. It does **not** give us historical open interest, historical bid-ask spreads, live account state, or greeks.

| Testable on the backtest | Not testable (structural or no data) |
|---|---|
| Evidence gate, credit/width band, volatility regime, drawdown stops, concurrent limit, distance, width, expiry window, profit target, day-before-expiry exit | Market-open check, data sanity, liquidity filter (no historical OI or spread), net delta (no historical greeks), per-trade cap, crash-day budget, one-leg emergency |

The untestable ones are kept on **structural grounds**, not measured ones, and Part 9B's audit already classes them as *chosen* rather than *measured*. **Say which is which rather than implying everything was validated.**

### The universal baseline

> **"Always trade, no rules, no exits, hold to expiry."**

Everything is measured against that. Same metric throughout: **win-rate cushion in standard errors**, plus net P&L.

### Picker rules

| Rule | Baseline to beat | Verdict comes from |
|---|---|---|
| Distance (3%) | Every other distance, 1%–6% | ✅ Already measured - only 3% was overpaid |
| Width ($5) | $1, $2, $10 | ⬜ Sweep alongside distance |
| Expiry 7–11 days | 2, 5, 14, 21 days | ✅ Partly done - 2-day loses at every distance |
| Strike rounding (away) | Rounding to nearest, or toward | ⬜ Cheap to test |
| LIMIT at mid | Crossing the spread | ✅ The cost sweep already shows the edge dies past ~$0.10 |

### Guards

For each: **how often would it have blocked a winner?** Anything above 30% is mis-set. *(This is the false-trip test, extended from kill-switches to every guard.)*

| Guard | Baseline | What we're checking |
|---|---|---|
| Volatility regime (RV > 25%) | No regime filter | Does skipping wild weeks help, or just skip good ones? |
| Credit/width 0.08–0.35 | No ratio filter | Does the band add anything past the distance rule? |
| Drawdown 5% / 8% | No drawdown stop | On 120 weeks, would these have fired on noise? |
| Concurrent limit (4) | Unlimited | Does concentration actually hurt? |
| Evidence gate (2 SE) | Trade everything | **The headline comparison - does the gate beat trading blindly?** |

*(The liquidity filter is deliberately absent from this table: the expired-contract data carries no historical open interest or bid-ask, so it cannot be ablated. It stays on structural grounds, and live fill-versus-mid logging is the only evidence we will get for it.)*

**Expect some guards to fail this test.** That's the point. A guard that blocks 40% of winners and prevents no real losses should be loosened or dropped, and saying so is more credible than shipping fourteen unexamined rules.

### Exit rules - how each works, and its baseline

| # | Exit | How it works | Baseline to beat |
|---|---|---|---|
| 1 | **50% profit target** | Every 15 min, compute current value. If we've captured half the credit, buy the spread back and bank it. | **Hold to expiry** - plus sweep 25%, 75%. **This is our most glaring untested number.** |
| 2 | **Day-before-expiry close** | If tomorrow is expiry, close at any price. | Holding to expiry - measurable as the cost of that one day's decay |
| 3 | **One-leg emergency** | After each order, verify both legs exist. If not, close the orphan at market. | No baseline - this is safety, not optimization |
| 4 | **Hard drawdown (8%)** | Account below 8% from peak → close everything, halt. | No stop - check it wouldn't have fired on ordinary losing streaks |

Exits 1 and 2 are **strategy choices** and must be measured. Exits 3 and 4 are **safety** and are kept regardless - but we still check they don't fire spuriously.

### Where the results go

`EXPERIMENT.md`, same format as Experiments 0–9. **Log every variant tried, including the losers.** With this many sweeps on 120 observations, multiple-testing is a live risk - the log is what keeps it honest.

## The exact decision logic (ambiguities resolved)

Several rules above were described but not specified precisely enough to code. Resolving them here so they do not get decided by accident during implementation.

### Limits are a percentage of CURRENT equity, not starting equity

**This matters more than it looks.** If we are down $5,000, is the per-trade cap 3% of $100,000 or 3% of $95,000?

**Answer: current equity.** So $2,850, not $3,000.

Risk then scales down automatically after losses and up after gains, which is the standard approach and the safer one. Using starting equity would mean risking a progressively larger share of what is left, which is how accounts spiral.

### Contract sizing formula

```
budget_left   = crash_day_budget - sum(max_loss of open positions)
allowance     = min(per_trade_cap, budget_left)
contracts     = floor(allowance / max_loss_per_contract)

if contracts < 1  ->  SKIP, log "insufficient budget"
```

**Always `floor`, never round.** Contracts are whole numbers and rounding up breaches the cap.

### Guards re-run after the Reviewer shrinks a trade

The flow is Picker, then Guard, then Reviewer. But if the Reviewer halves the size, **the guards must run again on the new size.**

Halving is always safer so it should always pass, but re-running is cheap and it means no order ever reaches the broker unchecked. **The guard is the last thing that touches an order before it goes out. Always.**

### The 50% profit target, precisely

> Close when the spread can be bought back for **half or less** of the credit received.

Collected $162, close when it costs $81 or less. Measured on the mid price at each monitor cycle, not on the last trade.

### When the day-before-expiry close fires

**At the first monitor cycle after 15:00 ET on the day before expiry.** Not at the open (poor prices), not at the close (no room if the order does not fill).

If it does not fill, retry every cycle until 15:45 ET, then cross the spread and take whatever price is available. **Getting out matters more than the price we get out at.**

### One decision per session, and it is idempotent

The decision loop opens **at most one new position per session.** If it crashes and restarts, it reconciles first, sees today's position already exists, and does nothing. Re-running the loop must never produce a second order.

### Duplicate expiries are allowed, with a caveat

Two positions may share an expiry date. But note this concentrates risk on a single day, and the crash-day budget already accounts for it because every open position counts against one combined number.

### What if Tuesday's rebuilt backtest disagrees with the provisional numbers?

Not a hypothetical. The figures throughout this plan came from a throwaway script, and reimplementation regularly produces different answers.

| If the rebuild shows... | Then |
|---|---|
| **Roughly the same** (3% clears, 1-2% do not) | Proceed. Update any figures that shifted. |
| **A different distance clears** | **Use that one.** The gate picks, not the plan. Update the submission copy. |
| **Nothing clears 2 SE** | Trade the best available at half size (Part 0's contingency), and **make the refusal the story.** Do not quietly lower the bar to manufacture a trade. |
| **The premium is positive everywhere** | Suspicious. Check for lookahead bias before believing it. A result that flatters us deserves more scrutiny than one that does not. |

**In every case the write-up reports what the rebuild found, not what this plan predicted.** The plan is a hypothesis. The rebuild is the evidence.

### Cold start: what every value is on the very first run

Unstated defaults are where systems misbehave on day one, so they are fixed here.

| Value | First-run default |
|---|---|
| **Peak equity** (for drawdown) | The account's starting equity, $100,000. Never undefined, never zero. |
| **Mode** | **MANUAL.** The first order of the project is always human-approved, regardless of what the config says. AUTO from the second session onward. |
| **Limits** | The evidence gate's recommendations. If the gate has not run, **the system refuses to trade** rather than falling back to guessed numbers. |
| **Open positions** | Read from Alpaca, never assumed empty. A fresh account genuinely has none, but the code must not depend on that. |
| **Audit log** | Created if absent. A missing log is not a reason to skip logging. |
| **Volatility forecast** | Naive estimate if the model has not been trained. Log which method produced it. |

### Costs are modelled in the backtest but must also be modelled live

The backtest sweeps a slippage haircut and shows the edge dies past roughly $0.10 per spread. **The live system has to respect the same number.**

- Real options carry per-contract exchange and clearing fees of roughly $0.03 to $0.05. **Paper trading charges none**, so paper P&L is optimistic by that amount. State it in the write-up.
- The Picker's limit-at-mid rule plus the cancel-if-unfilled discipline is what keeps live slippage inside what was tested. **Chasing a fill silently spends the entire edge.**
- Log the actual fill price against the mid at order time. That gives a real slippage figure to compare against the backtest's assumption, which is worth more than any prediction.

### Overnight gaps are unhedgeable, and that is already priced in

The market can gap down before we can react. There is no monitor cycle at 3am ET, and no order would help if there were.

**This is already accounted for:** the capped loss holds regardless of gap size. A 10% overnight crash costs exactly the same as a 4% one. This is the single strongest argument for defined-risk structures, and it belongs in the video.

### The Reviewer in AUTO mode

It still runs. AUTO removes the *human* approval step, not the model review.

- Reviewer says **approve** -> the trade proceeds
- Reviewer says **shrink** -> size is halved, **guards re-run**, then it proceeds
- Reviewer says **reject** -> skip the session, log the reason
- Reviewer **unavailable** -> fall back to MANUAL and ask the human

Autonomy means no human is required in the normal path. It does not mean removing checks.

### If no expiry has liquid strikes at the chosen distance

Fall back in this order:

1. Nearest listed strike **further out** at another expiry inside the 7 to 11 day window
2. If none qualify, **SKIP and log it**

Never fall back to a closer strike. Closer means more risk than the evidence gate approved, which is the one substitution that quietly invalidates the whole analysis.

## Why the AI is deliberately weak

The obvious design is "AI picks the trade, safety code checks it." We do the opposite.

An AI choosing bets would be an untested decision-maker sitting on a barely-significant edge, and its picks wouldn't match anything we tested. So plain code picks from tested rules, and **the AI can only veto or shrink.**

*The AI can only ever make us trade less.*

---

# PART 7 - Schedule

## 🎯 The plan: build everything TODAY, go live with a complete system

**Design decision that makes this work: the UI reads from files, not from live state.**

```
  backtest_results.json  ─┐
  evidence_gate.json     ─┼→  UI renders from these
  audit_log.jsonl        ─┤    (always has content)
  live Alpaca positions  ─┘    (added when they exist)
```

The dashboard's headline content - the premium table, the evidence gate, the decision log - **comes from the backtest, which exists before any trade does.** So the public URL is never empty, never a stack trace, and is fully presentable the moment the backtest finishes. Live positions layer on top when they appear.

This also means the video is filmable from Monday night, not dependent on trades having accumulated.

### Build order - strict dependency order, most valuable first

| # | Component | Why this position | Est. |
|---|---|---|---|
| **0** | **Write this plan into the repo** as `OPTIONS_SYSTEM_PLAN.md` + `VOLATILITY_ML_PLAN.md`, seed `PROGRESS.md`, add `LICENSE`, fix `.gitignore`, commit | **Do this first.** The plan currently lives only in a scratch directory. Getting it into the repo makes it survivable, reviewable, and part of the public submission. | 20 min |
| 1 | Account + keys + MCP running | Blocks everything | 30 min |
| 2 | `contracts.py` - OCC symbols, expiry calendar | Pure functions, no network, testable instantly | 30 min |
| 3 | `chain.py` - fetch + retry + liquidity filter | First real Alpaca call | 45 min |
| 4 | `vol.py` - annualized realized vol | Needed by selector and gate | 30 min |
| 5 | **`spread_backtest.py` + `evidence_gate.py`** | 🔴 **The long pole and the differentiator.** Everything downstream needs its output - including the UI's content. | 2–3 h |
| 6 | `risk/guards.py` - all 14 | Nothing trades without it | 1 h |
| 7 | `selector.py` - the 9 picker rules | Uses the gate's chosen distance | 1 h |
| 8 | `audit/log.py` | Schema first, before anything writes | 30 min |
| 9 | `broker.py` + `orders.py`, `dry_run=True` | Can dry-run end to end after this | 1 h |
| 10 | `monitor.py` - the 15-min loop | Nothing ever closes without it | 1 h |
| 11 | `ui/app.py` reading from files | Presentable immediately | 2–3 h |
| 12 | Deploy to Streamlit, `CONTROLS_ENABLED=false` | The submission requirement | 30 min |

**~12 hours of estimates, which for unfamiliar APIs usually means more.** Treat it as optimistic. The ordering is what matters: whatever gets finished is the *right* part: stop after #5 and you still have the finding, the differentiator, and something to film.

### Tonight's decision point (20:30 WIB, market opens)

| If by 20:30 you have… | Then |
|---|---|
| Through #9, dry-run clean | **Smoke test tonight** - 1 contract, MANUAL. Buys a 4th trading session. |
| Through #5 only | No orders. Print the exact spread you'd sell. Go live Tuesday. |
| Less than #5 | Stop building features. Finish the backtest. It's the differentiator and the UI's content. |

**Going live tonight is worth real points** - a 4th session is a 33% increase in trading days and in P&L opportunity. But **never place a first order without a clean dry-run**; a broken first trade costs more than a missed session.

---

## The week

**Today is Monday Aug 31.** Saturday and Sunday were meant to be build days and went into planning instead, so everything gets built today.

**Deadline: Fri Sep 4, 11:00 ET = 22:00 WIB Friday.**

Because your day runs ahead of ET, **you build during your daytime and trade that same evening.** That's the only reason a one-day build is survivable.

| When (WIB) | What | Non-negotiable? |
|---|---|---|
| **Mon 31, daytime** | **Build items #1–12 above.** Everything. | 🔴 |
| **Mon 31, 20:30** | Decision point (see table above). Smoke test tonight if dry-run is clean. | ⬜ |
| **Tue 1, daytime** | Finish anything unfinished. `recovery.py`. Deploy the UI if not already up. | 🔴 UI is a submission requirement |
| **Tue 1, 21:00** | **LIVE.** MANUAL for the first order, then AUTO. | 🔴 |
| **Wed 2, daytime** | **Experiment 12** if there's room. Otherwise start submission assets a day early - that buys slack. | 🟢 Exp 12 optional |
| **Wed 2, 21:00** | AUTO, full size. | ⬜ |
| **Thu 3, daytime** | **SUBMISSION ASSETS.** Video, slides, cover image, write-up, README, LICENSE, repo public, `.gitignore` fix. 6–8 hours. | 🔴 No partial credit |
| **Thu 3, 21:00** | Trade. Close anything at 50%+ profit to realize it. | ⬜ |
| **Fri 4, morning** | Dry-run the submission form. Fill every field. | 🔴 |
| **Fri 4, 20:45** | Final trade. | ⬜ |
| **Fri 4, 21:15** | Freeze. Screenshots: equity, positions, audit log. | 🔴 |
| **Fri 4, 21:30** | **SUBMIT.** 30 minutes of buffer. | 🔴 |

**Building it all today buys back the slack the weekend cost.** Wednesday becomes a buffer instead of a crunch, and if tonight's smoke test happens you get a 4th trading session.

### If today runs short - what to drop, in order

Build order #1–12 is ranked by value, so the honest fallback is simply "stop where you stop." But if you have to choose:

| Task | Cost of skipping | Drop order |
|---|---|---|
| `spread_backtest.py` + gate | **No differentiator, no UI content, nothing to film.** | ❌ Never |
| `monitor.py` | **Nothing ever closes.** Every exit rule becomes fiction. | ❌ Never |
| UI built + deployed | **Submission requirement failed.** | ❌ Never |
| `recovery.py` | Lose the partial-fill net - partly mitigated by Alpaca's coverage rule | 🟡 3rd |
| Full guard set (14) | Ship the 6 that bind: budget, per-trade cap, gate, expiry-day, liquidity, drawdown | 🟡 2nd |
| Experiment 12 | An ML result we already expect to be "the simple baseline won" | 🟢 **1st** |

### Experiment 12 - Wednesday, only if Tuesday is clean

**The expensive part is backtest infrastructure, not the forecast**, and `engineered_SPY.csv` already holds the features.

| Contender | What it is | Effort |
|---|---|---|
| **Naive** | Last week's volatility = next week's. One number, no model. | Minutes |
| **HAR-RV** | Weighted average of yesterday's, last week's, last month's volatility. A three-term linear regression. | ~30 min |
| **XGBoost** | Existing SPY features, existing pipeline | ~1 hour |

One metric (**QLIKE**), one walk-forward split. **Whichever wins ships.** If the naive baseline wins, that *is* the result and it gets logged - the literature says it usually does.

### What this week still costs us

- **Experiments 13 to 16 are out of scope**, presented as documented next steps
- **3 trading sessions** (Tue, Wed, Thu) plus a partial Friday - **4 if tonight's smoke test happens**
- **The rule ablations (Part 6) compete with build time** - run the cheap sweeps inside the backtest, defer the rest
- Wednesday is the only real buffer. Protect it.

### The rule for today

**Get to #5 - the backtest - no matter what.** It is the differentiator, the UI's content, and the thing that makes the video filmable. If the day collapses, a finished backtest plus a complete submission beats a half-built agent that misses the form.

## The deadline problem nobody had addressed

We submit **Friday 11:00 ET**. Our bets run 7–11 days. So **at submission we will be holding open positions that expire the following week.** Nothing in the plan said what to do about that.

**The issue:** if judging counts only *realized* profit, open bets contribute nothing and our score is whatever closed by Friday morning. If it counts *mark-to-market*, they count at current value - which for a healthy spread is a partial gain, and on Day 1 is a small paper loss (see Gotchas).

**Decision - assume mark-to-market, but don't depend on it:**

| Action | When | Why |
|---|---|---|
| Close anything already at 50%+ profit | Thu Sep 3 | Converts paper gains into realized ones. Costs nothing - that's our normal exit rule anyway. |
| Let healthy bets ride | Thu–Fri | If MTM counts, they help. If not, we lost nothing. |
| Place the Friday bet anyway | Fri 09:45 | It's the best-tested setup and demonstrates the system live, even though it books ~zero P&L before 11:00 |
| **Screenshot everything at 10:15** | Fri | Equity, positions, full log. **This is the submission evidence**, and it doesn't depend on how they score open bets. |

**Also state it plainly in the write-up:** "N bets remain open at submission with a combined mark-to-market of $X and a defined maximum loss of $Y." That turns an ambiguity into a demonstration that we know our exact exposure at all times - which is the point we're making anyway.

## Cut list, in order

1. The false-trip test - eyeball thresholds against the backtest table manually.
2. Multiple concurrent bets - run one at a time instead of up to four.
3. **The ML volatility model** - fall back to "assume vol stays the same," a legitimate forecast on its own. Log it as the Experiment 12 result either way.
4. **The Reviewer's MCP wiring** - fall back to the Alpaca CLI (allowed by the rules) or, worst case, feed it a plain text summary. *Decide Tuesday.*
5. **The Reviewer entirely** - if Gemini wiring fails, write the explanation by hand. But note this weakens the "AI logic" section of the required write-up, so cut it late.
6. The backtest - **only** if Tuesday collapses. Without it you're trading on vibes and have no differentiator.

**⚠️ AUTO mode was #1 on this list and has been removed.** The brief asks for an *autonomous* agent - cutting autonomy cuts the deliverable. See Part 0's scope check.

### ❌ Never cut - these are either safety-critical or submission-mandatory

| Item | Why |
|---|---|
| The Guard | The limits are meaningless without it |
| **`monitor.py` (15-min loop)** | **Alpaca has no broker-side brackets on multi-leg options - this is the only thing that ever closes a position.** Without it, every exit rule in the plan is fiction. |
| **The day-before-expiry close** | Prevents pin risk: a $0.01 in-the-money finish would assign us **$444,000 of stock** on a $100,000 account. This is now the worst scenario in the plan. |
| The audit log | Required for the write-up's "risk gates" section, and for any post-mortem |
| Dry-run mode | The only safe way to test |
| `recovery.py` partial-fill check | The one failure that can lose more than this plan says is possible |
| **The UI, deployed to a public URL** | **Hard submission requirement** - "working prototype accessible by URL" |
| **Public repo + MIT LICENSE** | **Hard submission requirement** |
| **Video + slides + cover image** | **Hard submission requirements** - no partial credit |

**The UI moved from cuttable to mandatory** once the lablab requirements were checked. It's also the best demo surface we have, since P&L will be small regardless - so this is a case where the requirement and the strategy happen to agree.

**Not live by Tuesday's session?** Stop building the trading logic. Place one bet manually. Spend everything left on the backtest, the UI, and the submission assets - **a beautiful submission with two trades scores better than a sophisticated bot that misses the submission requirements.**

## The pitch video - outline, since Presentation is scored

Never made one, it's a scored criterion, and lablab's own advice is *a 4-minute video that shows the thing working beats a polished 5-minute one that buries the demo.*

**Target 4 minutes. Lead with the working agent.**

| Time | What's on screen | What you say |
|---|---|---|
| **0:00–0:20** | The live dashboard, a real position open | *"This agent sells S&P 500 insurance. Here it is running. Every position's maximum loss is fixed before entry."* **Show the product first.** |
| **0:20–1:10** | The payoff table, loss flattening at −$473 | How a spread works - sell one contract, buy cheaper protection, loss capped by structure not by discipline |
| **1:10–2:10** | `EXPERIMENT.md`, then the premium table | *"We spent ten experiments failing to predict direction. Then we held this strategy to the same standard - and at the strikes most people sell, the premium is **negative**."* **This is the differentiator. Give it the most time.** |
| **2:10–2:50** | Evidence gate output; a logged SKIP | *"It only trades when the measured edge clears two standard errors. Here it is refusing."* |
| **2:50–3:30** | Mode selector, limits screen, an audit row | Risk architecture. *"The AI reviews every trade through MCP - with the order-placing tools removed. It can veto or shrink. It can never choose a trade or make one bigger."* |
| **3:30–4:00** | Equity curve vs SPY benchmark | Honest results. *"Three sessions is a sample, not proof. Here's what we'd test next."* |

**Practical notes:** record with QuickTime (built into macOS) or OBS. Record the screen and audio in one pass - editing costs more time than a retake. Have the dashboard showing a real position *before* you hit record. Write the script first and read it; improvising costs takes.

**The riskiest failure:** having nothing live to film. If Wednesday slips, **record the dry-run and the backtest output instead** - a working analysis is filmable even if the live agent isn't.

## The README - the first thing judges see on GitHub

| Section | Content |
|---|---|
| One-liner | What it does, in a sentence |
| The finding | The premium-is-negative table. **Lead with this** - it's the reason anyone should care. |
| How it works | The architecture diagram from Part 6 |
| Risk design | The guards table, and why there's no stop-loss |
| Honesty | Link to `EXPERIMENT.md` and to Part 9B's measured/cited/chosen audit |
| Run it | Setup steps, env vars, `--dry-run` first |
| Limits | Three sessions, one regime, what we didn't test |

## Final submission checklist (tick these Friday morning)

```
ALPACA
  [ ] New paper account, options level 3, trades placed
  [ ] MCP server (or CLI) demonstrably used
  [ ] One-page write-up: AI logic / risk gates / Alpaca infrastructure

LABLAB PLATFORM
  [ ] Public GitHub repo
  [ ] MIT LICENSE file present
  [ ] README explaining setup + the research story
  [ ] .gitignore fixed so plan docs are included
  [ ] Live app URL (Streamlit Cloud), loads for a stranger
  [ ] Pitch video, MP4, under 5 minutes
  [ ] Slide deck, PDF
  [ ] Cover image, PNG/JPG, 16:9
  [ ] Title + short description + long description
  [ ] Technology and category tags set

EVIDENCE
  [ ] Screenshots: equity, positions, audit log
  [ ] Open positions declared with max loss stated
```

---

# PART 8 - Implementation detail

## Files to create

```
pipeline/options/
├── config.py       SPY, DTE bounds, distance targets, width
├── contracts.py    option symbol build/parse, expiry calendar (pure)
├── chain.py        fetch live prices + retry + liquidity filter
├── vol.py          realized vol (annualized), forward-move distribution
└── selector.py     select_spread(chain, spot, vol_forecast, cfg) -> candidate | None

pipeline/volatility/
├── target.py       forward N-day realized vol as the label
├── baseline.py     "assume it stays the same" -- the bar to beat
└── model.py        XGBoost on SPY features; must beat baseline or it doesn't ship

pipeline/backtest/spread_backtest.py    expired-contract replay + sweeps
pipeline/backtest/evidence_gate.py      per-distance SE cushion (Part 2B); picks the tradable
                                         distance(s), or returns "none clear the bar"
pipeline/risk/options_config.py         the numbers from Part 5
pipeline/risk/guards.py                 check_*(state) -> (bool, reason); enforces the
                                         COMBINED crash-day cap, not per-bet caps stacked
pipeline/risk/false_trip.py             replay guards over backtested trades
pipeline/execution/broker.py            TradingClient (new paper keys)
pipeline/execution/orders.py            build the two-legged order
pipeline/execution/reconcile.py         desired vs actual; safe to re-run
pipeline/audit/log.py                   append-only JSONL
pipeline/agent/reviewer.py              the Reviewer: LLM approve/shrink/reject (cuttable)
pipeline/agent/modes.py                 MANUAL/SEMI-AUTO/AUTO; the "is this unusual?"
                                         test that decides when to ask a human
pipeline/risk/limits_store.py           3-tier limits: hard ceiling (code) /
                                         user setting (json) / recommendation (backtest)
pipeline/execution/recovery.py          reconcile-on-start, partial-fill detection
                                         and emergency single-leg close, heartbeat
pipeline/execution/monitor.py           ⭐ intraday position check every 15 min:
                                         50% profit target, day-before-expiry close,
                                         drawdown check. NOT optional - Alpaca rejects
                                         broker-side brackets on multi-leg options,
                                         so polling is the only exit path that exists.
pipeline/snapshot.py                    one SQLite snapshot per cycle (borrowed from
                                         Alpaca's reference architecture) - a single
                                         consistent view, no re-fetch races
pipeline/ui/app.py                      Streamlit: dashboard, limits, approvals, log
pipeline/run_agent.py                   daily entry, --dry-run default True
```

**This is the full target list. Part 7's build order is the subset that fits today**, ranked by value. These are in the file list but NOT in today's build order, and are honest stretch items: `volatility/*` (Experiment 12), `false_trip.py`, `modes.py`, `limits_store.py`, `snapshot.py`, `reconcile.py`, `recovery.py`. If a module is missing at submission, say so in the write-up rather than implying it exists.

## MCP - what it is, what it does, and exactly how we use it

The rules require **Alpaca's MCP Server or CLI**. Until this revision it appeared once in a table with no design and no test - a submission-invalidating gap hiding in plain sight.

### What MCP is - the banking app analogy

**Imagine handing someone your banking app so they can check your balance.** The full app also has a "transfer money" button. But you can give them a stripped-down version with transfer removed - they can see everything, and move nothing.

That is exactly what we're doing.

**MCP (Model Context Protocol)** is an open standard for giving an AI a set of real functions it can call, instead of only producing text. It's commonly described as *"USB-C for AI"* - one universal plug so any model connects to any tool ([Descope](https://www.descope.com/learn/post/mcp), [Google Cloud](https://cloud.google.com/discover/what-is-model-context-protocol)).

Three steps when it runs:

1. **Discovery** - the AI asks "what functions do you have?" and gets a list
2. **Invocation** - the AI calls one, e.g. `get_all_positions()`
3. **Response** - the server runs it against the real Alpaca account and returns real data

The point: the AI is **looking at live reality**, not reading a summary we wrote for it.

### ⚠️ The direct answer: yes, MCP can place trades. We switch that off.

Alpaca's MCP server ships with roughly 30 functions. Some **show** information. Some **take action**:

| Function | What calling it does |
|---|---|
| `get_all_positions` | 👁️ **Shows** what we currently hold |
| `get_account_info` | 👁️ **Shows** the balance |
| `get_option_chain` | 👁️ **Shows** current option prices |
| `place_option_order` | ⚠️ **Places a real order** |
| `close_all_positions` | ⚠️ **Closes every position** |
| `cancel_all_orders` | ⚠️ **Cancels everything** |

**By default the AI would get all 30**, including the bottom three. That would put an untested decision-maker in direct control of the account - the exact thing this plan's architecture exists to prevent.

So we don't hand it the default. The server accepts an `ALPACA_TOOLSETS` setting that controls which functions it exposes, and **we configure it to expose only the 👁️ ones.** The action functions aren't disabled, discouraged, or policed - they are **not present**. The Reviewer cannot call a function that was never given to it.

Orders are placed by our own plain Python code, which we unit-test and which behaves identically to what the backtest assumed.

### What Alpaca's MCP server can actually do

This matters, because it's **not read-only** ([alpacahq/alpaca-mcp-server](https://github.com/alpacahq/alpaca-mcp-server)):

| Category | Tools |
|---|---|
| **Account** | `get_account_info`, `get_account_config`, `get_portfolio_history`, `get_account_activities` |
| **Positions** | `get_all_positions`, `get_open_position` |
| **Options data** | `get_option_contracts`, `get_option_snapshot` (Greeks + IV), `get_option_chain`, `get_option_latest_quote` |
| **Market** | stock bars/quotes/trades/snapshots, `get_clock`, `get_calendar` |
| **⚠️ Orders** | `place_option_order` (**single and multi-leg**), `place_stock_order`, `cancel_order_by_id`, `cancel_all_orders` |
| **⚠️ Closing** | `close_position`, `close_all_positions`, `exercise_options_position` |

**The bottom two rows can place and cancel real trades.** Handing all of that to an LLM would put an untested decision-maker in direct control of the account - the exact thing this plan's architecture exists to prevent.

### How we use it - and how we enforce the restriction

| Job | Uses MCP? | Why |
|---|---|---|
| Fetching option prices for the Picker | ❌ No - direct `alpaca-py` | Must be deterministic and identical to what the backtest assumed |
| Placing and closing orders | ❌ No - direct `alpaca-py` | Execution stays in plain code that we unit-test |
| **The Reviewer checking account state** | ✅ **Yes** | This is what MCP is for - let it verify reality itself rather than trusting our summary |
| **The Reviewer inspecting the option chain** | ✅ **Yes** | So it can sanity-check the proposed spread independently |

**Enforcement is configuration, not a promise.** The server accepts an `ALPACA_TOOLSETS` environment variable that filters which tools it exposes. **We configure it to expose only the read tools.** The order-placing functions are not merely unused - they are **not present** in the Reviewer's tool list at all.

That's the difference between "we decided not to call it" and "it cannot be called," and it's worth stating exactly that way in the write-up:

> *The language model can query anything about the account and cannot place a single order, because the tools that place orders were never exposed to it.*

### Setup and verification

**Setup: TODAY (Mon)**, alongside account creation. Needs Python 3.10+, the `uv` package manager, and the same API keys. Configured via `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER_TRADE=true`, and `ALPACA_TOOLSETS` set to read-only. Minutes of work - do it while there's slack, not Friday morning.

**Two verification steps:**

1. The Reviewer answers "what do I currently hold?" through MCP, and the answer matches `get_all_positions()` called directly. Disagreement means MCP is misconfigured.
2. **Confirm `place_option_order` is absent** from the Reviewer's available tools. If it's visible, the toolset filter didn't apply and the restriction is decorative.

## The Reviewer - implementation detail (was unspecified until this revision)

The plan said "an LLM reviews the trade" without ever saying which model, how it's called, what it's given, or what happens when it fails. All four matter.

**Model: Gemini, free tier.** Confirmed sufficient:

| | Free tier gives | We need |
|---|---|---|
| Requests/minute | ~15 | 1 |
| Requests/day | ~1,000–1,500 | **1** |
| Function calling | ✅ included | ✅ required |
| Cost | $0, no card | - |

We make roughly **one call per trading session**. The free tier is ~1,000× more than required ([rate limits](https://tokenmix.ai/blog/gemini-api-free-tier-limits)). Use `google-genai`, key supplied by the user, stored in `.env` as `GEMINI_API_KEY` (never committed - same handling as the Alpaca keys).

**⚠️ One wrinkle: MCP was designed Claude-first.** Connecting it to Gemini needs a small conversion layer translating MCP's tool descriptions into Gemini's function-calling format. This is a solved problem with published examples ([Google Cloud walkthrough](https://medium.com/google-cloud/model-context-protocol-mcp-with-google-gemini-llm-a-deep-dive-full-code-ea16e3fac9a3), [FastMCP + Gemini guide](https://www.marktechpost.com/2025/04/21/a-step-by-step-coding-guide-to-defining-custom-model-context-protocol-mcp-server-and-client-tools-with-fastmcp-and-integrating-them-into-google-gemini-2-0s-function%E2%80%91calling-workflow/)) - but it is fiddly work on a four-day deadline.

**Fallback, written into the rules:** the requirement is "MCP Server **or** CLI." If the MCP-to-Gemini wiring isn't working by **Tuesday evening**, switch to the **Alpaca CLI** - trivially scriptable, satisfies the same requirement, no schema conversion. Decide by Tuesday, not Friday.

**What it receives:**
1. The spread the Picker chose (strike prices, width, contracts, credit, max loss)
2. The volatility forecast (calm / choppy / wild) and the evidence-gate cushion
3. Account state - **which it looks up itself via MCP**, rather than trusting our summary
4. The limits currently in force

**What it returns - a strict, validated structure, not free text:**

```json
{
  "decision": "approve" | "shrink" | "reject",
  "size_multiplier": 1.0 | 0.5,
  "reason": "one or two plain sentences for the log"
}
```

**Validation is not optional.** If the response doesn't parse, or `decision` isn't one of the three, or `size_multiplier` exceeds 1.0 - **the response is discarded and treated as "reject."** A malformed answer must never be interpreted generously. Note the schema itself makes upsizing unrepresentable: there is no value of `size_multiplier` above 1.0 that the system will accept.

**If the Reviewer fails entirely** (API down, timeout, repeated malformed output):

| Mode | Behaviour |
|---|---|
| MANUAL | No change - a human was approving anyway |
| **SEMI-AUTO** | **Fall back to MANUAL** - ask the human instead of proceeding unreviewed |
| **AUTO** | **Fall back to MANUAL** - same reason |

We do *not* simply skip the review and trade anyway. The Reviewer only ever reduces risk, so losing it means losing a safety check - and the correct response to losing a safety check is more human oversight, not less.

## The audit log - schema fixed now, not later

`TRADING_SYSTEM_PLAN.md:338` warns that retrofitting an audit log is painful and growing one is free. Same applies here. One append-only JSONL row per decision, **including every decision not to trade**:

```
timestamp · mode · spy_price · vol_forecast · gate_distance · gate_cushion_se
· proposed_contracts · proposed_credit · proposed_max_loss
· guards_checked · guards_failed · budget_remaining
· reviewer_decision · reviewer_multiplier · reviewer_reason
· human_action · order_id · fill_price · both_legs_confirmed
· outcome · realized_pnl
```

`guards_failed` and `reviewer_reason` are what make a "why didn't it trade?" question answerable. `both_legs_confirmed` is what makes the one-leg emergency auditable after the fact.

## When it runs - two loops, not one

This was a single daily run until Alpaca's reference architecture made the gap obvious.

| Loop | Frequency | Does what |
|---|---|---|
| **Decision loop** | Once, **10:00 ET** | Evaluate, propose, review, maybe open a position |
| **⭐ Position monitor** | **Every 15 min while market is open** | 50% profit target, day-before-expiry close, drawdown check |

### Why the monitor is mandatory, in plain words

**With stocks**, you can leave standing instructions with the broker: *"sell this automatically if it reaches $50 profit, or if it falls $200."* Set once, and the broker watches the price all day for you. You can go to sleep.

**With option spreads, Alpaca doesn't allow that.** When placing the order you may only say one of two things:

- "Do this now, at whatever price is available" (MARKET)
- "Do this only at exactly this price" (LIMIT)

Confirmed in the SDK: multi-leg option orders accept MARKET and LIMIT only (`requests.py:243-252`). **You cannot attach any "…and close it later when X happens" instruction.**

**So nobody is watching our positions except us.**

Every exit rule in this plan - close at 50% profit, close near the strike price at expiry, force-close on expiry day - **is just words unless something actively checks.** The broker will not do it.

Think of a kitchen timer. With stocks you set the timer and it rings. With option spreads there is no timer, so you have to keep walking back to the oven.

**The hole this closes:** the plan previously had the bot waking once daily at 10:00. A position hitting its profit target at 10:30 would sit unmanaged for 23 hours. Polling every 15 minutes isn't a refinement here - **it is the entire exit mechanism.**

The decision loop deliberately avoids the open - the first 15 minutes have the worst option prices, which is also why the first smoke test is 09:45–10:15 ET (20:45–21:15 WIB).

No market holidays fall inside the window (Labor Day is Sept 7, after the deadline). Both loops call `get_clock` rather than assuming the market is open.

**Time-zone consequence:** the monitor must run unattended from 20:30 to 03:00 WIB. It cannot depend on you watching - see the time-zone section above.

## 🚨 Deployment: the public app cannot be the controlling app

**A hole this plan had until now.** The submission requires a *"working prototype accessible by URL."* But our UI has an **Approve trade** button, **limit sliders**, and a **stop button**.

**A public URL with those controls means anyone who finds the link can approve trades on our account.** That is not a theoretical risk - the URL gets handed to judges and posted publicly.

### Two instances, one codebase

| | **Public (Streamlit Cloud)** | **Local (your machine)** |
|---|---|---|
| Dashboard, positions, equity | ✅ Visible | ✅ Visible |
| Audit log | ✅ Visible | ✅ Visible |
| Approve / reject trades | ❌ **Disabled** | ✅ Enabled |
| Change limits | ❌ **Read-only display** | ✅ Enabled |
| Stop button | ❌ Disabled | ✅ Enabled |
| Runs the trading loop | ❌ Never | ✅ Yes |

One environment variable - `CONTROLS_ENABLED` - gates every action. Default **off**, so a misconfigured deploy is safe rather than dangerous.

### The public app is a viewer, not the bot

Streamlit Cloud apps sleep when idle, so they cannot host a scheduled trading loop. **The bot runs on your machine; the deployed app displays what it did.** It reads live equity and positions straight from Alpaca (read-only), plus the audit log from the repo.

**Secrets:** Streamlit Cloud has its own secrets manager. API keys go there - never committed, never in `.env` inside the repo.

## 🕐 Time zones - the trading window lands in your evening

**Also missing until now, and it affects every day of the schedule.**

US markets run 09:30–16:00 ET. In September that's UTC−4. Working from Indonesia (WIB, UTC+7), that's an **11-hour offset**:

| Event | ET | **WIB (your time)** |
|---|---|---|
| Market open | 09:30 | **20:30** |
| **Bot's daily run** | 10:00 | **21:00** |
| Monday smoke test | 09:45–10:15 | **20:45–21:15** |
| Market close | 16:00 | **03:00 next day** 😴 |
| **Submission deadline** | **Fri 11:00** | **Fri 22:00** |

**Consequences to plan around:**

1. **Supervised trading happens ~21:00 nightly.** MANUAL and SEMI-AUTO both need you awake then. Build during your day, trade in your evening.
2. **The day-before-expiry close fires around 15:00 ET, which is 02:00 WIB.** You will not reliably be awake. **This must be fully automatic** - it cannot depend on a human, which is exactly why it is coded as a hard rule rather than a judgment call.
3. **The deadline is 22:00 WIB Friday**, not some comfortable morning hour. Submission assets must be *finished* Thursday, not started Friday.
4. **Verify the ET↔WIB offset against a real clock** before Monday. Getting this wrong by an hour means missing the smoke test window.

### If nobody answers an approval request

SEMI-AUTO can ask for approval at 21:00 while you're eating, asleep, or away.

**Rule: an unanswered approval request expires after 30 minutes and becomes a SKIP.** Never a default approve. A missed trade costs nothing; an unsupervised trade costs the entire point of having the mode.

## Failure handling is not optional plumbing

`recovery.py` is the one module that must be correct even if everything else is rough. Its three jobs, in priority order:

1. **Reconcile before acting** - on every start, read positions from Alpaca and treat that as truth. Never act on local state.
2. **Detect a one-legged fill** - after every submission, verify *both* legs exist. If only one does, close it at market immediately and halt. This is the only place in the system authorised to place an unplanned order, and it may only ever *reduce* risk.
3. **Heartbeat** - record every successful cycle. If >4h stale with open positions, alert regardless of mode.

## Reuse vs write fresh

**Reuse:**
- `news_extract.py:47-57` (retry/backoff) + `:77` (rate limit) → the pattern for `chain.py`. **Not** `extract.py:17` - no retry, no checkpointing.
- `eval.py:38` non-overlapping discipline → always report `n_eff` and a confidence interval, never a bare Sharpe.
- `model/baseline_model.py` → the *shape* of Experiment 12's baseline comparison.
- `TRADING_SYSTEM_PLAN.md:301` reconciliation design (send the difference, idempotent).
- `raw_SPY.csv` for spot - **not** `engineered_SPY.csv`, which contains `fwd_5d_return`, the answer key.
- SPY features already in `engineered_SPY.csv` (`volatility_5/10`, `ATR_5/10`, `RSI`, `momentum_*`) → inputs to the vol model.

**Write fresh:**
- Volatility measurement. `transform.py:62-63` is un-annualized std of *simple* returns; options need log returns × √252. New function in `options/vol.py`. **Do not patch `transform.py`** - the ML experiments must stay reproducible.

## 📚 Documentation review - findings that change the design

Read after the architecture kept springing surprises. Sources: [Options Trading](https://docs.alpaca.markets/us/docs/options-trading), [Level 3 Trading](https://docs.alpaca.markets/us/docs/options-level-3-trading), [Level 3 risks](https://alpaca.markets/support/what-risks-should-you-consider-before-using-level-3-options-trading), [short option expiry](https://alpaca.markets/support/what-happens-when-my-short-option-position-expires), [automatic exercise](https://alpaca.markets/support/what-is-automatic-exercise).

### 🔴 NEW DANGER - pin risk. Our "max loss" can be true and still wreck the account.

**Alpaca auto-exercises any long option that finishes in the money by $0.01 or more**, by 6:00 PM ET on expiry day. Assignment on short options follows the same logic.

Now consider SPY closing at **$739.99** - one cent below our $740 strike, comfortably above our $735 protection:

| Leg | Outcome |
|---|---|
| Short $740 put | **ITM by $0.01 → we get assigned** |
| Long $735 put | OTM → expires worthless, protects nothing |

We are forced to **buy 100 shares per contract at $740**. At 6 contracts that's **600 shares × $740 = $444,000 of stock in a $100,000 account.**

The *economic* loss is about $6. **The position is $444,000.** Instant margin call, forced liquidation, and a P&L display that looks catastrophic on submission day.

**This is the single worst scenario in the plan and the payoff table in Part 1B does not show it** - that table assumes both legs settle against each other, which only happens below $735.

**The fix - simpler and stricter than the old rule:**

```
  Close EVERY position no later than the day BEFORE expiry.
  Never hold an option position into its expiration day. Ever.
```

**Cost:** we forfeit the final day of time decay - a small, quantifiable amount.
**Benefit:** assignment risk drops to approximately zero, because we're never holding anything when auto-exercise runs.

This **replaces** the old "close if within 0.5% of strike on expiry day" rule. That version left us exposed exactly in the $735–$740 band, which is where pin risk lives.

**Also:** Alpaca stops accepting orders that open or extend positions from **3:30 PM ET on expiry day** - the old plan's "force-close by 15:30 ET" was cutting it to the minute. Now moot, since we're out a day earlier.

### 🟢 GOOD NEWS - the one-leg risk was overstated

> *"An MLeg order is accepted only if all its legs are covered within the same MLeg order."*

**Alpaca refuses to accept a multi-leg order that would leave a short leg uncovered.** The package is validated as a unit. That substantially reduces the "sold insurance with nothing behind it" scenario I called the worst realistic failure.

**Keep the check anyway** - the guarantee is about order *acceptance*, not fill mechanics, and paper simulation may behave differently. But:
- **Downgrade it** from "the one thing that can exceed our max loss" to "verify on the first live order"
- **Pin risk now holds that title instead**

Honest note: this correction is *why* reading documentation matters. I'd built a whole never-cut module around a risk the platform already mitigates, while the genuinely dangerous one went unmentioned.

### 🟢 GOOD NEWS - paper accounts get Level 3 automatically

> *"All paper trading accounts will automatically have access to Level 3 strategies."*

Credit spreads are explicitly Level 3 ([Alpaca's own list](https://alpaca.markets/learn/level-3-options-trading) names credit spreads and iron condors). **The "verify level 3" task is now a confirmation, not a blocker.**

### Mechanics confirmed

| Rule | Detail | Impact |
|---|---|---|
| **Closing a spread** | Use `position_intent: buy_to_close` / `sell_to_close` in an MLeg order | Close as a package, not leg by leg |
| **Ratio must be simplest form** | GCD across all `ratio_qty` must equal 1 | Our 1:1 spread is fine |
| **No equity legs in MLeg** | Can't mix stock and options in one order | If ever assigned shares, unwind separately |
| **Margin: "universal spread rule"** | Maintenance margin = theoretical max loss across all legs | Confirms our $473 collateral math |
| **Time in force** | `day` or `gtc` only | Use `day`, as planned |
| **Order types** | market, limit, stop, stop_limit - **stop is single-leg only** | Confirms: no broker-side stop on a spread |
| **⚠️ Paper sync delay** | Exercise/assignment/expiry activities "are synced at the start of the following day" | **A Thursday expiry may not show final numbers until Friday.** Plan P&L reporting around this. |
| **Dividend assignment risk** | Alpaca warns short positions can be assigned around dividends | SPY's next ex-dividend is ~Sept 18, **after our window**. Not a factor, but confirm. |

## Gotchas (verified against alpaca-py 0.44.0 and the live API)

- Multi-leg works: `OrderClass.MLEG`, `OptionLegRequest` (`requests.py:169`). 2–4 legs, `qty` required, `notional` forbidden.
- **MLEG accepts MARKET and LIMIT only** (`requests.py:243-252`). No broker-side stop on a spread - poll it ourselves.
- **Always LIMIT.** The entire edge lives inside $0.10 of slippage.
- **Verify the net-price sign convention on the first 1-lot order.** Don't guess. Don't scale until confirmed.
- **IV and greeks are often `None`** on real chains. `snap.greeks.delta` will crash. Filter first, fall back to percentage-based selection.
- **Filter chain queries** - a 5-day expiry window returned 2,070 contracts.
- Collateral comes from `options_buying_power` ($100k), not `buying_power` ($400k). ~$450/contract.
- **Historical option bars contain junk** - found a Saturday-dated bar with identical OHLC across two strikes. Filter to real sessions; check prices rise with strike.
- **Day 1 will show an unrealized loss.** We cross the spread on entry; Alpaca marks at mid. Expect −$5 to −$15/contract immediately. **Write this down before Monday so nobody panics.**
- Paper fills better than live, doesn't simulate assignment, charges no fees (~$0.03–0.05/contract live). Say so in the write-up.

## Verification

1. Selector runs against a saved weekend snapshot - emits a full bet or a clean `None`, never crashes on missing greeks.
2. Backtest self-checks: prices rise with strike, real session dates only, `n_eff` beside every Sharpe, reproduces the 3% cell (charged 5.4% vs actual 2.5%).
3. **Experiment 12 reports both** the baseline and the ML score. Whichever wins ships. Result goes in `EXPERIMENT.md` either way.
4. Guard unit tests on fake account states: at the drawdown line, one dollar over, at max bets, with `IV=None`.
5. False-trip: no gate blocks >30% of winners.
6. `python -m pipeline.run_agent --dry-run` prints the bet, writes an audit row, sends nothing.
7. Live smoke test Monday: 1 contract - confirm fill, both legs, audit row, price sign.
8. Run twice - the second run must submit nothing.
9. **Partial-fill drill:** simulate a one-legged fill (fake the position state) and confirm `recovery.py` closes the orphan leg and halts. **Test this before it matters** - it's the failure with the worst consequences and the least warning.
10. **Reconcile drill:** manually open a position outside the bot, then start the bot. It must notice and account for it, not ignore it.
11. **Limits drill:** set a limit looser than recommended in the UI, confirm the warning appears and the override is written to the audit log. Set one above the hard ceiling, confirm it's refused outright.
12. **Mode drill:** in SEMI-AUTO, force an "unusual" condition and confirm it asks instead of trading.
13. **MCP drill:** the Reviewer answers "what do I currently hold?" through MCP, and the answer matches `get_all_positions()`. Disagreement means MCP is misconfigured - and MCP is a hard submission requirement, so this must pass before Friday.
14. **Budget drill:** open bets until the $12,000 crash-day budget is nearly spent, then confirm the next bet is either sized down to fit or refused - not waved through because a slot was free.
15. **Expiry-rule drill:** confirm a position is closed the day *before* expiry, unconditionally - and that mere price proximity with 9 days left does **not** trigger a close.
16. **🚨 Public-deploy safety drill:** open the deployed Streamlit URL in a private browser window and confirm **every control is absent or inert** - no approve button, no editable limits, no stop. A stranger must be able to look and do nothing. Test this *before* sharing the link anywhere.
17. **Timeout drill:** trigger an approval request and don't answer it. After 30 minutes it must resolve to SKIP, with a log row saying so - never to an approval.
18. **Overnight drill:** confirm the day-before-expiry close fires without any human present. It runs in the middle of your night; it cannot depend on you being awake.
19. **Secrets drill:** confirm no API key appears anywhere in the public repo or in the deployed app's page source. Check Streamlit secrets are used, not a committed file.
20. **🔴 Pin-risk drill:** simulate a position still open on its expiry date and confirm the system closes it immediately at any price rather than letting it run to auto-exercise. **This is the worst scenario in the plan** - test it deliberately.
21. **Coverage-rule check:** on the first live order, confirm whether Alpaca fills both legs as a package (its docs say an MLeg order is only accepted if all legs are covered within it). If confirmed, partial-fill risk drops from severe to minor - **record the finding either way**, since the plan currently assumes the worse case.
22. **🔴 Cold-open drill:** open the deployed URL in a private window, **outside market hours, with zero open positions.** It must render something meaningful - backtest results, the evidence-gate table, the decision log - never a blank page or a stack trace. **This is how a judge will first see it.**
23. **Stranger test:** hand the URL to someone who knows nothing about the project. If they can't tell what it does within 30 seconds, the dashboard needs a one-line explanation at the top.

---

# PART 9 - What we admit openly

1. **We overfit during research.** 13+ configurations tested against the same 120 observations. The best result sits ~2.2 standard errors from zero *before* multiple-testing correction, and isn't significant after. **Log all 13 in `EXPERIMENT.md`** - reporting only the winner is the exact mistake ten experiments were spent avoiding. This is also *why* Part 2B's evidence gate exists: picking "3%" because its row had a checkmark would have been the same mistake in a different costume.
2. **The strategy is shaped like a known failure pattern, and we're saying so rather than hiding it.** Small steady wins against rare large losses is the "picking up pennies in front of a steamroller" pattern, and its canonical real-world failure (Volmageddon, 2018) wiped out a popular fund overnight. Our defenses against it: (a) every position is capped-loss by construction, (b) the evidence gate requires the win-rate cushion to clear noise, not just be positive, (c) all open positions are risk-capped as one combined crash event, not stacked independent ones.
3. **The backtest is currently scratch work.** A research agent produced it; it is not in the repo. Tuesday's job is rebuilding it as real code. **Don't cite numbers you haven't reproduced yourself.**
4. **Option history only goes back to Feb 2024** - about 2.5 years, one broad market regime. Same single-regime weakness Experiment 6d found in the equity work.
5. **This is not market-neutral, and the exposure is larger than the account.** These bets profit when the market rises or holds. A full book runs about **120 share-equivalents, roughly $92,000 of SPY notional** against $100,000 of equity. Loss is still capped at $12,000, but "capped risk" must never be read as "no market exposure." Experiment 6d's 54%-beta finding applies fully.
6. **The best-tested entry day is Friday**, which inside our window only exists at the deadline itself. Every trade we actually place is a weaker-tested configuration, chosen for schedule reasons rather than evidence. Say so explicitly.
7. **Three or four sessions proves nothing.** Whatever P&L we post is one sample. We report it as a sample, not as evidence the strategy works.
8. **XSP** would remove the assignment danger entirely (cash-settled, no shares) but came back thin and often `None`. Staying with SPY for liquidity; naming XSP as the known improvement.
9. **Three numbers in this plan were mutually contradictory until this revision** (per-bet cap × max bets ≠ combined cap; drawdown triggers tighter than a single expected loss; the assignment rule silently reintroducing the stop-loss we'd argued against). They're fixed, but the fact they survived several drafts is itself worth noting - **a plan is not self-consistent just because each section reads well on its own.** Re-check the arithmetic across sections after any change to sizing.

---

# PART 9B - Where every number comes from (the honesty audit)

You asked whether everything is data-supported. **It isn't, and pretending otherwise would repeat the exact mistake this project spent ten experiments learning to avoid.** Every number in this plan falls into one of three categories.

## 🟢 MEASURED - from our own data

| Number | Source |
|---|---|
| 3% distance is the only one where we're overpaid (market charged 5.4%, reality delivered 2.5%) | 120-week expired-contract replay |
| 1% and 2% distances are *underpaid* (18.1% vs 22.5%; 9.8% vs 11.7%) | Same replay |
| 2-day trades lose at every distance tested | Same replay |
| SPY *touches* −3% 42% of the time but *closes* below it 16% of the time (2.6×) | SPY daily history, 2020–2026 |
| Breach probabilities by distance and horizon | SPY daily history |
| Effective sample is ~54–332 independent windows, not thousands | Non-overlapping count, `eval.py:38` discipline |

## 🔵 CITED - from published research

| Claim | Source |
|---|---|
| A volatility premium exists and compensates asymmetric risk | [Skew premium research](https://arxiv.org/pdf/1409.7720) |
| This strategy shape has a documented failure mode | [Steamroller analysis](https://www.sharpetwo.com/p/picking-up-pennies-in-front-of-a), [Volmageddon](https://www.ebc.com/forex/volmageddon-explained-when-volatility-turns-violent) |
| Simple HAR-RV is hard to beat when the feature set is limited | [Financial Innovation review](https://link.springer.com/article/10.1186/s40854-025-00809-5) |
| Forecast accuracy ≠ trading profit | [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1059056020302513) |
| IV−RV predicts returns (but needs intraday data we don't have) | [Bollerslev/Tauchen/Zhou](https://public.econ.duke.edu/~boller/Published_Papers/rfs_09.pdf) |
| News volume predicts volatility better than direction | Experiment 9's own research check |

## 🟡 CHOSEN - judgment calls, NOT derived from data

**This is the honest list, and it's longer than the other two.**

| Number | Basis | Could we test it? |
|---|---|---|
| $3,000 max loss per bet (3%) | Your decision, given a paper account | Not a testable question - it's a risk preference |
| $12,000 crash-day budget | Follows from 3% × 4 bets | Preference, not finding |
| 4 concurrent bets max | Round number | Could sweep, didn't |
| **50% profit target** | **Industry convention. We did NOT test it.** | ✅ **Yes - sweepable in the backtest. Post-hackathon.** |
| 7–11 days to expiry | Partly measured (7-day Friday was the best cell), partly convention | Partly tested |
| 2-standard-error cushion bar | Standard statistical convention | It's the convention, not a finding |
| Day-before-expiry exit (vs holding to expiry) | Judgment, driven by Alpaca's $0.01 auto-exercise rule | ✅ Cost is measurable: one day of decay |
| 2-day assignment window | Judgment - assignment is an expiry event | Could test against historical assignment data we don't have |
| −5% / −8% drawdown stops | Set so one expected loss doesn't halt the system | ⚠️ Should pass the false-trip test before trusting |
| 25% volatility skip threshold | Judgment | ⚠️ Should pass the false-trip test |
| 4-hour heartbeat | Operational judgment | No |
| 30% false-trip rejection threshold | Judgment about an acceptable false-alarm rate | No |
| 10% hard ceiling | Your setup choice | Preference |
| Liquidity filters (OI ≥ 500, spread ≤ 15%) | Common practice | Could sweep |

## What this means

**The strategy is data-supported. Most of the risk parameters are not - they're conventions and preferences.** That's normal and defensible, but only if stated.

Two consequences the plan already reflects:

1. **The false-trip test exists precisely to convert some of these from "chosen" to "at least checked."** Any threshold that blocks >30% of historical winners is mis-set. That doesn't make them optimal, it makes them non-harmful.
2. **The 50% profit target is the most glaring untested number**, because it directly affects P&L on every trade and *is* testable with the data we already have. It's convention, we're using it, and it goes on the post-hackathon list.

**In the write-up, say this plainly.** A team that can tell you which of its numbers are measured and which are guessed is more credible than one presenting fourteen confident parameters with no provenance.

---

# PART 10A - Operating modes

Three modes. The mode decides **who pulls the trigger**, never **what the limits are** - limits apply identically in all three.

| Mode | Bot does | Human does | Use when |
|---|---|---|---|
| **MANUAL** | Analyses, recommends, waits | Approves or rejects every trade | The first smoke test. Demos. |
| **SEMI-AUTO** | Trades inside normal conditions; **asks** when anything is unusual | Approves only exceptions | When you want oversight without babysitting |
| **AUTO** | Everything, unattended | Watches; can hit stop | ✅ **The default, from the second session onward. This is what the brief asks for.** |

**One exception, hard-coded:** the very first order of the project runs in MANUAL regardless of configuration. That is a launch check, not a trust level, and it is where the net-price sign convention and the both-legs-filled behaviour get confirmed by eye.

**Why AUTO is the default, not the risky option.** The brief asks for an *autonomous* agent. Autonomy is safe here because the LLM never decides anything: fixed rules pick the trade, hard limits gate it, and the Reviewer can only shrink or veto. Nothing about unattended operation removes a safeguard.

There's also a practical argument - the trading day runs 20:30–03:00 your time. A design that *requires* you awake at 02:30 to close positions isn't a working system.

## What counts as "unusual" in SEMI-AUTO (triggers an approval request)

- Volatility forecast is in its top tercile (choppy/wild)
- The proposed size is at or near the per-trade cap
- Account is already down for the week
- Any guard *nearly* fired (within 10% of a limit)
- The evidence gate's cushion is thin (between 1.5 and 2 SE)
- The Reviewer raised an objection

Everything else fills automatically. In practice this means most quiet days are hands-off, and the human is only pulled in when it actually matters.

## Mode is itself a guarded setting

Switching **MANUAL → SEMI-AUTO → AUTO** requires an explicit confirmation and is logged. Switching *down* toward MANUAL is always instant and never blocked. **Loosening is friction; tightening is free.** Same principle as the limits below.

---

# PART 10B - Human-in-the-loop limits

Yes - **the human sets the numbers.** All of them: max loss per trade, max total, max bets open, drawdown stop, distance, days-to-expiry, profit target. Every one is yours to change, and the bot shows its recommendation next to each.

But there's a distinction that matters, and I stated it badly before.

## Numbers vs. structure

Some things in this system are **limits** (a quantity you pick). Others are **structure** (the thing that makes limits mean anything at all).

| Type | Examples | Editable? |
|---|---|---|
| **Numbers** | Max loss $3,000 · max 4 bets open · stop at −4% · sell 3% out · 7–11 days · take profit at 50% | ✅ **Yes, all of them** |
| **Structure** | Every position must have its protective leg · close on assignment risk · reconcile before acting · one-leg fill triggers emergency close | ❌ **No** |

**Why structure isn't editable - the concrete reason:**

"Max loss $3,000" is only a true statement *because* leg 2 exists (Part 1). Turn off the protective leg and "$3,000" isn't a limit anymore, it's a wish - the real answer becomes "$14,000, or more, depending on how bad the crash is."

So the structural rules aren't a stricter tier of the same thing. **They're the machinery that makes your numbers real.** Editing them wouldn't give you more freedom, it would silently make every number on the limits screen a lie.

That's the whole list, though. Four rules. Everything else is yours.

## The ceiling - and your objection to it

Fair challenge: *it's paper money, why can't I set max loss to 100%?*

You can. But **not from the UI while it's running.** The ceiling is set once, deliberately, in a config file at setup - and cannot be raised from the dashboard mid-session.

The reason isn't that we know better than you. It's that the version of you setting limits calmly before launch and the version of you down $4,000 mid-session are making decisions under very different conditions, and only one of them should be allowed to raise the ceiling. **The ceiling protects against tilt, not against judgment.**

Lower it from the UI anytime. Raising it means opening the config, which is enough friction to require actually meaning it.

## Three tiers

```
  ┌─────────────────────────────────────────────┐
  │  CEILING - set once at setup, in config     │  ← lower anytime from UI,
  │  e.g. never >10% of account on one trade    │     raise only in the file
  ├─────────────────────────────────────────────┤
  │  YOUR SETTING - you choose, freely          │  ← the slider
  │  Tighter than recommended: no friction      │
  │  Looser than recommended: confirm + logged  │
  ├─────────────────────────────────────────────┤
  │  OUR RECOMMENDATION - from the backtest     │  ← shown, never enforced
  │  "2.1 SE cushion at this level"             │
  └─────────────────────────────────────────────┘
```

**Why not just let the bot decide?** The recommendation comes from 120 observations with wide error bars. It's a well-informed suggestion, not a fact. You should be able to say "I don't care what the backtest says, go smaller" - or larger, within the ceiling you set.

## The limits screen

```
┌────────────────────────────────────────────────────────────────┐
│  LIMITS                                    Mode: [SEMI-AUTO ▾] │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Max loss per trade                                            │
│  ├──────────●──────────────────────────┤   $3,000  (3.0%)      │
│  $0                                $10,000 ← hard ceiling      │
│  ✓ Recommended: $3,000 - cushion 2.1 SE at this size           │
│                                                                │
│  Max loss if everything fails at once (crash day)              │
│  ├────────●────────────────────────────┤   $5,000  (5.0%)      │
│  ⚠ Remember: all bets fail together. This is ONE number,       │
│    not 4 separate ones.                                        │
│                                                                │
│  Max bets open at once                                         │
│  ├──────────────●──────────────────────┤   4                   │
│                                                                │
│  Stop everything if account drops                              │
│  ├────●────────────────────────────────┤   4.0%                │
│  ✓ Recommended: 4.0%                                           │
│                                                                │
│  Distance from price                                           │
│  ○ Let the evidence gate decide  (recommended)                 │
│  ● Fix it manually:  [ 3.0 % ]                                 │
│  ⚠ You've overridden the gate. Measured cushion at 3.0%        │
│    is 1.8 SE - below the 2.0 SE bar. Confirm?  [ Confirm ]     │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                       [ Save ]    [ Reset to recommended ]     │
└────────────────────────────────────────────────────────────────┘
```

Notice the bottom warning: that's the 1.8-SE finding, surfaced live instead of buried in a document. The UI's job is to make the honest number impossible to miss at the moment you'd act on it.

**⚠️ The "2.1 SE" and "2.4 SE" figures in these mockups are placeholders showing what a *passing* gate looks like.** The only cushion actually computed so far is **1.8 SE at 3%, which does not clear the bar** (Part 2B). Do not mistake mockup numbers for measurements, in the video or anywhere else.

---

# PART 10C - When things go wrong

The question "do we just do nothing?" has a **different answer depending on what failed**, and getting this wrong is dangerous.

## The core principle

> **Failing to OPEN a trade is safe. Failing to CLOSE one is not.**

Doing nothing is a perfectly good response to "I couldn't place a bet." It is a terrible response to "I have a position expiring today and I can't reach the broker." So the system treats those two paths completely differently.

## Failure table

Every failure lands in one of three buckets.

### 🟢 Bucket 1 - "We couldn't place a bet today"

**All of these are fine. Genuinely. The answer is do nothing.**

Not placing a bet costs us nothing - no position, no risk, no obligation.

- Internet down / Alpaca unreachable
- Option prices missing or unreadable
- Broker rejected our order
- Our price was too optimistic, nobody took it

**Response: skip today, write a log line, try tomorrow.** One rule only - *don't retry blindly.* A rejection means something was wrong; find out what before resending.

### 🟡 Bucket 2 - "We're holding something and lost track of it"

**Needs attention, not panic.**

The danger isn't the position - it's *not knowing about* the position. A bet nobody is watching is a bet nobody will close.

- Bot crashed partway through
- Bot never started (laptop asleep, schedule didn't fire)
- A position exists that the bot has no record of
- Market-wide trading halt

**Response: the broker is always the truth.** On every startup the bot asks Alpaca "what do I actually own?" and believes that over its own notes. Plus a **heartbeat** - no check-in for 4 hours with open bets triggers an alert. Silence is treated as a problem, not as "all clear."

### 🔴 Bucket 3 - the only two that can really hurt

**A. Only one leg filled.** We sent two contracts as a package; one went through.

- Only **leg 2** (our protection) filled → harmless, ~$18 wasted
- Only **leg 1** (the sold one) filled → **we've sold insurance with nothing behind it.** The $473 cap doesn't exist. A crash could cost $14,000.

*Response: automatic and instant.* Close the orphan at whatever price, halt everything, alert. No waiting to see if the other fills.

**B. We're still holding a position on expiry day.** This should now be impossible - the rule is to close the day *before* expiry - but if it happens, it's the scenario that ends with **hundreds of thousands of dollars of SPY stock** in a $100,000 account. Alpaca auto-exercises anything $0.01 in the money.

*Response: close immediately, at any price. Alert loudly. If the broker is unreachable, a human must intervene.* This is the one case the system cannot fix itself, and the day-early exit rule exists so we never reach it.

### Also covered, for completeness

| What broke | Bucket | Response |
|---|---|---|
| The Reviewer (LLM) is down or returning nonsense | 🟢 1 | Fall back to MANUAL mode - ask the human. Never trade unreviewed. |
| MCP server won't start | 🟢 1 | Trading is unaffected (execution doesn't use MCP), but **it's a submission requirement** - fix before Friday. |
| New paper account came back at options level 1 or 2 | 🟢 1 | **Blocks everything.** Spreads need level 3 - though paper accounts get it automatically. Confirm first thing. |
| Evidence gate says no distance qualifies | 🟢 1 | Don't trade. Write it up as the result. Part 4 already treats this as a legitimate outcome. |
| Volatility forecast unavailable | 🟢 1 | Fall back to the naive "assume it stays the same" estimate, which is a valid forecast on its own. Log which one was used. |

---

**The pattern:** bucket 1 resolves itself by doing nothing. Bucket 2 is about never losing track of what we hold. **Only bucket 3 can produce a loss larger than this plan says is possible** - which is why `recovery.py` is on the never-cut list.

## Why the one-leg case is the only true emergency

We send both contracts as one package, but the market can still fill one and not the other - one found a buyer in those seconds, the other didn't.

**Everything else in this system fails *inside* the limits we set.** A bad forecast, the wrong distance, a losing week - all of those play out within the $473-per-bet ceiling, because leg 2 is sitting there holding the floor.

The one-leg case is the only situation where **the maximum-loss number stops being true.** Without leg 2, there is no floor at all. That's the difference between a bad day and an account-ending one, and it's why `recovery.py` checks after *every* submission and why it can never be cut.

## The dead-man's switch

If the bot hasn't completed a successful cycle in **4 hours** *and* there are open positions, it fires an alert regardless of mode - including in AUTO. Silence is treated as a failure, not as "everything's fine."

## The stop button

Always visible, works in every mode, and does exactly one thing: **stop opening new positions.** It deliberately does *not* dump existing positions - panic-closing a defined-risk spread mid-drawdown realizes a loss that the structure was already capping for us. Closing everything is a separate, explicitly-labelled second button.

---

# PART 10D - What you (and the judges) will actually see, day to day

This section is the non-technical walkthrough: what does using this thing feel like, what shows up on screen, what should you expect to happen and *not* happen.

## The main screen

```
┌────────────────────────────────────────────────────────────────┐
│  SPY PREMIUM AGENT              Mode: [SEMI-AUTO ▾]  ● running │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   $100,412        +$412         2 of 4          $5,676         │
│   account       profit         bets open       at risk         │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  TODAY - Mon Aug 31, 10:00 ET                                  │
│                                                                │
│  SPY $763.40 · forecast: CALM · gate: 3% cleared (2.4 SE)      │
│                                                                │
│  ✓ SOLD  6× SPY put spread, 3% out, 8 days                     │
│    Collected $162 · Max loss $2,838                            │
│    Reviewer: "no objection - calm forecast, cushion above bar" │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  OPEN POSITIONS                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 3% spread · exp Sep 8 · +$41  ▓▓▓▓▓▓░░░░  48% to target │  │
│  │ 3% spread · exp Sep 11 · -$12 ▓▓░░░░░░░░  11% to target │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  [ ■ STOP OPENING NEW ]              [ Limits ]  [ Full log ]  │
└────────────────────────────────────────────────────────────────┘
```

Four numbers, today's decision in plain English, what's open, and a stop button. That's the whole thing.

## When it needs you (SEMI-AUTO)

```
┌────────────────────────────────────────────────────────────────┐
│  ⚠  APPROVAL NEEDED                              expires 10:15 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Proposed:  6× SPY put spread, 3% out, 8 days                  │
│  Collect:   $162        Max loss:  $2,838                      │
│                                                                │
│  Why you're being asked:                                       │
│  → Volatility forecast is CHOPPY (top tercile)                 │
│  → Cushion is 1.8 SE, below the 2.0 bar                        │
│                                                                │
│  Reviewer:                                                  │
│  "Forecast is elevated and the cushion doesn't clear our        │
│   own bar. I'd recommend skipping or halving size."            │
│                                                                │
│  [ Approve ]   [ Approve at half size ]   [ Skip today ]       │
└────────────────────────────────────────────────────────────────┘
```

Note the AI can only argue *downward* - the options offered are full, half, or none. There's no "double it" button, because the AI never gets to propose that.

## Most days, you won't touch it

Outside those approval moments, this isn't an app you click around in. It runs once a day and writes a line. What you mostly interact with is a **log** - one line per day, in plain language, saying what it decided and why.

## What one day's entry looks like

```
Mon Aug 31 - 10:00 ET
  SPY at $763.40. Recent-swing forecast: CALM.
  Checked distances 1%–6% against the evidence gate.
  3% cleared the bar (cushion: 2.4 standard errors).
  → SOLD: SPY 3% put spread, 6 contracts, 8 days to expiry.
     Collected: $162.  Max possible loss: $2,838.
  AI review: no objection. Proceeding at full size.
```

Or, on a day it refuses:

```
Wed Sep 2 - 10:00 ET
  SPY at $758.10. Recent-swing forecast: WILD (yesterday moved 2.3%).
  → SKIPPED. Kill-switch #2 (volatility spike) triggered.
  No bet placed today. Existing positions unaffected.
```

**Every day gets a line, including every day it does nothing.** A wall of "skipped" is not a malfunction - it's the system working as designed. Refusing a bad day is the point, not an embarrassment to hide.

## The dashboard (simple version - a few numbers, updated daily)

| | |
|---|---|
| Account value | starts at $100,000, moves in small steps |
| Open bets right now | e.g. "2 of 4 slots used" |
| Total money currently at risk | one number, the combined cap from Part 2B |
| Running profit so far | a running total, in dollars |
| Today's decision | the one-line log entry above |

No charts to read, no jargon on screen. If someone wants the reasoning behind a specific day, the full log entry is one click away, but the headline view is five numbers and a sentence.

## What to actually expect, honestly

- **Most days: a small trade, or nothing.** This is not a strategy that produces exciting moment-to-moment action. That's intentional - exciting usually means risky.
- **Daily profit, if any, is small** - tens to low hundreds of dollars. It will not look impressive next to a strategy that's guessing direction and got lucky. The trade-off is that ours has a known ceiling on how badly it can go wrong, and theirs doesn't.
- **A "skip" day is a good sign, not a bad one.** It means the safety checks are doing their job.
- **If SPY has a genuinely bad week,** expect to see an early close logged (the assignment rule) with a plain-language reason, and a loss that matches the pre-agreed maximum - not a surprise number.
- **The write-up and this log are the same story told twice** - one for a judge reading a page, one for anyone watching the account live.

---

# The argument for the write-up

> **⚠️ Provisional until the backtest is rebuilt.** The claims below about the premium being negative, and about the stop-loss result, come from an unreproduced research script. Confirm them against `pipeline/backtest/spread_backtest.py` before publishing this anywhere.

> We spent ten experiments proving we could not predict **which way** the S&P 500 would move, and published the negative result instead of shipping it.
>
> Then we noticed we had been asking the wrong question. An insurance seller doesn't care about direction - only about **how far**. And unlike direction, that is predictable: volatility clusters.
>
> So we pointed the same pipeline at the right target, and held the volatility premium to the same standard as everything else. It turns out the premium is **negative** at the strikes most people sell, and that adding a stop-loss to a capped-risk bet **triples** how often you actually lose.
>
> Our agent trades only the setup that survived, in capped size, and refuses otherwise. The AI can veto a bet or shrink it. It can never choose one, and never make one bigger.
