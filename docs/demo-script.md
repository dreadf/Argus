# Demo video script

Six beats, ~3:00 total, well under the hackathon's 5-minute cap
(`PROGRESS.md:106`). Structure and pacing are drawn from Devpost's own
hackathon-demo guidance, YC's canonical launch-video conventions, and
patterns that recur across a dozen professional product-demo breakdowns
(Notion, Slack, RemSense, Canva, and others) -- see the approved plan for
full sourcing. This file is the **recording script**: read the narration
close to verbatim; the second-marks are a target, not the final cut
points (see "Production notes" below).

---

## Beat 1 -- Hook (0:00-0:15)

**On screen:** Cold open, no title card, no team intro. The live account
dashboard, already loaded. The open position and the cash-up figure are
highlighted a few seconds before anything is said.

**Say:**
"This is Argus -- an autonomous agent that checks in every 15 minutes,
unattended, and decides whether to sell insurance on the S&P 500. Right
now it's holding a real position it opened on its own."

## Beat 2 -- Problem (0:15-0:35)

**On screen:** Cut away from the dashboard entirely. Plain background.
The words "Sharpe ratio: 0.56" appear, then get struck through as
"...out of how many tries?" fades in below. No UI in this beat, deliberately.

**Say:**
"Any trading bot can publish a backtest with a good Sharpe ratio -- a
single number meant to sum up return versus risk. Ours is 0.56. What a
bot usually won't publish is how many strategies it tried before landing
on the number it's showing you. That's cheap to produce and almost
impossible for a judge to check. This project checks it anyway, against
itself."

## Beat 3 -- Demo, core feature (0:35-1:50)

Real task-order sequence, matching the actual pipeline: the trade, the
guardrails, proof of the constraint, then proof of autonomy.

**Shot 3a (0:35-0:55) -- the trade.** *On screen:* the fill detail --
SPY 735/730 put credit spread, 6 contracts, expiring 2026-09-11.
*Say:* "It sells a put credit spread -- that means two option legs
traded together, so the most it can ever lose is fixed before the trade
exists. This one: six contracts, expiring September 11th, filled for a
net credit of twenty-three cents a share."

**Shot 3b (0:55-1:15) -- the safety machinery.** *On screen:* the local
admin console's Manual Controls panel (Pause/Resume, Run agent now,
Force-close), then the Picker -> Guards -> Reviewer -> Execution
pipeline. *Say:* "Before any of that happens, fifteen automated checks
run -- account risk, liquidity, a volatility filter. Only after all
fifteen pass does an AI even see the trade, and it gets exactly two
powers: shrink it, or cancel it. It cannot make a trade bigger, and it
cannot propose one of its own."

**Shot 3c (1:15-1:35) -- show it, don't just say it.** *On screen:* the
real `apply_reviewer_decision` clamp logic, on screen, with the line that
enforces "never raise size" highlighted. *Say:* "That's not a prompt
instruction the model could ignore. It's a plain function with no
network call in it -- the limit holds regardless of what the model says."

**Shot 3d (1:35-1:50) -- autonomy, briefly.** *On screen:* `crontab -l`,
both lines. *Say:* "And nobody is clicking anything to make this happen
-- this runs on a schedule, on its own, during market hours."

## Beat 4 -- The hardest technical hurdle, the peak (1:50-2:30)

**On screen:** Terminal running `python -m pipeline.falsify.audit`,
output scrolling, stopping and highlighting the final DSR line.

**Say:**
"Guards and autonomy keep the trade safe. They don't prove it's a good
trade -- so here's the part almost nobody building one of these actually
does. We built a falsification engine, aimed it at our own result, and
it caught something immediately: our simulation was crediting zero
interest on collateral while still subtracting the full risk-free rate
as the benchmark -- a bug that made us look worse than reality, not
better. We found it ourselves, and the honest number is 0.56. Then we
went further: corrected for the thirty-one things this project has
actually tried against this data, the Deflated Sharpe Ratio is 0.20 --
about a one-in-five chance the edge is real, and we won't dress that up
as more. Most trading bots never run this check, because it can only
hurt them. We'd rather know than guess."

## Beat 5 -- Close, the CTA (2:30-3:00)

**On screen:** Return to the exact opening frame from Beat 1 -- the live
position, still open, still real -- then a text overlay with the
reproduce-it commands, timed to land on the final line below.

**Say:**
"This isn't a backtest slideshow. Argus is a fully autonomous agent, running
unattended, respecting fifteen hard risk limits, logging every decision
it makes -- including every trade it refuses. And because we ran our own
numbers through a correction most teams skip, you don't have to take our
word for any of it. Clone the repo, run one command, and verify it
yourself in under twenty seconds. That's the bar an autonomous trading
agent should have to clear before anyone trusts it with real money."

---

## Things to avoid saying

- Do not call the Deflated Sharpe Ratio "proof the strategy works." It is
  not; the write-up's own words are "not proven."
- Do not claim the admin-console buttons have been "used live" unless one
  specifically has been, at recording time.
- Do not present the paper account as newly created for the hackathon;
  say what `WRITEUP.md` says: it predates the hackathon, carried zero
  orders before the contest window, and every order shown was placed
  during it.
- Do not narrate the ML direction-prediction track as part of what
  trades. It is a separate, unrelated research track that found nothing.

## Production notes

This script is produced with a Remotion project under `video/remotion/`
(local only, never committed -- see `.gitignore`), which recreates the
dashboard, admin console, and terminal beats as motion graphics driven by
real captured data, rather than screen-recording the live apps. Full
rationale and architecture are in the approved plan
(`~/.claude/plans/try-to-draft-the-graceful-adleman.md`); short version:
it gives frame-exact timing and sidesteps this machine's blocked
screen-recording permission entirely.

**Recording checklist, for this production method:**
- [ ] Re-capture all three data files fresh immediately before building
      the final cut, not reused from an earlier session:
      `video/remotion/data/dashboard_snapshot.json` (real account state),
      `video/remotion/data/audit_stdout.txt` (real
      `python -m pipeline.falsify.audit` run), `video/remotion/data/crontab_output.txt`
      (real `crontab -l`)
- [ ] Record the narration above as one continuous voiceover take
      (Phase A) -- this is the one step that has to be a human
- [ ] Run alignment on the recording (Phase B) and regenerate
      `video/remotion/src/timing.ts` from the real timestamps -- it
      currently holds PLACEHOLDER TIMING from this script's target
      second-marks, not real ones
- [ ] `./video/remotion/render.sh` to produce the final silent video, then
      mux in the real voiceover (the script prints the exact `ffmpeg`
      command)
- [ ] Watch the final render once, audio on, confirming every figure
      still matches `WRITEUP.md`'s current text (it can drift as the
      project's own numbers are revised)
