"use strict";

const PAGE_SIZE = 100;
const REFRESH_MS = 5000;
const SEARCH_DELAY_MS = 300;

const state = {
  flaggedOnly: true,
  search: "",
  newestId: null, // newest visit shown, for fetching new ones
  oldestId: null, // oldest visit shown, for "Load older visits"
  lastAlertedId: null, // newest flagged visit already announced
  generation: 0, // bumped on every reset, so stale responses are dropped
};

const $ = (id) => document.getElementById(id);

function startOfToday() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today.getTime();
}

async function getJSON(path, params = {}) {
  const url = new URL(path, location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, value);
    }
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function visitParams(extra = {}) {
  return {
    flagged: state.flaggedOnly ? "1" : "",
    q: state.search,
    limit: PAGE_SIZE,
    ...extra,
  };
}

function safeHref(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

function renderVisit(visit) {
  const item = document.createElement("li");
  item.className = "visit";
  if (visit.flagged) item.classList.add("flagged");

  const time = document.createElement("time");
  const date = new Date(visit.time);
  time.dateTime = date.toISOString();
  time.textContent = date.toLocaleString();

  const host = document.createElement("span");
  host.className = "host";
  host.textContent = visit.host;

  const href = safeHref(visit.url);
  const url = document.createElement(href ? "a" : "span");
  url.className = "url";
  url.textContent = visit.url;
  if (href) {
    url.href = href;
    url.target = "_blank";
    url.rel = "noopener noreferrer";
  }

  item.append(time, host);
  if (visit.blocked || visit.flagged) {
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = visit.blocked ? "Blocked" : "Flagged";
    item.append(badge);
  }
  item.append(url);
  return item;
}

function updateEmptyState() {
  const empty = $("empty");
  const hasVisits = $("visits").children.length > 0;
  empty.hidden = hasVisits;
  if (!hasVisits) {
    if (state.search) empty.textContent = "No visits match your search.";
    else if (state.flaggedOnly) empty.textContent = "No flagged visits.";
    else empty.textContent = "No visits recorded yet.";
  }
}

async function reloadVisits() {
  const generation = ++state.generation;
  const data = await getJSON("/api/visits", visitParams());
  if (generation !== state.generation) return;
  $("visits").replaceChildren(...data.visits.map(renderVisit));
  state.newestId = data.visits.length ? data.visits[0].id : null;
  state.oldestId = data.visits.length ? data.visits[data.visits.length - 1].id : null;
  $("load-more").hidden = !data.has_more;
  updateEmptyState();
}

async function fetchNewVisits() {
  if (state.newestId === null) return reloadVisits();
  const generation = state.generation;
  const data = await getJSON("/api/visits", visitParams({ after_id: state.newestId }));
  if (generation !== state.generation || data.visits.length === 0) return;
  if (data.has_more) return reloadVisits(); // too many to prepend
  $("visits").prepend(...data.visits.map(renderVisit));
  state.newestId = data.visits[0].id;
  updateEmptyState();
}

async function loadOlderVisits() {
  const generation = state.generation;
  const data = await getJSON("/api/visits", visitParams({ before_id: state.oldestId }));
  if (generation !== state.generation) return;
  $("visits").append(...data.visits.map(renderVisit));
  if (data.visits.length) state.oldestId = data.visits[data.visits.length - 1].id;
  $("load-more").hidden = !data.has_more;
}

function renderSummary(summary) {
  $("stat-visits").textContent = summary.visits.toLocaleString();
  $("stat-flagged").textContent = summary.flagged.toLocaleString();
  $("stat-watched").textContent = summary.watched_domains.toLocaleString();

  const top = summary.top_flagged_hosts;
  $("top-flagged").hidden = top.length === 0;
  $("top-flagged-list").replaceChildren(
    ...top.map(({ host, count }) => {
      const item = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = host;
      const visits = document.createElement("span");
      visits.className = "count";
      visits.textContent = count === 1 ? "1 visit" : `${count} visits`;
      item.append(name, visits);
      return item;
    }),
  );
}

async function announceNewFlagged(latestFlaggedId) {
  if (latestFlaggedId === null) return;
  if (state.lastAlertedId === null) {
    state.lastAlertedId = latestFlaggedId; // don't announce what was there on load
    return;
  }
  if (latestFlaggedId <= state.lastAlertedId) return;
  const data = await getJSON("/api/visits", {
    flagged: "1",
    after_id: state.lastAlertedId,
    limit: 50,
  });
  state.lastAlertedId = latestFlaggedId;
  if (data.visits.length === 0) return;

  const newest = data.visits[0];
  const text =
    data.visits.length === 1
      ? `Flagged visit: ${newest.host}`
      : `${data.visits.length} new flagged visits, latest: ${newest.host}`;
  $("alert-text").textContent = text;
  $("alert").hidden = false;
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification("URL Monitor", { body: text });
  }
}

async function refresh() {
  try {
    const summary = await getJSON("/api/summary", { since: startOfToday() });
    renderSummary(summary);
    await Promise.all([fetchNewVisits(), announceNewFlagged(summary.latest_flagged_id)]);
    $("status").textContent = `Live · updated ${new Date().toLocaleTimeString()}`;
    $("status").classList.remove("offline");
  } catch (error) {
    console.error(error);
    $("status").textContent = "Can't reach URL Monitor. Is it running?";
    $("status").classList.add("offline");
  }
}

function selectTab(flaggedOnly) {
  state.flaggedOnly = flaggedOnly;
  $("tab-flagged").setAttribute("aria-selected", String(flaggedOnly));
  $("tab-all").setAttribute("aria-selected", String(!flaggedOnly));
  reloadVisits().catch(console.error);
}

function setUpNotifications() {
  const button = $("notify");
  if (!("Notification" in window) || Notification.permission !== "default") return;
  button.hidden = false;
  button.addEventListener("click", async () => {
    await Notification.requestPermission();
    button.hidden = true;
  });
}

function init() {
  $("tab-flagged").addEventListener("click", () => selectTab(true));
  $("tab-all").addEventListener("click", () => selectTab(false));
  $("load-more").addEventListener("click", () => loadOlderVisits().catch(console.error));
  $("alert-dismiss").addEventListener("click", () => {
    $("alert").hidden = true;
  });

  let searchTimer;
  $("search").addEventListener("input", (event) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = event.target.value.trim();
      reloadVisits().catch(console.error);
    }, SEARCH_DELAY_MS);
  });

  setUpNotifications();
  refresh();
  setInterval(refresh, REFRESH_MS);
}

init();
