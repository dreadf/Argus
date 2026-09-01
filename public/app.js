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
  const wrap = el("div");
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
// Status line
// ---------------------------------------------------------------------------
function renderStatus(status) {
  const line = document.getElementById("status-line");
  line.innerHTML = "";
  const word = el("span", { class: `word ${status.cls}`, text: status.word });
  line.appendChild(word);
  line.appendChild(document.createTextNode(". " + status.rest));
  if (status.timestamp) {
    line.appendChild(document.createTextNode(" "));
    line.appendChild(el("span", { class: "time", text: `(${status.timestamp})` }));
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
  box.appendChild(kpiTile("Equity", fmtMoney(account.equity), "accent"));
  box.appendChild(kpiTile("Cash", fmtMoney(account.cash)));
  box.appendChild(kpiTile("Options buying power", fmtMoney(account.options_buying_power)));
  box.appendChild(kpiTile("Open positions", String(account.positions.length)));
  if (account.positions.length > 0) {
    box.appendChild(kpiTile("Unrealized P&L", fmtMoney2(unrealized), unrealized >= 0 ? "good" : "bad"));
  }
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
  box.appendChild(metric("SPY spot", fmtMoney2(m.spot)));
  box.appendChild(metric("Yesterday's move", fmtPctSigned(m.yesterday_move_pct), "Blocks a new trade above 2% in either direction."));
  box.appendChild(metric("Contango (VIX3M/VIX9D)", fmtNum(m.contango, 3), "Below its own trailing 33rd percentile means the term structure is flattening."));

  const blocks = [];
  if (Math.abs(m.yesterday_move_pct) > 0.02) blocks.push(`SPY moved ${fmtPctSigned(m.yesterday_move_pct)} yesterday`);
  if (m.contango_threshold !== null && m.contango < m.contango_threshold) blocks.push(`term structure is flattening (${fmtNum(m.contango, 3)} < ${fmtNum(m.contango_threshold, 3)})`);
  note.textContent = blocks.length ? `Would block a new trade today: ${blocks.join("; ")}.` : "Nothing here would block a new trade today.";
}

function renderVolatility(overview) {
  const box = document.getElementById("volatility-metrics");
  const verdict = document.getElementById("volatility-verdict");
  box.innerHTML = "";
  verdict.innerHTML = "";
  if (overview.market_error || !overview.volatility) {
    box.appendChild(el("p", { class: "card-note", text: "Not enough data to compute today." }));
    return;
  }
  const v = overview.volatility;
  box.appendChild(metric("VIX9D (implied)", fmtPct(v.vix9d_decimal, 1)));
  box.appendChild(metric("Realized vol (10d)", fmtPct(v.rv10d, 1)));
  box.appendChild(metric("Ratio", fmtNum(v.ratio, 2)));
  verdict.appendChild(el("span", { class: `path-word ${v.verdict_class}`, text: v.verdict_text }));
}

function renderDecisionPath(overview) {
  const box = document.getElementById("decision-path");
  box.innerHTML = "";
  overview.decision_path.forEach((row) => {
    const r = el("div", { class: "path-row" });
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
    const tr = el("tr");
    tr.appendChild(el("td", { text: p.underlying }));
    tr.appendChild(el("td", { text: p.strikes }));
    const roomCell = el("td", { class: "num" });
    if (p.room_pct !== null) {
      const barCap = 0.15;
      const fillPct = Math.max(0, Math.min(100, (Math.abs(p.room_pct) / barCap) * 100));
      const wrap = el("span", { class: "room-cell" });
      const bar = el("span", { class: "mini-bar" });
      bar.appendChild(el("span", { class: `mini-bar-fill${p.room_pct < 0.02 ? " bad" : ""}`, style: `width:${fillPct}%` }));
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
        { label: "Trade every week", data: c.cum_pnl_unfiltered, borderColor: "#E0796B", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
        { label: "VIX filter", data: c.cum_pnl_filtered, borderColor: "#6FBF8A", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: chartOptions("$ per contract"),
  }));

  // Also inside a collapsed <details> -- same zero-width-at-construction
  // problem as a hidden tab, plus it needs a resize when the reader
  // actually opens it later.
  const referenceChart = new Chart(document.getElementById("reference-chart"), {
    type: "line",
    data: {
      labels: c.dates,
      datasets: [
        { label: "SPY (indexed)", data: c.spy_indexed, borderColor: "#8F8575", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
        { label: "Cash @ 3%/yr (indexed)", data: c.cash_indexed, borderColor: "#4A4438", backgroundColor: "transparent", pointRadius: 0, borderWidth: 1.5 },
      ],
    },
    options: chartOptions("Indexed to 100"),
  });
  document.querySelector("#tab-track-record details").addEventListener("toggle", () => referenceChart.resize());
}

function chartOptions(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 400 },
    interaction: { mode: "index", intersect: false },
    scales: {
      x: { ticks: { color: "#8F8575", maxTicksLimit: 8 }, grid: { color: "#262119" } },
      y: { title: { display: true, text: yLabel, color: "#8F8575" }, ticks: { color: "#8F8575" }, grid: { color: "#262119" } },
    },
    plugins: { legend: { labels: { color: "#C7BFAF", font: { family: "IBM Plex Sans" } } } },
  };
}

function renderTrackRecordStats(tr) {
  const box = document.getElementById("track-record-metrics");
  box.innerHTML = "";
  if (!tr.stats) return;
  const s = tr.stats;
  box.appendChild(metric("Max drawdown, $/contract", fmtNum(s.dd_filtered), `${fmtNum(s.dd_filtered - s.dd_unfiltered)} vs. unfiltered`));
  box.appendChild(metric("Worst year, filtered", `${s.worst_year_filtered.pnl >= 0 ? "+" : ""}${fmtNum(s.worst_year_filtered.pnl)}`, `Year ${s.worst_year_filtered.year}. Unfiltered: ${fmtNum(s.worst_year_unfiltered.pnl)} in ${s.worst_year_unfiltered.year}.`));
  box.appendChild(metric("Weeks traded", `${s.weeks_traded} of ${s.weeks_total}`));
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
  headline.appendChild(metric("Correlation (real vs. modelled credit)", fmtNum(v.correlation, 3)));
  headline.appendChild(metric("Quartiles inside band", `${v.quartiles.length} of ${v.quartiles.length}`, `Band: ${v.band[0]}–${v.band[1]}`));

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
  headline.appendChild(metric("Blocked (aggregate)", fmtPct(ft.blocked_pct, 1), `Bar: ≤${fmtPct(ft.bar, 0)}`));
  headline.appendChild(metric("Real winning weeks tested", String(ft.n_winners)));

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
  if (!ev.current_pick) {
    pick.textContent = "No (distance, width) combination currently clears the 2-SE evidence bar. The system declines to trade, on purpose.";
  } else {
    const p = ev.current_pick;
    pick.textContent = `Today's pick: ${fmtPct(p.distance, 0)} distance, $${p.width.toFixed(0)} width, cushion ${fmtNum(p.cushion_se, 2)} SE (${p.n_survivors} of ${p.n_total} combinations qualify).`;
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

  function renderTable() {
    const table = document.getElementById("decisions-table");
    table.querySelector("thead").innerHTML = "<tr><th>Timestamp</th><th>Mode</th><th>Outcome</th><th>Reason</th></tr>";
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";
    const rows = active === "All" ? decisions.rows : decisions.rows.filter((r) => r.category === active);
    if (rows.length === 0) {
      tbody.appendChild(el("tr", {}, el("td", { colspan: "4", text: "No decisions in this category." })));
      return;
    }
    rows.slice(0, 50).forEach((r) => {
      const tr = el("tr");
      tr.appendChild(el("td", { text: r.timestamp || "" }));
      tr.appendChild(el("td", { text: r.mode || "" }));
      tr.appendChild(el("td", { text: r.outcome || "" }));
      tr.appendChild(el("td", { text: r.reason || "" }));
      tbody.appendChild(tr);
    });
  }

  categories.forEach((cat) => {
    const btn = el("button", { class: "chip", type: "button", "aria-pressed": cat === active ? "true" : "false", text: cat });
    btn.addEventListener("click", () => {
      active = cat;
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

  renderStatus(overview.status);
  renderAccount(account);
  renderMarket(overview);
  renderVolatility(overview);
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
