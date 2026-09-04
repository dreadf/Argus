"use strict";

// ---------------------------------------------------------------------------
// Formatting helpers -- Intl.* throughout rather than hand-rolled string
// formatting (web-interface-guidelines: use Intl.NumberFormat/DateTimeFormat,
// not hardcoded formats).
// ---------------------------------------------------------------------------
const fmtMoney = (v, opts = {}) =>
  v === null || v === undefined ? "N/A" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0, ...opts }).format(v);
const fmtMoney2 = (v) => (v === null || v === undefined ? "N/A" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v));
const fmtPct = (v, digits = 1) => (v === null || v === undefined ? "N/A" : new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v));
// Signed variant -- only for genuine deltas (a day-over-day move, a margin
// that can be positive or negative), never for a level/rate like VIX9D or a
// win rate, which read as nonsensical with a "+" in front.
const fmtPctSigned = (v, digits = 1) => (v === null || v === undefined ? "N/A" : new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits, signDisplay: "exceptZero" }).format(v));
const fmtNum = (v, digits = 2) => (v === null || v === undefined ? "N/A" : new Intl.NumberFormat("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(v));

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) node.appendChild(child);
  return node;
}

function metric(label, value, help, cls) {
  const wrap = el("div", { class: `metric-tile${cls ? " " + cls : ""}` });
  wrap.appendChild(el("div", { class: "metric-label", text: label }));
  wrap.appendChild(el("div", { class: `metric-value${cls ? " " + cls : ""}`, text: value }));
  if (help) wrap.appendChild(el("div", { class: "metric-help", text: help }));
  return wrap;
}

function kpiTile(label, value, cls) {
  const wrap = el("div", { class: `kpi-tile${cls ? " " + cls : ""}` });
  wrap.appendChild(el("div", { class: "kpi-label", text: label }));
  wrap.appendChild(el("div", { class: `kpi-value${cls ? " " + cls : ""}`, text: value }));
  return wrap;
}

// ---------------------------------------------------------------------------
// Tabs -- real <button>s with URL hash routing, so the active section is
// linkable/bookmarkable (web-interface-guidelines: URL reflects tab state).
// ---------------------------------------------------------------------------
// Chart.js measures its canvas's parent width at construction time. All
// charts are built once at page load (renderEquityChart runs immediately,
// regardless of which tab is visible), so any chart built while its tab
// panel is `hidden` (display:none) gets a zero-width measurement and stays
// broken even after the tab becomes visible -- there's no resize event to
// tell it otherwise. Fix: keep every Chart instance here and call
// .resize() whenever a tab is activated, which is what actually re-measures
// the now-visible container. Cheap no-op for charts that were already sized
// correctly.
window.dashboardCharts = [];

function initTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  const panels = document.querySelectorAll(".tab-panel");

  function activate(name) {
    let matched = false;
    tabs.forEach((t) => {
      const isMatch = t.dataset.tab === name;
      if (isMatch) matched = true;
      t.toggleAttribute("aria-current", isMatch);
      if (isMatch) t.setAttribute("aria-current", "page");
      else t.removeAttribute("aria-current");
    });
    if (!matched) tabs[0].setAttribute("aria-current", "page");
    const activeName = matched ? name : tabs[0].dataset.tab;
    panels.forEach((p) => {
      p.hidden = p.id !== `tab-${activeName}`;
    });
    window.dashboardCharts.forEach((c) => c.resize());
  }

  tabs.forEach((t) => {
    t.addEventListener("click", () => {
      window.location.hash = t.dataset.tab;
      activate(t.dataset.tab);
    });
  });
  window.addEventListener("hashchange", () => activate(window.location.hash.slice(1)));
  activate(window.location.hash.slice(1) || "overview");
}

// ---------------------------------------------------------------------------
// "Today, in plain terms" -- a short, colored label + plain-English detail
// per line, meant to be read top-to-bottom as the answer to "what's going
// on", with the metric cards below as supporting detail for anyone who
// wants to check the underlying numbers themselves.
// ---------------------------------------------------------------------------
function renderNarrative(overview) {
  const box = document.getElementById("narrative");
  box.innerHTML = "";
  (overview.narrative || []).forEach((line) => {
    const row = el("div", { class: "narrative-line" });
    row.appendChild(el("span", { class: `narrative-label ${line.cls}`, text: line.label }));
    row.appendChild(el("span", { class: "narrative-detail", text: line.detail }));
    box.appendChild(row);
  });
  if (overview.status && overview.status.timestamp) {
    box.appendChild(el("p", { class: "card-note", text: `Last decision logged: ${overview.status.timestamp}` }));
  }
}

// ---------------------------------------------------------------------------
// Overview tab
// ---------------------------------------------------------------------------
function renderAccount(account) {
  const box = document.getElementById("account-metrics");
  box.innerHTML = "";
  if (!account || account.available === false) {
    box.appendChild(el("p", { class: "card-note", text: `Live account data unavailable right now (${account ? account.reason : "no response"}).` }));
    return;
  }
  const unrealized = account.positions.reduce((sum, p) => sum + (p.unrealized_pl || 0), 0);
  box.appendChild(el("div", { class: "kpi-row" }, [kpiTile("Equity", fmtMoney(account.equity), "accent")]));
  const rowItems = [
    metric("Cash", fmtMoney(account.cash)),
    metric("Options buying power", fmtMoney(account.options_buying_power)),
    metric("Open positions", String(account.positions.length)),
  ];
  if (account.positions.length > 0) {
    rowItems.push(metric("Unrealized P&L", fmtMoney2(unrealized), null, unrealized >= 0 ? "good" : "bad"));
  }
  box.appendChild(el("div", { class: "metric-row" }, rowItems));
}

function renderMarket(overview) {
  const box = document.getElementById("market-metrics");
  const note = document.getElementById("market-note");
  box.innerHTML = "";
  note.textContent = "";
  if (overview.market_error || !overview.market) {
    box.appendChild(el("p", { class: "card-note", text: `Live market data unavailable right now (${overview.market_error || "no data"}).` }));
    return;
  }
  const m = overview.market;
  const moveBlocks = Math.abs(m.yesterday_move_pct) > 0.02;
  const contangoBlocks = m.contango_threshold !== null && m.contango < m.contango_threshold;
  box.appendChild(el("div", { class: "metric-row" }, [
    metric("SPY spot", fmtMoney2(m.spot)),
    metric("Yesterday's move", fmtPctSigned(m.yesterday_move_pct), "Blocks a new trade above 2%.", moveBlocks ? "bad" : null),
    metric("Contango (VIX3M/VIX9D)", fmtNum(m.contango, 3), "Flattening below its own 33rd percentile.", contangoBlocks ? "bad" : null),
  ]));

  const blocks = [];
  if (moveBlocks) blocks.push(`SPY moved ${fmtPctSigned(m.yesterday_move_pct)} yesterday (blocks above 2%)`);
  if (contangoBlocks) blocks.push(`term structure is flattening (${fmtNum(m.contango, 3)} < ${fmtNum(m.contango_threshold, 3)})`);
  note.className = `card-note ${blocks.length ? "bad" : "good"}`;
  note.textContent = blocks.length ? `Would block a new trade today: ${blocks.join("; ")}.` : "Nothing here would block a new trade today.";
}

// Shows the calculation as one connected line (value / value = ratio ->
// verdict) instead of three same-looking boxes the reader has to mentally
// connect themselves.
function renderVolatility(overview) {
  const box = document.getElementById("volatility-equation");
  const verdict = document.getElementById("volatility-verdict");
  box.innerHTML = "";
  verdict.innerHTML = "";
  if (overview.market_error || !overview.volatility) {
    box.appendChild(el("p", { class: "card-note", text: "Not enough data to compute today." }));
    return;
  }
  const v = overview.volatility;
  const eq = el("div", { class: `equation equation-box ${v.verdict_class}` });
  const item = (label, val) => {
    const wrap = el("span", { class: "eq-item" });
    wrap.appendChild(el("span", { class: "eq-label", text: label }));
    wrap.appendChild(el("span", { class: "eq-val", text: val }));
    return wrap;
  };
  eq.appendChild(item("VIX9D", fmtPct(v.vix9d_decimal, 1)));
  eq.appendChild(el("span", { class: "eq-op", text: "÷" }));
  eq.appendChild(item("realized (10d)", fmtPct(v.rv10d, 1)));
  eq.appendChild(el("span", { class: "eq-op", text: "=" }));
  eq.appendChild(item("ratio", fmtNum(v.ratio, 2)));
  eq.appendChild(el("span", { class: "eq-op", text: "→" }));
  eq.appendChild(el("span", { class: `eq-verdict ${v.verdict_class}`, text: v.verdict_text.split(":", 1)[0] }));
  box.appendChild(eq);

  let thresholdText;
  if (v.verdict_class === "good") thresholdText = `above the ${fmtNum(v.rich_threshold, 2)} "rich" line`;
  else if (v.verdict_class === "bad") thresholdText = `below the ${fmtNum(v.thin_threshold, 2)} "thin" line`;
  else thresholdText = `between the ${fmtNum(v.thin_threshold, 2)}-${fmtNum(v.rich_threshold, 2)} "fair" band`;
  verdict.className = `card-note ${v.verdict_class}`;
  verdict.textContent = `${v.verdict_text}: the ratio is ${thresholdText}.`;
}

// Research-track volatility forecast (HAR-X). Rendered only when
// data/vol_forecast.json is present -- the card stays hidden otherwise, so a
// missing or stale export degrades to "not shown" rather than an error.
function renderVolForecast(vf) {
  if (!vf) return;
  const card = document.getElementById("section-vol-forecast");
  const box = document.getElementById("vol-forecast-metrics");
  const note = document.getElementById("vol-forecast-note");
  if (!card || !box) return;
  box.innerHTML = "";
  box.appendChild(el("div", { class: "metric-row" }, [
    metric("Forecast vol (annualized)", `${fmtNum(vf.forecast_vol_annualized_pct, 2)}%`),
    metric(`Breach prob. (${fmtNum(vf.breach_distance_pct, 0)}% / weekly)`, fmtPct(vf.breach_prob, 2)),
  ]));
  if (note) note.textContent = vf.note ? `${vf.note} (data through ${vf.data_through}).` : `Data through ${vf.data_through}.`;
  card.hidden = false;
}

function renderDecisionPath(overview) {
  const box = document.getElementById("decision-path");
  box.innerHTML = "";
  overview.decision_path.forEach((row) => {
    const r = el("div", { class: `path-row ${row.cls}` });
    r.appendChild(el("span", { class: "path-stage", text: row.stage }));
    r.appendChild(el("span", { class: `path-word ${row.cls}`, text: row.cls === "neutral" ? "N/A" : row.cls.toUpperCase() }));
    r.appendChild(el("span", { class: "path-detail", text: row.detail }));
    box.appendChild(r);
  });
}

function renderPositions(overview, account) {
  const card = document.getElementById("card-positions");
  const table = document.getElementById("positions-table");
  const positions = overview.open_positions || [];
  if (positions.length === 0) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  card.className = `card card-half ${positions.some((p) => p.room_pct !== null && p.room_pct < 0.02) ? "bad-top" : "accent-top"}`;
  const liveBySymbol = {};
  if (account && account.positions) account.positions.forEach((p) => (liveBySymbol[p.symbol] = p));

  table.querySelector("thead").innerHTML =
    "<tr><th>Underlying</th><th>Strikes</th><th>Room</th><th>Expires</th><th>Qty</th><th>Collected</th><th>Max loss</th><th>Unrealized</th></tr>";
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  positions.forEach((p) => {
    let unrealized = 0;
    [p.short_symbol, p.long_symbol].forEach((sym) => {
      const live = liveBySymbol[sym];
      if (live && live.unrealized_pl !== null) unrealized += live.unrealized_pl;
    });
    const atRisk = p.room_pct !== null && p.room_pct < 0.02;
    const tr = el("tr", { class: atRisk ? "risk-bad" : "risk-ok" });
    tr.appendChild(el("td", { text: p.underlying }));
    tr.appendChild(el("td", { text: p.strikes }));
    const roomCell = el("td", { class: "num" });
    if (p.room_pct !== null) {
      const barCap = 0.15;
      const fillPct = Math.max(0, Math.min(100, (Math.abs(p.room_pct) / barCap) * 100));
      const wrap = el("span", { class: "room-cell" });
      const bar = el("span", { class: "mini-bar" });
      bar.appendChild(el("span", { class: `mini-bar-fill${atRisk ? " bad" : ""}`, style: `width:${fillPct}%` }));
      wrap.appendChild(bar);
      wrap.appendChild(document.createTextNode(fmtPctSigned(p.room_pct)));
      roomCell.appendChild(wrap);
    } else {
      roomCell.textContent = "N/A";
    }
    tr.appendChild(roomCell);
    tr.appendChild(el("td", { class: "num", text: p.expires_days !== null ? `${p.expires_days}d` : "N/A" }));
    tr.appendChild(el("td", { class: "num", text: String(p.qty) }));
    tr.appendChild(el("td", { class: "num", text: fmtMoney2(p.collected) }));
    tr.appendChild(el("td", { class: "num", text: fmtMoney(p.max_loss) }));
    tr.appendChild(el("td", { class: `num ${unrealized >= 0 ? "good" : "bad"}`, text: fmtMoney2(unrealized) }));
    tbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------------
// Track record tab
// ---------------------------------------------------------------------------
function renderEquityChart(tr) {
  if (!tr.equity_curve) return;
  const c = tr.equity_curve;
  window.dashboardCharts.push(new Chart(document.getElementById("equity-chart"), {
    type: "line",
    data: {
      labels: c.dates,
      datasets: [
        { label: "Trade every week", data: c.cum_pnl_unfiltered, borderColor: "#E2726E", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
        { label: "VIX filter", data: c.cum_pnl_filtered, borderColor: "#5FBF95", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: chartOptions("$ per contract"),
  }));

  window.dashboardCharts.push(new Chart(document.getElementById("reference-chart"), {
    type: "line",
    data: {
      labels: c.dates,
      datasets: [
        { label: "SPY (indexed)", data: c.spy_indexed, borderColor: "#8B98A0", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
        { label: "Cash @ 3%/yr (indexed)", data: c.cash_indexed, borderColor: "#45505A", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: chartOptions("Indexed to 100"),
  }));

  if (tr.equity_headline) document.getElementById("equity-headline").textContent = tr.equity_headline;
}

function chartOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 400 },
    interaction: { mode: "index", intersect: false },
    scales: {
      x: { ticks: { color: "#8B98A0", maxTicksLimit: 8 }, grid: { color: "#232B31" } },
      y: { title: { display: true, text: yLabel, color: "#8B98A0" }, ticks: { color: "#8B98A0" }, grid: { color: "#232B31" } },
    },
    plugins: { legend: { labels: { color: "#C5CFD4", font: { family: "IBM Plex Sans" } } } },
  };
}

function renderTrackRecordStats(tr) {
  const box = document.getElementById("track-record-metrics");
  const tradeBox = document.getElementById("trade-stats");
  const benchmarkNote = document.getElementById("benchmark-note");
  box.innerHTML = "";
  if (tradeBox) tradeBox.innerHTML = "";
  if (!tr.stats) return;
  const s = tr.stats;
  box.appendChild(metric("Max drawdown, $/contract", fmtNum(s.dd_filtered), `${fmtNum(s.dd_filtered - s.dd_unfiltered)} vs. unfiltered`));
  box.appendChild(metric("Worst year, filtered", `${s.worst_year_filtered.pnl >= 0 ? "+" : ""}${fmtNum(s.worst_year_filtered.pnl)}`, `Year ${s.worst_year_filtered.year}. Unfiltered: ${fmtNum(s.worst_year_unfiltered.pnl)} in ${s.worst_year_unfiltered.year}.`));
  box.appendChild(metric("Weeks traded", `${s.weeks_traded} of ${s.weeks_total}`));

  if (tradeBox) {
    tradeBox.appendChild(metric("Win rate", fmtPct(s.win_rate, 1), `${s.n_wins} wins, ${s.n_losses} losses`, s.win_rate >= 0.5 ? "good" : "bad"));
    tradeBox.appendChild(metric("Profit factor", fmtNum(s.profit_factor, 2), "Gross wins ÷ gross losses", s.profit_factor >= 1 ? "good" : "bad"));
    tradeBox.appendChild(metric("Avg win / avg loss", `${fmtMoney2(s.avg_win)} / ${fmtMoney2(s.avg_loss)}`, "Per traded week, $/contract"));
    tradeBox.appendChild(metric("Best / worst week", `${fmtMoney2(s.best_week)} / ${fmtMoney2(s.worst_week)}`, "Single-week extremes, $/contract"));
  }

  if (benchmarkNote) {
    benchmarkNote.textContent = `SPY buy-and-hold returned ${fmtPctSigned(s.spy_final_pct, 0)} over ${s.date_range} (full market exposure); `
      + `cash at 3%/yr returned ${fmtPctSigned(s.cash_final_pct, 0)}. Neither carries the same risk as a defined-loss options `
      + `spread, so these are context, not a head-to-head with the $${fmtNum(s.final_filtered, 2)}/contract chart above.`;
  }
}

function renderValidation(tr) {
  const headline = document.getElementById("validation-headline");
  const table = document.getElementById("validation-table");
  headline.innerHTML = "";
  if (!tr.validation) {
    headline.appendChild(el("p", { class: "card-note", text: "Validation not computed." }));
    return;
  }
  const v = tr.validation;
  const allInside = v.quartiles.every((q) => q.ratio >= v.band[0] && q.ratio <= v.band[1]);
  headline.appendChild(metric("Correlation (real vs. modelled credit)", fmtNum(v.correlation, 3)));
  headline.appendChild(metric("Quartiles inside band", `${v.quartiles.length} of ${v.quartiles.length}`, `Band: ${v.band[0]}-${v.band[1]}`, allInside ? "good" : "bad"));
  document.getElementById("card-validation").className = `card card-half ${allInside ? "good-top" : "bad-top"}`;

  table.querySelector("thead").innerHTML = "<tr><th>Quartile</th><th>Weeks</th><th>Mean VIX9D</th><th>Real credit</th><th>Model credit</th><th>Model/real</th></tr>";
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  v.quartiles.forEach((q) => {
    const tr2 = el("tr");
    tr2.appendChild(el("td", { text: q.bucket }));
    tr2.appendChild(el("td", { class: "num", text: String(q.n) }));
    tr2.appendChild(el("td", { class: "num", text: fmtPct(q.vix9d_mean, 1) }));
    tr2.appendChild(el("td", { class: "num", text: fmtMoney2(q.real_credit) }));
    tr2.appendChild(el("td", { class: "num", text: fmtMoney2(q.model_credit) }));
    tr2.appendChild(el("td", { class: `num ${q.ratio >= v.band[0] && q.ratio <= v.band[1] ? "good" : "bad"}`, text: fmtNum(q.ratio, 3) }));
    tbody.appendChild(tr2);
  });
}

function renderFalseTrip(tr) {
  const headline = document.getElementById("false-trip-headline");
  const table = document.getElementById("false-trip-table");
  headline.innerHTML = "";
  if (!tr.false_trip) {
    headline.appendChild(el("p", { class: "card-note", text: "False-trip test not computed." }));
    return;
  }
  const ft = tr.false_trip;
  const ftGood = ft.blocked_pct <= ft.bar;
  headline.appendChild(metric("Blocked (aggregate)", fmtPct(ft.blocked_pct, 1), `Bar: ≤${fmtPct(ft.bar, 0)}`, ftGood ? "good" : "bad"));
  headline.appendChild(metric("Real winning weeks tested", String(ft.n_winners)));
  document.getElementById("card-false-trip").className = `card card-half ${ftGood ? "good-top" : "bad-top"}`;

  table.querySelector("thead").innerHTML = "<tr><th>Regime</th><th>Weeks</th><th>Blocked</th><th>Blocked %</th></tr>";
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  ft.by_regime.forEach((r) => {
    const row = el("tr");
    row.appendChild(el("td", { text: r.regime }));
    row.appendChild(el("td", { class: "num", text: String(r.n) }));
    row.appendChild(el("td", { class: "num", text: String(r.blocked) }));
    row.appendChild(el("td", { class: "num", text: fmtPct(r.blocked_pct, 1) }));
    tbody.appendChild(row);
  });
}

function renderEvidence(ev) {
  const pick = document.getElementById("evidence-pick");
  const summary = document.getElementById("evidence-summary");
  const table = document.getElementById("evidence-table");
  pick.innerHTML = "";
  if (!ev.current_pick) {
    pick.appendChild(el("p", { class: "card-note bad", text: "No (distance, width) combination currently clears the 2-SE evidence bar. The system declines to trade, on purpose." }));
  } else {
    const p = ev.current_pick;
    const row = el("div", { class: "metric-row" });
    row.appendChild(metric("Distance", fmtPct(p.distance, 0), "How far OTM the short strike sits", "accent"));
    row.appendChild(metric("Width", `$${p.width.toFixed(0)}`, "Spread between short and long strike", "accent"));
    row.appendChild(metric("Cushion", `${fmtNum(p.cushion_se, 2)} SE`, "Standard errors above the 2-SE bar", "good"));
    row.appendChild(metric("Qualifying shapes", `${p.n_survivors} of ${p.n_total}`, "Combinations clearing the bar today"));
    pick.appendChild(row);
  }
  summary.textContent = `See all ${ev.rows.length} combinations tested`;

  table.querySelector("thead").innerHTML = "<tr><th>Distance</th><th>Width</th><th>Weeks</th><th>Win rate</th><th>Breakeven</th><th>Cushion (SE)</th><th>Mean P&amp;L</th><th>Clears 2 SE</th></tr>";
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  ev.rows.forEach((r) => {
    const row = el("tr");
    row.appendChild(el("td", { text: fmtPct(r.distance, 0) }));
    row.appendChild(el("td", { text: `$${r.width.toFixed(0)}` }));
    row.appendChild(el("td", { class: "num", text: String(r.n) }));
    row.appendChild(el("td", { class: "num", text: fmtPct(r.win_rate, 1) }));
    row.appendChild(el("td", { class: "num", text: fmtPct(r.required_win_rate, 1) }));
    row.appendChild(el("td", { class: "num", text: fmtNum(r.cushion_se, 2) }));
    row.appendChild(el("td", { class: "num", text: fmtMoney2(r.mean_net_pnl) }));
    row.appendChild(el("td", { class: r.passes_gate ? "good" : "", text: r.passes_gate ? "Yes" : "No" }));
    tbody.appendChild(row);
  });
}

// ---------------------------------------------------------------------------
// Decision log tab
// ---------------------------------------------------------------------------
function renderDecisions(decisions) {
  const summaryBox = document.getElementById("decisions-summary");
  summaryBox.innerHTML = "";
  const s = decisions.summary;
  summaryBox.appendChild(metric("Total", String(s.total)));
  summaryBox.appendChild(metric("Traded", String(s.traded)));
  summaryBox.appendChild(metric("Guard-blocked", String(s.guard_blocked)));
  summaryBox.appendChild(metric("Reviewer-vetoed", String(s.reviewer_vetoed)));
  summaryBox.appendChild(metric("Dry run", String(s.dry_run)));

  const filterBox = document.getElementById("decision-filters");
  filterBox.innerHTML = "";
  const categories = ["All", "Traded", "Guard-blocked", "Reviewer-vetoed", "Dry run"];
  let active = "All";
  const PAGE_SIZE = 15;
  let page = 1;

  function renderTable() {
    const table = document.getElementById("decisions-table");
    table.querySelector("thead").innerHTML = "<tr><th>Timestamp</th><th>Account</th><th>Mode</th><th>Outcome</th><th>Reason</th></tr>";
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";
    const rows = active === "All" ? decisions.rows : decisions.rows.filter((r) => r.category === active);
    const pager = document.getElementById("decisions-pager");
    pager.innerHTML = "";

    if (rows.length === 0) {
      tbody.appendChild(el("tr", {}, el("td", { colspan: "5", text: "No decisions in this category." })));
      return;
    }

    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    page = Math.min(Math.max(1, page), totalPages);
    const start = (page - 1) * PAGE_SIZE;
    const pageRows = rows.slice(start, start + PAGE_SIZE);

    pageRows.forEach((r) => {
      const tr = el("tr");
      tr.appendChild(el("td", { text: r.timestamp_display || r.timestamp || "" }));
      tr.appendChild(el("td", { text: r.account_display || r.account_number || "unknown" }));
      tr.appendChild(el("td", { text: r.mode || "" }));
      tr.appendChild(el("td", { text: r.outcome || "" }));
      tr.appendChild(el("td", { class: "wrap", text: r.reason || "" }));
      tbody.appendChild(tr);
    });

    const prevBtn = el("button", { class: "chip", type: "button", text: "< Prev" });
    prevBtn.disabled = page <= 1;
    prevBtn.addEventListener("click", () => { page -= 1; renderTable(); });

    const nextBtn = el("button", { class: "chip", type: "button", text: "Next >" });
    nextBtn.disabled = page >= totalPages;
    nextBtn.addEventListener("click", () => { page += 1; renderTable(); });

    pager.appendChild(prevBtn);
    pager.appendChild(el("span", { class: "pager-label", text: `Page ${page} of ${totalPages} (${rows.length} rows)` }));
    pager.appendChild(nextBtn);
  }

  categories.forEach((cat) => {
    const btn = el("button", { class: "chip", type: "button", "aria-pressed": cat === active ? "true" : "false", text: cat });
    btn.addEventListener("click", () => {
      active = cat;
      page = 1;
      filterBox.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", c.textContent === cat ? "true" : "false"));
      renderTable();
    });
    filterBox.appendChild(btn);
  });
  renderTable();
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function fetchJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

async function main() {
  initTabs();

  let overview, trackRecord, decisions, evidence, account;

  try {
    [overview, trackRecord, decisions, evidence] = await Promise.all([
      fetchJSON("data/overview.json"),
      fetchJSON("data/track_record.json"),
      fetchJSON("data/decisions.json"),
      fetchJSON("data/evidence.json"),
    ]);
  } catch (e) {
    document.getElementById("status-line").textContent = `Could not load dashboard data (${e.message}).`;
    return;
  }

  try {
    account = await fetchJSON("/api/account");
  } catch (e) {
    account = { available: false, reason: "request failed" };
  }

  // Fetched separately from the Promise.all above ON PURPOSE: this file is
  // optional, and a 404 inside that block would take down the whole
  // dashboard rather than just this one card.
  let volForecast = null;
  try {
    volForecast = await fetchJSON("data/vol_forecast.json");
  } catch (e) {
    volForecast = null;
  }

  renderNarrative(overview);
  renderAccount(account);
  renderMarket(overview);
  renderVolatility(overview);
  renderVolForecast(volForecast);
  renderDecisionPath(overview);
  renderPositions(overview, account);

  renderEquityChart(trackRecord);
  renderTrackRecordStats(trackRecord);
  renderValidation(trackRecord);
  renderFalseTrip(trackRecord);
  renderEvidence(evidence);

  renderDecisions(decisions);
}

main();
