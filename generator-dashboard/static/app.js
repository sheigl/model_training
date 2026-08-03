"use strict";

const state = {
  snapshots: new Map(), // generator slug -> snapshot
  scrapers: new Map(),  // scraper slug -> snapshot
  mode: "generators",   // "generators" | "scrapers"
  active: null,         // slug of the active item in the current mode
  logSSE: null,
  logBuf: new Map(),    // "mode:slug" -> [lines]
  refs: null,           // DOM refs for the active panel
};

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const tabsEl = $("#tabs");
const panelEl = $("#panel");
const sidebarTitle = $("#sidebar-title");
const modeGenBtn = $("#mode-generators");
const modeScrapBtn = $("#mode-scrapers");
const mongoBadge = $("#mongo-status");
const connBadge = $("#conn-status");

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function activeList() {
  return state.mode === "scrapers" ? state.scrapers : state.snapshots;
}

function displayName(item) {
  return state.mode === "scrapers" ? item.name : item.name.replace(/^Generate/, "");
}

function sortedItems() {
  const items = [...activeList().values()];
  return items.sort((a, b) => {
    if (a.running !== b.running) return a.running ? -1 : 1;
    return displayName(a).localeCompare(displayName(b));
  });
}

function renderTabs() {
  tabsEl.replaceChildren();
  for (const item of sortedItems()) {
    const tab = el("div", "tab" + (item.slug === state.active ? " active" : ""));
    const dot = el("span", "dot" + (item.running ? " on" : ""));
    tab.appendChild(dot);
    tab.appendChild(el("span", null, displayName(item)));
    tab.addEventListener("click", () => selectTab(item.slug));
    tabsEl.appendChild(tab);
  }
}

function selectTab(slug) {
  state.active = slug;
  state.refs = null;
  renderTabs();
  const item = activeList().get(slug);
  buildPanel(item);
  openLogSSE(slug);
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

function buildPanel(item) {
  if (state.mode === "scrapers") return buildScraperPanel(item);
  return buildGeneratorPanel(item);
}

function buildGeneratorPanel(g) {
  const refs = {};

  const head = el("div", "gen-head");
  const title = el("div", "gen-title");
  title.appendChild(el("h2", null, g.name));
  const meta = el("div", "gen-meta",
    `${g.category} · ${g.script} · ${g.flag}`);
  title.appendChild(meta);
  head.appendChild(title);

  const actions = el("div", "gen-actions");
  refs.startBtn = el("button", "btn btn-start", "Start");
  refs.stopBtn = el("button", "btn btn-stop", "Stop");
  refs.stopBtn.disabled = true;
  actions.appendChild(refs.startBtn);
  actions.appendChild(refs.stopBtn);
  head.appendChild(actions);
  refs.statusLine = el("div", "status-line", "");

  // Controls
  const controls = el("div", "controls");
  const makeField = (label, id, value, type = "text", step) => {
    const f = el("div", "field");
    f.appendChild(el("label", null, label));
    const input = el("input", null);
    input.id = id;
    input.type = type;
    input.value = value;
    if (step !== undefined) input.step = step;
    f.appendChild(input);
    return f;
  };

  const countField = makeField("Target count", "ctl-count", g.default_count, "number", 1);
  const modelField = makeField("Generation model", "ctl-model", g.default_model || "");
  modelField.querySelector("input").placeholder = "blank = script default";
  const valModelField = makeField("Validation model", "ctl-valmodel", g.default_validation_model || "");
  valModelField.querySelector("input").placeholder = "blank = script default";
  const pctField = makeField("Validation %", "ctl-pct", "1.0", "number", 0.1);
  const dryRow = el("div", "checkbox-row");
  const dryBox = el("input", null);
  dryBox.type = "checkbox";
  dryBox.id = "ctl-dryrun";
  dryRow.appendChild(dryBox);
  dryRow.appendChild(el("label", null, "dry-run"));
  dryRow.querySelector("label").style.fontSize = "12px";
  dryRow.querySelector("label").style.color = "var(--text-dim)";

  controls.append(countField, modelField, valModelField, pctField, dryRow);

  // Metrics
  refs.metricsGrid = el("div", "metrics-grid");
  refs.metricsGrid.appendChild(el("div", "empty", "No metrics yet"));

  const sections = el("div", "two-col");
  const left = el("div");
  left.appendChild(el("div", "section-title", "Per-category validation"));
  refs.catTable = el("div", "table-wrap");
  refs.catTable.appendChild(el("div", "empty", "No data"));
  refs.tplVersions = el("div", "status-line", "");
  left.append(refs.catTable, refs.tplVersions);

  const right = el("div");
  right.appendChild(el("div", "section-title", "Recent outcomes"));
  refs.traceFeed = el("div", "trace-feed");
  right.appendChild(refs.traceFeed);
  sections.append(left, right);

  // Log
  const logSection = el("div");
  const logBar = el("div", "log-bar");
  logBar.appendChild(el("span", null, `Log — ${g.slug}.log`));
  const autoscroll = el("label", null);
  const scrollBox = el("input", null);
  scrollBox.type = "checkbox";
  scrollBox.checked = true;
  autoscroll.appendChild(scrollBox);
  autoscroll.appendChild(document.createTextNode(" auto-scroll"));
  logBar.appendChild(autoscroll);
  refs.logBox = el("pre", "log-box", "");
  logSection.append(logBar, refs.logBox);

  // Progress bar
  refs.progress = el("div", "log-bar");
  refs.progressBar = el("progress", null);
  refs.progressBar.max = 100;
  refs.progressBar.value = 0;
  refs.progress.style.display = "block";
  refs.progress.appendChild(refs.progressBar);
  refs.progress.appendChild(el("span", null, ""));

  panelEl.replaceChildren(head, refs.statusLine, refs.progress, controls, refs.metricsGrid, sections, logSection);
  state.refs = refs;

  refs.startBtn.addEventListener("click", () => onStart(g.slug));
  refs.stopBtn.addEventListener("click", () => onStop(g.slug));
  scrollBox.addEventListener("change", () => renderLog(g.slug));

  updateGeneratorPanel(g);
  renderLog(g.slug);
}

function buildScraperPanel(item) {
  const refs = {};

  const head = el("div", "gen-head");
  const title = el("div", "gen-title");
  title.appendChild(el("h2", null, item.name));
  const meta = el("div", "gen-meta",
    `${item.script}${item.args ? " · " + item.args : ""}`);
  title.appendChild(meta);
  title.appendChild(el("div", "scraper-desc", item.description || ""));
  head.appendChild(title);

  const actions = el("div", "gen-actions");
  refs.startBtn = el("button", "btn btn-start", "Start");
  refs.stopBtn = el("button", "btn btn-stop", "Stop");
  refs.stopBtn.disabled = true;
  actions.appendChild(refs.startBtn);
  actions.appendChild(refs.stopBtn);
  head.appendChild(actions);
  refs.statusLine = el("div", "status-line", "");

  // Controls
  const controls = el("div", "controls");
  const f = el("div", "field");
  f.appendChild(el("label", null, "Extra args"));
  const input = el("input", null);
  input.id = "ctl-args";
  input.type = "text";
  input.value = item.args || "";
  input.placeholder = "blank = script defaults";
  f.appendChild(input);
  controls.appendChild(f);
  controls.appendChild(el("div", "field-hint",
    "CLI args passed to the scraper after its defaults (e.g. --top-by-color red)"));

  // Log
  const logSection = el("div");
  const logBar = el("div", "log-bar");
  logBar.appendChild(el("span", null, `Log — ${item.slug}.log`));
  const autoscroll = el("label", null);
  const scrollBox = el("input", null);
  scrollBox.type = "checkbox";
  scrollBox.checked = true;
  autoscroll.appendChild(scrollBox);
  autoscroll.appendChild(document.createTextNode(" auto-scroll"));
  logBar.appendChild(autoscroll);
  refs.logBox = el("pre", "log-box", "");
  logSection.append(logBar, refs.logBox);

  panelEl.replaceChildren(head, refs.statusLine, controls, logSection);
  state.refs = refs;

  refs.startBtn.addEventListener("click", () => onScraperStart(item.slug));
  refs.stopBtn.addEventListener("click", () => onScraperStop(item.slug));
  scrollBox.addEventListener("change", () => renderLog(item.slug));

  updateScraperPanel(item);
  renderLog(item.slug);
}

// ---------------------------------------------------------------------------
// Generator actions
// ---------------------------------------------------------------------------

function onStart(slug) {
  const refs = state.refs;
  const payload = {
    count: parseInt($("#ctl-count", panelEl).value, 10) || 100,
    model: $("#ctl-model", panelEl).value || null,
    validation_model: $("#ctl-valmodel", panelEl).value || null,
    validation_pct: parseFloat($("#ctl-pct", panelEl).value) || 1.0,
    dry_run: $("#ctl-dryrun", panelEl).checked,
  };
  refs.startBtn.disabled = true;
  refs.startBtn.textContent = "Starting…";
  fetch(`/api/generators/${slug}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        refs.statusLine.textContent = `Started PID ${data.pid} → ${data.log_path}`;
      } else {
        refs.statusLine.textContent = `Failed: ${data.detail || "unknown error"}`;
      }
    })
    .catch((e) => {
      refs.statusLine.textContent = `Request failed: ${e}`;
    })
    .finally(() => {
      refs.startBtn.disabled = false;
      refs.startBtn.textContent = "Start";
    });
}

function onStop(slug) {
  const refs = state.refs;
  refs.stopBtn.disabled = true;
  refs.stopBtn.textContent = "Stopping…";
  fetch(`/api/generators/${slug}/stop`, { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      refs.statusLine.textContent = data.ok
        ? `Stopped (PIDs ${data.killed.join(", ") || "none"})`
        : `Failed: ${data.detail || "unknown error"}`;
    })
    .catch((e) => {
      refs.statusLine.textContent = `Request failed: ${e}`;
    })
    .finally(() => {
      refs.stopBtn.disabled = true;
      refs.stopBtn.textContent = "Stop";
    });
}

// ---------------------------------------------------------------------------
// Scraper actions
// ---------------------------------------------------------------------------

function onScraperStart(slug) {
  const refs = state.refs;
  const payload = {
    args: $("#ctl-args", panelEl).value || "",
  };
  refs.startBtn.disabled = true;
  refs.startBtn.textContent = "Starting…";
  fetch(`/api/scrapers/${slug}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        refs.statusLine.textContent = `Started PID ${data.pid} → ${data.log_path}`;
      } else {
        refs.statusLine.textContent = `Failed: ${data.detail || "unknown error"}`;
      }
    })
    .catch((e) => {
      refs.statusLine.textContent = `Request failed: ${e}`;
    })
    .finally(() => {
      refs.startBtn.disabled = false;
      refs.startBtn.textContent = "Start";
    });
}

function onScraperStop(slug) {
  const refs = state.refs;
  refs.stopBtn.disabled = true;
  refs.stopBtn.textContent = "Stopping…";
  fetch(`/api/scrapers/${slug}/stop`, { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      refs.statusLine.textContent = data.ok
        ? `Stopped (PIDs ${data.killed.join(", ") || "none"})`
        : `Failed: ${data.detail || "unknown error"}`;
    })
    .catch((e) => {
      refs.statusLine.textContent = `Request failed: ${e}`;
    })
    .finally(() => {
      refs.stopBtn.disabled = true;
      refs.stopBtn.textContent = "Stop";
    });
}

// ---------------------------------------------------------------------------
// Snapshot updates (from /api/events SSE)
// ---------------------------------------------------------------------------

function updateSnapshot(snap) {
  mongoBadge.textContent = snap.mongo_connected ? "mongo: connected" : "mongo: unavailable";
  mongoBadge.classList.toggle("badge-ok", snap.mongo_connected);
  mongoBadge.classList.toggle("badge-fail", !snap.mongo_connected);

  let orderChanged = false;
  for (const g of snap.generators) {
    const prev = state.snapshots.get(g.slug);
    if (!prev || prev.running !== g.running) orderChanged = true;
    state.snapshots.set(g.slug, g);
  }
  for (const s of snap.scrapers || []) {
    const prev = state.scrapers.get(s.slug);
    if (!prev || prev.running !== s.running) orderChanged = true;
    state.scrapers.set(s.slug, s);
  }
  if (orderChanged) {
    renderTabs();
  } else {
    refreshTabDots();
  }

  if (state.active) {
    const item = activeList().get(state.active);
    if (item) updateActivePanel(item);
  }
}

function refreshTabDots() {
  const tabs = [...tabsEl.children];
  for (const item of activeList().values()) {
    const label = displayName(item);
    const tab = tabs.find((t) => t.textContent.trim().endsWith(label));
    if (tab) {
      const dot = tab.querySelector(".dot");
      dot.className = "dot" + (item.running ? " on" : "");
    }
  }
}

function fmt(n) {
  return n == null ? "—" : Number(n).toLocaleString();
}

function updateActivePanel(item) {
  if (state.mode === "scrapers") return updateScraperPanel(item);
  return updateGeneratorPanel(item);
}

function updateScraperPanel(item) {
  if (!state.refs) return;
  const refs = state.refs;
  refs.stopBtn.disabled = !item.running;
  refs.stopBtn.textContent = "Stop";
  refs.startBtn.disabled = false;
  refs.startBtn.textContent = "Start";

  const inst = item.instances || [];
  const pids = inst.map((i) => `PID ${i.pid}`).join(", ");
  refs.statusLine.textContent = item.running
    ? `RUNNING (${pids || "no pid"})`
    : "STOPPED";
}

function updateGeneratorPanel(g) {
  if (!state.refs) return;
  const refs = state.refs;
  const inst = g.instances || [];

  refs.stopBtn.disabled = !g.running;
  refs.stopBtn.textContent = "Stop";
  refs.startBtn.disabled = false;
  refs.startBtn.textContent = "Start";

  const target = inst.length ? Math.max(...inst.map((i) => i.count)) : g.default_count;
  const counts = inst.map((i) => `PID ${i.pid}${i.count ? ` · target ${fmt(i.count)}` : ""}`).join(", ");
  refs.statusLine.textContent = g.running
    ? `RUNNING ${counts ? `(${counts})` : ""} — target ${fmt(target)}`
    : `STOPPED — target ${fmt(target)}`;

  const m = g.metrics ? g.metrics.metrics : null;
  if (!m) {
    refs.metricsGrid.replaceChildren(el("div", "empty", "No metrics yet"));
    refs.progressBar.value = 0;
  } else {
    const candidates = m.total_candidates || 0;
    refs.progressBar.value = target > 0 ? Math.min(100, (candidates / target) * 100) : 0;
    const cards = [
      ["Candidates", fmt(m.total_candidates)],
      ["Validated", fmt(m.total_validated)],
      ["Skipped", fmt(m.total_skipped)],
      ["Passed", fmt(m.total_passed)],
      ["Failed", fmt(m.total_failed)],
      ["Fix attempts", fmt(m.total_fix_attempts)],
      ["Pass rate", m.overall_pass_rate != null ? `${m.overall_pass_rate}%` : "—"],
      ["1st-attempt rate", m.first_attempt_pass_rate != null ? `${m.first_attempt_pass_rate}%` : "—"],
      ["Fix recovery", m.fix_recovery_rate != null ? `${m.fix_recovery_rate}%` : "—"],
      ["Avg score", m.avg_score != null ? m.avg_score : "—"],
    ];
    refs.metricsGrid.replaceChildren(...cards.map(([k, v]) => {
      const card = el("div", "metric-card");
      card.appendChild(el("div", "k", k));
      card.appendChild(el("div", "v", v));
      return card;
    }));

    // per-category table
    const byCat = m.by_category || {};
    const keys = Object.keys(byCat);
    if (!keys.length) {
      refs.catTable.replaceChildren(el("div", "empty", "No data"));
    } else {
      const table = el("table", null);
      const thead = el("thead", null);
      const tr = el("tr", null);
      for (const h of ["category", "cand", "val", "pass", "fail", "rate"]) {
        tr.appendChild(el("th", null, h));
      }
      thead.appendChild(tr);
      const tbody = el("tbody", null);
      for (const k of keys) {
        const s = byCat[k];
        const row = el("tr", null);
        row.appendChild(el("td", null, k));
        row.appendChild(el("td", null, fmt(s.candidates)));
        row.appendChild(el("td", null, fmt(s.validated)));
        row.appendChild(el("td", "pass", fmt(s.passed)));
        row.appendChild(el("td", "fail", fmt(s.failed)));
        row.appendChild(el("td", null, `${s.pass_rate ?? 0}%`));
        tbody.appendChild(row);
      }
      table.append(thead, tbody);
      refs.catTable.replaceChildren(table);
    }

    // template versions
    const tv = { ...(m.template_versions || {}), ...(m.validator_template_versions || {}) };
    const keys2 = Object.keys(tv);
    refs.tplVersions.textContent = keys2.length
      ? "templates: " + keys2.map((k) => `${k}@${tv[k]}`).join(", ")
      : "";
  }
}

// ---------------------------------------------------------------------------
// Log + traces (per-tab SSE)
// ---------------------------------------------------------------------------

function openLogSSE(slug) {
  if (state.logSSE) state.logSSE.close();
  const key = `${state.mode}:${slug}`;
  state.logBuf.set(key, []);
  const refs = state.refs;
  if (refs) {
    refs.logBox.textContent = "connecting…";
    if (refs.traceFeed) refs.traceFeed.replaceChildren(el("div", "empty", "waiting for data…"));
  }
  const url = state.mode === "scrapers" ? `/api/scraper-logs/${slug}` : `/api/logs/${slug}`;
  const src = new EventSource(url);
  state.logSSE = src;

  src.addEventListener("message", (ev) => {
    if (state.active !== slug) return;
    let data;
    try { data = JSON.parse(ev.data); } catch { return; }
    if (data.type === "init") {
      state.logBuf.set(key, data.lines);
      renderLog(slug);
    } else if (data.type === "lines") {
      const buf = state.logBuf.get(key) || [];
      buf.push(...data.lines);
      if (buf.length > 3000) buf.splice(0, buf.length - 3000);
      state.logBuf.set(key, buf);
      renderLog(slug);
    } else if (data.type === "traces") {
      renderTraces(data.traces);
    }
  });

  src.addEventListener("error", () => {
    if (state.active !== slug) return;
    if (refs) refs.logBox.textContent = "log stream disconnected — retrying…";
  });
}

function renderLog(slug) {
  const refs = state.refs;
  if (!refs || state.active !== slug) return;
  const key = `${state.mode}:${slug}`;
  const buf = state.logBuf.get(key) || [];
  const atBottom = refs.logBox.scrollTop + refs.logBox.clientHeight >= refs.logBox.scrollHeight - 40;
  refs.logBox.textContent = buf.length ? buf.join("\n") : "(empty)";
  if (atBottom) refs.logBox.scrollTop = refs.logBox.scrollHeight;
}

function renderTraces(traces) {
  const refs = state.refs;
  if (!refs) return;
  if (!traces || !traces.length) {
    refs.traceFeed.replaceChildren(el("div", "empty", "No traces yet"));
    return;
  }
  refs.traceFeed.replaceChildren(
    ...traces.map((t) => {
      const row = el("div", "trace-row");
      const badge = el("span", `outcome outcome-${t.final_outcome}`, t.final_outcome);
      row.appendChild(badge);
      row.appendChild(el("span", null, t.source_template || "?"));
      row.appendChild(el("span", null, t.created_at ? t.created_at.slice(11, 19) : ""));
      return row;
    })
  );
}

// ---------------------------------------------------------------------------
// Mode toggle
// ---------------------------------------------------------------------------

function setMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  state.active = null;
  state.refs = null;
  modeGenBtn.classList.toggle("active", mode === "generators");
  modeScrapBtn.classList.toggle("active", mode === "scrapers");
  sidebarTitle.textContent = mode === "scrapers" ? "Scrapers" : "Generators";

  const items = sortedItems();
  if (items.length) {
    state.active = items[0].slug;
    renderTabs();
    buildPanel(activeList().get(state.active));
    openLogSSE(state.active);
  } else {
    renderTabs();
    panelEl.replaceChildren(el("div", "empty", "No items"));
  }
}

modeGenBtn.addEventListener("click", () => setMode("generators"));
modeScrapBtn.addEventListener("click", () => setMode("scrapers"));

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function boot() {
  try {
    const snap = await fetch("/api/generators").then((r) => r.json());
    for (const g of snap.generators) state.snapshots.set(g.slug, g);
    for (const s of snap.scrapers || []) state.scrapers.set(s.slug, s);
    mongoBadge.textContent = snap.mongo_connected ? "mongo: connected" : "mongo: unavailable";
    mongoBadge.classList.toggle("badge-ok", snap.mongo_connected);
    mongoBadge.classList.toggle("badge-fail", !snap.mongo_connected);
    const items = sortedItems();
    if (items.length) {
      state.active = items[0].slug;
      renderTabs();
      buildPanel(activeList().get(state.active));
      openLogSSE(state.active);
    }
  } catch (e) {
    panelEl.replaceChildren(el("div", "empty", `Failed to load dashboard: ${e}`));
  }

  const snapSrc = new EventSource("/api/events");
  snapSrc.addEventListener("message", (ev) => {
    try { updateSnapshot(JSON.parse(ev.data)); } catch { /* ignore */ }
  });
  snapSrc.addEventListener("error", () => {
    connBadge.textContent = "disconnected";
    connBadge.classList.add("badge-fail");
  });
  snapSrc.addEventListener("open", () => {
    connBadge.textContent = "live";
    connBadge.classList.remove("badge-fail");
  });
}

document.addEventListener("DOMContentLoaded", boot);
