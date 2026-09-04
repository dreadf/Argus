---
marp: true
theme: argus
paginate: true
size: 16:9
html: true
header: 'ARGUS'
---

<!--
Asset sources, each downloaded and recolored to this deck's exact palette:
- assets/icons/clipboard-check.svg, shield.svg, eye.svg, send.svg, circle-dollar-sign.svg --
  Lucide (lucide.dev), MIT/ISC license
- assets/illustrations/watching-the-market.svg -- hand-authored for this deck (round 6/7): the
  Argus "watchful eye" over a rising market chart, flat two-tone fills only (accent teal + muted
  grays), no gradients, used on the two hero slides so the cover/close illustration is
  unambiguously about trading, not generic stargazing
-->

<!-- _class: tpl-hero -->

<div class="hero-text">

# Argus

<p class="subhead">An AI-assisted trading agent that sells insurance on the S&P 500, and publishes
the honest math on whether it works.</p>

<span class="badge">Live account, real trades</span>

<div class="source">Source: WRITEUP.md, opening line</div>

</div>
<div class="hero-illustration">
  <img src="assets/illustrations/watching-the-market.svg" alt="">
</div>

<!-- Speaker notes: Argus, the many-eyed guardian of Greek myth (also Odysseus's loyal dog), maps to the system's 15 backtested guards, covered later in the Evaluation section. It places real, defined-risk options trades on a live paper account, on a schedule, with no person clicking anything, and prints the corrected number even when the correction makes it worse. -->

---

<!-- _class: tpl-section -->

<p class="section-label">Section 01</p>

# The Problem

<p class="subhead">Why options income is easy to sell and hard to do safely, and why nobody checks the safety.</p>

---

<!-- _class: tpl-split -->

<p class="eyebrow">The problem</p>

<div class="split">
  <div class="split-text">
    <h1>Nobody tests the safety rails</h1>
    <p class="subhead">Selling options for income is a proven strategy. Not blowing up doing it is the part that actually fails.</p>
    <ul class="body-list">
      <li>By hand it takes discipline few people sustain: one oversized trade after a good month erases a year of income</li>
      <li>Handed to a bot, you're trusting risk rules nobody ever measured against real market history</li>
      <li>An untested safety rule is a guess wearing a safety label, and you find out when it costs you money</li>
    </ul>
  </div>
  <div class="split-visual">
    <div class="equation-box">
      <span class="eq-label">Typical bot's risk controls</span>
      <span class="eq-val strike">Trust us</span>
      <span class="eq-op">...tested against what?</span>
    </div>
  </div>
</div>

<div class="source">Source: WRITEUP.md positioning, paragraph 3</div>

---

<!-- _class: tpl-split -->

<p class="eyebrow">The opportunity</p>

<div class="split">
  <div class="split-text">
    <h1>Rails you can actually check</h1>
    <p class="subhead">The gap isn't a smarter signal. It's automation whose limits are measured, so real money behind it stops being a leap of faith.</p>
    <ul class="body-list">
      <li>The income is documented research: index options price in more volatility than actually shows up (Bakshi &amp; Kapadia 2003, Carr &amp; Wu 2009, CBOE's PUT index)</li>
      <li>What's missing is proof the safety layer holds, so Argus replays every guard against real history instead of assuming it works</li>
      <li>That turns a safety claim into a number a buyer can check, not a promise they have to take</li>
    </ul>
  </div>
  <div class="split-visual">
    <svg viewBox="0 0 320 240" style="width:100%">
      <line x1="30" y1="30" x2="30" y2="190" stroke="#2A3238" stroke-width="1"/>
      <line x1="30" y1="60" x2="300" y2="60" stroke="#1D252A" stroke-width="1"/>
      <line x1="30" y1="100" x2="300" y2="100" stroke="#1D252A" stroke-width="1"/>
      <line x1="30" y1="140" x2="300" y2="140" stroke="#1D252A" stroke-width="1"/>
      <line x1="30" y1="190" x2="300" y2="190" stroke="#2A3238" stroke-width="1"/>
      <polygon points="30,95 75,72 120,108 165,62 210,92 255,58 300,80 300,128 255,112 210,135 165,118 120,140 75,124 30,130" fill="#4FBDBA" fill-opacity="0.1"/>
      <polyline points="30,95 75,72 120,108 165,62 210,92 255,58 300,80" fill="none" stroke="#63707A" stroke-width="2"/>
      <polyline points="30,130 75,124 120,140 165,118 210,135 255,112 300,128" fill="none" stroke="#4FBDBA" stroke-width="2.5"/>
      <text x="30" y="45" fill="#8B98A0" font-family="IBM Plex Mono" font-size="11">IMPLIED VOL</text>
      <text x="30" y="160" fill="#4FBDBA" font-family="IBM Plex Mono" font-size="11">REALIZED VOL</text>
      <text x="165" y="215" fill="#63707A" font-family="IBM Plex Mono" font-size="10" text-anchor="middle">THE PREMIUM IS THE GAP BETWEEN THEM</text>
    </svg>
  </div>
</div>

<div class="source">Source: SOURCES.md, "Volatility risk premium" section (Bakshi &amp; Kapadia 2003; Carr &amp; Wu 2009; CBOE PUT index methodology)</div>

---

<!-- _class: tpl-section -->

<p class="section-label">Section 02</p>

# The Product

<p class="subhead">What Argus actually does, how it decides, and proof it's trading for real.</p>

---

<!-- _class: tpl-split -->

<p class="eyebrow">What it actually does</p>

<div class="split">
  <div class="split-text">
    <h1>Insurance on the S<span class="amp">&amp;</span>P 500</h1>
    <p class="subhead">Sold on a schedule, without a person clicking anything. Every position is a defined-risk put credit spread.</p>
    <ul class="body-list">
      <li>Sells one put and buys a cheaper, further-out put, at the same time, as a single trade</li>
      <li>That second leg fixes the most Argus can lose the moment the trade is placed</li>
      <li>Both legs always go in together, so there's no window where only one side exists</li>
    </ul>
  </div>
  <div class="split-visual">
    <div class="diagram-2box" style="flex-direction:column;gap:14px">
      <div class="box sell">
        <div class="box-label">Leg 1</div>
        <div class="box-title">Sell one put option</div>
      </div>
      <div class="box buy">
        <div class="box-label">Leg 2</div>
        <div class="box-title">Buy a cheaper put, further out</div>
      </div>
      <div class="box">
        <div class="box-label">One order</div>
        <div class="box-title">Max loss fixed before it exists</div>
      </div>
    </div>
  </div>
</div>

<div class="source">Source: README.md "What the trading system does"; WRITEUP.md positioning para 2</div>

---

<!-- _class: tpl-full -->

<p class="eyebrow">Why this beats a typical trading bot</p>

<div class="content">
  <div class="head">
    <h1>Not your typical trading bot</h1>
    <p class="subhead">Most bots let the AI trade freely, and publish one number with no way to check it. Argus does neither.</p>
  </div>
  <div class="full-visual">
    <table class="compare">
      <tr><th></th><th>Typical bot</th><th class="argus">Argus</th></tr>
      <tr>
        <td><strong>Reporting</strong></td>
        <td>Reports a backtest Sharpe, full stop</td>
        <td class="argus">Reports the same number, and what it becomes once corrected for every strategy actually tried</td>
      </tr>
      <tr>
        <td><strong>AI's power</strong></td>
        <td>Can size or place a trade on its own</td>
        <td class="argus">Can only shrink or cancel a trade a fixed rules engine already built</td>
      </tr>
      <tr>
        <td><strong>Safety guards</strong></td>
        <td>Assumed to work</td>
        <td class="argus">Backtested against real historical winning weeks</td>
      </tr>
    </table>
  </div>
</div>

<div class="source">Source: README.md "What sets this apart from a typical trading bot"; WRITEUP.md positioning</div>

<!-- Speaker notes: framed against the category of trading bots generally, never against other hackathon entries, matching this project's established positioning style. -->

---

<!-- _class: tpl-full -->

<p class="eyebrow">How it decides</p>

<div class="content">
  <div class="head">
    <h1>How Argus decides</h1>
    <p class="subhead">Fifteen checks have to pass before an AI even sees the trade, and it can only shrink or cancel, never grow it.</p>
  </div>
  <div class="full-visual">
    <div class="path">
      <div class="step">
        <div class="step-marker"><img src="assets/icons/clipboard-check.svg" alt=""></div>
        <div class="step-title">Picker</div>
        <div class="step-tag">fixed rules engine</div>
        <div class="step-body">Builds the trade proposal</div>
      </div>
      <div class="step">
        <div class="step-marker"><img src="assets/icons/shield.svg" alt=""></div>
        <div class="step-title">Guards</div>
        <div class="step-tag">15 automated checks</div>
        <div class="step-body">Account risk, liquidity, volatility</div>
      </div>
      <div class="step">
        <div class="step-marker accent"><img src="assets/icons/eye.svg" alt=""></div>
        <div class="step-title">Reviewer</div>
        <div class="step-tag">AI, shrink / veto only</div>
        <div class="step-body">No network call in the clamp that enforces it</div>
      </div>
      <div class="step">
        <div class="step-marker"><img src="assets/icons/send.svg" alt=""></div>
        <div class="step-title">Execution</div>
        <div class="step-tag">Alpaca</div>
        <div class="step-body">Multi-leg order, unattended</div>
      </div>
    </div>
  </div>
</div>

<div class="source">Source: docs/demo-script.md Beat 3b/3c; WRITEUP.md architecture section</div>

<!-- Speaker notes: the limit that stops the AI from ever increasing a trade is not an instruction the model could ignore, it's a plain function with no network call in it, so the limit holds regardless of what the model outputs. -->

---

<!-- _class: tpl-split -->

<p class="eyebrow">Execution and disclosure</p>

<div class="split">
  <div class="split-text">
    <h1>A real fill, fully disclosed</h1>
    <p class="subhead">One account proved the system fills correctly. A different account is the one judged, and we say why.</p>
    <ul class="body-list">
      <li>The fill shown here proves the multi-leg order logic works. It's not an official return: that account is disqualified from judging under Alpaca's own rules, regardless of its clean history</li>
      <li>The account actually judged, PA3HWE141FA8, carries no trading history from the scored window, because it didn't exist during it. We're stating that plainly rather than leaving it for a judge to find</li>
    </ul>
  </div>
  <div class="split-visual" style="width:100%">
    <div class="frame screenshot" style="width:100%">
      <div class="frame-bar">
        <span class="frame-dot"></span><span class="frame-dot"></span><span class="frame-dot"></span>
      </div>
      <div class="frame-body">
        <p style="font-family:var(--font-mono);font-size:0.42em;letter-spacing:0.04em;text-transform:uppercase;color:var(--muted-dim);margin:0 0 10px">PA3LRFJ9JMVX &middot; execution proof, disqualified from judging</p>
        <div class="kpi-row" style="margin-top:0">
          <div class="kpi-tile muted">
            <div class="kpi-label">Position</div>
            <div class="kpi-value">SPY 735/730</div>
            <div class="kpi-help">Put credit spread, 6 contracts</div>
          </div>
          <div class="kpi-tile muted">
            <div class="kpi-label">Filled at</div>
            <div class="kpi-value">$0.23/share</div>
            <div class="kpi-help">Net credit, cash up $137.70</div>
          </div>
        </div>
        <p style="font-family:var(--font-mono);font-size:0.42em;letter-spacing:0.04em;text-transform:uppercase;color:var(--accent);margin:14px 0 0">Judged on PA3HWE141FA8 &middot; $100,000 starting balance</p>
      </div>
    </div>
  </div>
</div>

<div class="source">Source: WRITEUP.md "Real, and then a correction we found late" section; README.md "Live dashboard" section</div>

---

<!-- _class: tpl-section -->

<p class="section-label">Section 03</p>

# The Evaluation

<p class="subhead">How we stress-test our own claims, including the ones that don't flatter us.</p>

---

<!-- _class: tpl-full -->

<p class="eyebrow">The track record</p>

<div class="content">
  <div class="head">
    <h1>A 98.9% win rate</h1>
    <p class="subhead">351 wins, 4 losses, across 355 traded weeks from 2016 to 2026. This is the real, replayed result, before any statistical correction.</p>
  </div>
  <div class="full-visual">
    <div class="big-number-row">
      <div>
        <div class="big-number">98.9%</div>
        <div class="big-number-label">Win rate, 351 of 355 traded weeks (538 total, 2016-2026)</div>
      </div>
      <div class="side-figures">
        <div class="side-figure">
          <div class="side-figure-value">2.38</div>
          <div class="side-figure-label">Profit factor: total wins are worth 2.38x total losses</div>
        </div>
        <div class="side-figure">
          <div class="side-figure-value">4</div>
          <div class="side-figure-label">Losing weeks out of 355 traded, worst week -4.70%</div>
        </div>
      </div>
    </div>
  </div>
  <p class="body-copy">The next slide asks a harder, different question: not how often trades
  worked, but whether this is a repeatable skill, or luck from picking this idea out of 31 tried.</p>
</div>

<div class="source">Source: public/data/track_record.json (stats.win_rate, n_wins, n_losses, profit_factor)</div>

---

<!-- _class: tpl-full -->

<p class="eyebrow">Tested, not just claimed</p>

<div class="content">
  <div class="head">
    <h1>We benchmark our own results</h1>
    <p class="subhead">The 98.9% win rate is real. This asks a different question: is it a repeatable skill, or did we get lucky picking this idea out of 31 tried?</p>
  </div>
  <div class="full-visual">
    <div class="kpi-row">
      <div class="kpi-tile stat">
        <div class="kpi-label">Deflated Sharpe Ratio</div>
        <div class="kpi-value">0.20</div>
        <div class="kpi-help">At N = 31 ideas tried. Not proven yet.</div>
      </div>
      <div class="kpi-tile stat muted">
        <div class="kpi-label">Raw Sharpe, uncorrected</div>
        <div class="kpi-value">+0.574</div>
        <div class="kpi-help">Before the multiple-testing correction</div>
      </div>
    </div>
  </div>
  <p class="body-copy">That correction once caught a real mistake in our own simulation, and forced
  a lower, honest number instead of a flattering one.</p>
</div>

<div class="source">Source: WRITEUP.md performance table; EXPERIMENT_29_SHARPE_AUDIT.md. Reproduce it yourself: python -m pipeline.falsify.audit, no login, under twenty seconds.</div>

<!-- Speaker notes: 0.20 is not a failing grade, it's an honest one, it says the edge hasn't cleared the bar for statistical proof yet and states exactly how far short it falls. -->

---

<!-- _class: tpl-split -->

<p class="eyebrow">Safety checks are tested too</p>

<div class="split">
  <div class="split-text">
    <h1>A guard blocked too much</h1>
    <p class="subhead">One of Argus's own guards was quietly blocking 42-50% of good trades, until it was measured and corrected.</p>
    <ul class="body-list">
      <li>A guard nobody checks against the trades it blocks is a guess wearing a safety label</li>
      <li>Each of the fifteen guards is replayed against real historical winning weeks to measure exactly that</li>
    </ul>
  </div>
  <div class="split-visual" style="flex-direction:column;gap:12px;align-items:stretch">
    <div class="equation-box">
      <span class="eq-label">Before</span>
      <span class="eq-val strike">42-50%</span>
      <span class="eq-op">of winning trades blocked</span>
      <span class="eq-verdict bad">Too tight</span>
    </div>
    <div class="equation-box">
      <span class="eq-label">After</span>
      <span class="eq-val">0-1.6%</span>
      <span class="eq-op">of winning trades blocked</span>
      <span class="eq-verdict good">Measured, not assumed</span>
    </div>
  </div>
</div>

<div class="source">Source: PROGRESS.md, false-trip test entry</div>

---

<!-- _class: tpl-full -->

<p class="eyebrow">Why this matters beyond one trade</p>

<div class="content">
  <div class="head">
    <h1>A reusable honesty engine</h1>
    <p class="subhead">Not built for one strategy. Any trading idea can be run through the same gauntlet that caught Argus's own bug.</p>
  </div>
  <div class="full-visual">
    <div class="flow">
      <div class="flow-box">Any trading idea</div>
      <div class="flow-arrow">&rarr;</div>
      <div class="flow-box accent"><img src="assets/icons/eye.svg" alt="">The honesty check</div>
      <div class="flow-arrow">&rarr;</div>
      <div class="flow-box">Pass / fail, with the reason why</div>
    </div>
  </div>
  <ul class="body-list">
    <li><code>pipeline/falsify/engine.py</code> runs any trading hypothesis through the same gauntlet, and reports exactly which stage killed it, if any did</li>
    <li>A team building a completely different strategy can point this engine at their own result and get the same honest accounting</li>
  </ul>
</div>

<div class="source">Source: WRITEUP.md positioning and architecture; EXPERIMENT.md synthesis</div>

---

<!-- _class: tpl-split -->

<p class="eyebrow">What's next</p>

<div class="split">
  <div class="split-text">
    <h1>Two markets, checked first</h1>
    <p class="subhead">Before either got real money. One cleared the bar. One didn't, so it isn't being traded.</p>
    <p class="body-copy">The same cheap, honest gate ran before either got real money, and IWM's
    margin was real enough to keep it on paper.</p>
  </div>
  <div class="split-visual">
    <div class="ticker-composition">
      <div class="money-badge"><img src="assets/icons/circle-dollar-sign.svg" alt=""></div>
      <div class="ticker-stack">
        <div class="ticker-chip good">
          <div>
            <div class="ticker-symbol">QQQ</div>
            <div class="ticker-status">Cleared</div>
          </div>
        </div>
        <div class="ticker-chip">
          <div>
            <div class="ticker-symbol">IWM</div>
            <div class="ticker-status">Not yet</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="source">Source: pipeline/backtest/qqq_iwm_viability.py</div>

---

<!-- _class: tpl-full -->

<p class="eyebrow">In summary</p>

<div class="content">
  <div class="head">
    <h1>Honest about what's proven</h1>
    <p class="subhead">Three things this deck showed, and how to check every one of them yourself.</p>
  </div>
  <div class="full-visual">
    <div class="kpi-row">
      <div class="kpi-tile">
        <div class="kpi-label">The Problem</div>
        <div class="recap-text">Options income works. What fails is the risk discipline, manual or automated, that nobody ever tested.</div>
      </div>
      <div class="kpi-tile good">
        <div class="kpi-label">The Product</div>
        <div class="recap-text">Real trades, fixed rules, and an AI that can only shrink or veto a position, never grow one.</div>
      </div>
      <div class="kpi-tile muted">
        <div class="kpi-label">The Evaluation</div>
        <div class="recap-text">A 98.9% win rate, checked by a self-audit that also caught and fixed our own math before we published it.</div>
      </div>
    </div>
  </div>
  <div class="close-links">
  Repo &middot; WRITEUP.md &middot; Live dashboard &middot; Reproduce it: python -m pipeline.falsify.audit
  </div>
</div>

---

<!-- _class: tpl-hero -->

<div class="hero-text">

# Argus

<p class="subhead">An AI-assisted trading agent that sells insurance on the S&P 500.</p>

<div class="close-links">
Repo &middot; WRITEUP.md &middot; Live dashboard
</div>

</div>
<div class="hero-illustration">
  <img src="assets/illustrations/watching-the-market.svg" alt="">
</div>
