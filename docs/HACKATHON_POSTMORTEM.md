# Postmortem: why this submission did not place

Alpaca AI Trading Agents Hackathon, judged 2026-09-04. This project did not
win. 1st place was team RazorsEdge's "Autobelay" (SPY options, deterministic
gate architecture). 2nd place was "Should-AI Buy?" (multi-agent council,
TypeScript risk gate). Full comparison was done 2026-10-03 against the
Autobelay deck and the Should-AI Buy public repo.

This is not a record of what was technically wrong. The safety architecture
here (rules engine executes, LLM can only shrink or veto a proposal) was at
least as sound as both winners'. The gap was almost entirely in what got
made visible to a judge in the few minutes they actually spend per
submission, and in how much of the scored window had real P&L behind it.

## What the winners did that this submission did not

**A live, moving number in the scored window.** Autobelay's judged account
went $100,000 to $105,668 (+5.7%) over the four days of judging, shown as a
simple chart. Should-AI Buy gave judges a live web terminal with one-click
login. Both let a judge verify "did this make money this week" in under a
minute with no reading required.

**Bugs disclosed by number, not just by category.** Autobelay names its own
incidents (#174, #170, #171, #173) as proof the system is actually watched.
Naming the bug ID is what makes the disclosure read as evidence rather than
boilerplate humility.

**A second, independent check that is visibly checked.** Autobelay grades
every number the model states against the journal (tags like
`unsupported`, `misattributed`, `fabricated_urgency`) and scores a
prediction-market second opinion with a Brier score, reported in the deck
with a concrete score (0.004 vs 0.25 for a coin flip). Should-AI Buy runs
an adversarial red-team agent whose verdicts are visible in the pipeline
diagram. Both make the "we checked ourselves" claim legible in one slide.
This submission's self-checking work (DSR, MPPM, randomization nulls,
false-trip testing on risk guards) is methodologically deeper but reads as
prose a judge has to trust, not a number they can glance at.

**Infrastructure that visibly runs itself.** Autobelay: self-hosted
hardware, 795 tests, CI/CD with a freeze window around trading code, a
live journal viewer, Home Assistant dashboard, A/B test across three real
accounts before promoting a config change. Should-AI Buy: 891 tests across
52 suites, a 9-stage pipeline with a public live terminal. Both demonstrate
operational maturity a judge can see without reading code.

## What to do differently next time

1. **Get the judged account trading before judging starts, not during it.**
   The judged account here was created on 2026-09-03, one day before
   judging closed, and carried no meaningful history in the scored window.
   Create the dedicated account on day one of the hackathon and let it
   accumulate real fills for the full window, even if early trades are
   small or defensive.

2. **Lead with the live number, not the audit.** The DSR/MPPM rigor is
   real value and should stay, but it belongs after a simple "here is what
   the judged account actually did this week" chart, not before it. A
   judge who never gets past paragraph one should still see a number that
   moved.

3. **Make the live dashboard the first thing a judge sees, not an
   afterthought link.** Put the dashboard URL and a screenshot of it in
   the first screen of both the README and the deck. If it is read-only
   by design, say so in one line and move on, do not let the safety
   rationale crowd out the demo.

4. **Name incidents, not just categories.** When the system catches its
   own bug (the Sharpe sign error, the volatility-reconstruction
   calibration bug), give it a tracked ID and reference the ID in the
   writeup, the same way a changelog or issue tracker would. "We fixed
   bug #N, filed on date X" is more credible than "we found and fixed an
   issue."

5. **Build one glanceable self-check visualization.** A single chart or
   number a judge can register in two seconds: a Brier score against a
   coin-flip baseline, a pass/fail count on a false-trip test, something
   with the same immediacy as Autobelay's Brier-score bar. The underlying
   stats work already exists here; it needs one chart that does not
   require reading methodology to trust.

6. **Show infrastructure maturity visually, not just in prose.** A simple
   pipeline or cycle diagram (cron to gates to model to order to journal)
   does more in one slide than several paragraphs describing the same
   flow. Autobelay's "one cycle, every 10 minutes" diagram is the clearest
   example of this.

7. **Clean the repo of anything a judge could stumble on by accident.**
   `Black Brown and White Gradient Modern Business Pitch Deck
   Presentation.pdf` is a generic, unfilled Canva template (lorem ipsum,
   stock photography, placeholder company name) left at the repo root. It
   is not the submitted deck, but a judge browsing the repo has no way to
   know that without opening it. Delete anything that is not the final
   artifact before submission, or move scratch material somewhere clearly
   marked as such (an `archive/` or `scratch/` folder, already used
   elsewhere in this repo, is the right place).

8. **Decide early whether the demo is multi-agent or single-strategy, and
   lean into whichever one it is.** Both winners built multi-agent or
   multi-account systems (three live accounts, a six-agent council) that
   are inherently more demo-friendly than a single strategy reviewed by
   one model, because there is more to show moving at once. If staying
   single-strategy, the self-checking rigor needs to carry the full weight
   of the "creative/original" judging criterion on its own, which means it
   needs the glanceable treatment in point 5, not just written depth.

## What not to change

The core safety property (deterministic code places every order, the model
can only shrink or veto, nothing it outputs is reachable as an order
parameter) is correct and should not be loosened for the sake of a flashier
demo. Autobelay and Should-AI Buy both kept this same property. The fix is
presentation and timing, not loosening the gate.
