// 理小龙 CDUTdino v2 entry: chat (SSE with fallback) + map, wired with ES modules.
import { ask } from "./sse.mjs";
import { initialPlan, reducePlan } from "./plan-state.mjs";
import { createChecklistStore, sessionId } from "./checklist-store.mjs";
import { FILTERS, filterList, hasPosition, searchPlaces } from "./places.mjs";
import { h } from "./dom.mjs";
import { answerCards, planCard } from "./render.mjs";
import { cardsIn, stepIn, tick } from "./motion.mjs";
import { createMap } from "./map.mjs";
import { distanceMeters, formatDistance, toGcj02 } from "./geo.mjs";
import { initialOrigin, originLabel, reduceOrigin, routeOrigin } from "./origin.mjs";
import { dragOffset, initialSheet, reduceSheet, releaseVelocity, sheetOffset, visibleHeight } from "./sheet.mjs";
import { createHeadingTracker, needsPermission, viewRotation } from "./heading.mjs";

const $ = (id) => document.getElementById(id);
const thread = $("thread"), form = $("chat-form"), input = $("question"), send = $("send");
const store = createChecklistStore(localStorage, sessionId(sessionStorage));
const HEADERS = { "Content-Type": "application/json", "X-CampusPilot-Request": "1" };
let busy = false, ready = false, allPlaces = [];
let origin = initialOrigin(), sheet = initialSheet(), pendingTarget = null, current = null, guiding = false;
const placeCards = new Set();

window.element = (tag, text, className) => h(tag, { class: className }, text ?? ""); // for guidance.js

const map = createMap({
  frame: $("map-frame"), fallback: $("map-fallback"),
  status: (text) => { $("map-status").textContent = text; $("map-status").hidden = !text; },
  onSelect: (place) => highlight(place),
  onOrigin: (position, name) => setOrigin({ type: "map", position, label: name }),
  onPoi: (poi) => showCard({ name: poi.name, detail: poi.address, position: poi.position, poi: true }),
});

// ---- origin ---------------------------------------------------------------------------
function setOrigin(action) {
  const before = origin; origin = reduceOrigin(origin, action);
  if (origin === before) return;
  $("origin-label").textContent = originLabel(origin);
  document.body.classList.toggle("picking-origin", origin.picking);
  const from = routeOrigin(origin);
  for (const c of placeCards) if (c.isConnected) c.update(from); else placeCards.delete(c);
  if (current) showCard(current);
  if (from && !origin.picking) {
    if (pendingTarget) { const t = pendingTarget; pendingTarget = null; go(t); }
    else if (action.type !== "gps") note(`起点：${origin.label}。点任一地点的「带我去」规划路线。`);
  }
}
function locate({ quiet = false } = {}) {
  return new Promise((resolve) => {
    if (!navigator.geolocation || !window.isSecureContext) return resolve(false);
    navigator.geolocation.getCurrentPosition((fix) => {
      setOrigin({ type: "gps", position: { longitude: fix.coords.longitude, latitude: fix.coords.latitude, coordinate_system: "WGS84" } });
      resolve(true);
    }, () => { if (!quiet) setOrigin({ type: "gps-denied" }); resolve(false); }, { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 });
  });
}
function pickOnMap() {
  if (!map.pickOrigin()) { note("地图未加载，无法点选起点；可从列表选择地点出发。"); return; }
  setOrigin({ type: "pick-start" }); collapseForMap(); note();
  $("place-card").hidden = true; placeCrosshair();
}
// Crosshair sits in the middle of the visible map (above the sheet on phones).
function placeCrosshair() {
  const wrap = document.querySelector(".mapwrap").getBoundingClientRect();
  const bottom = mobile() ? sheetVisible() : 0, top = mobile() ? 130 : 110;
  const y = Math.round(top + (wrap.height - bottom - top) / 2), x = Math.round(wrap.width / 2);
  $("crosshair").style.transform = `translate(${x}px, ${y}px)`;
  $("crosshair").dataset.x = x; $("crosshair").dataset.y = y;
}
$("pick-here").addEventListener("click", () => map.pickAt(Number($("crosshair").dataset.x), Number($("crosshair").dataset.y)));
$("pick-cancel").addEventListener("click", () => { map.cancelPick(); setOrigin({ type: "pick-cancel" }); });
function originChooser(message) {
  const select = h("select", { class: "origin-select", "aria-label": "从地点出发" },
    h("option", { value: "" }, "从地点出发…"),
    allPlaces.filter(hasPosition).map((p) => h("option", { value: p.place_id }, p.name)));
  select.addEventListener("change", () => { const p = allPlaces.find((x) => x.place_id === select.value); if (p) setOrigin({ type: "place", place: p }); });
  const useGps = async () => {
    note("正在获取你的位置（只在本机使用）…"); setOrigin({ type: "use-gps" });
    if (!(await locate())) note(...originChooser("定位不可用，请换一种方式选择起点："));
  };
  return [h("span", {}, message), h("span", { class: "chooser" },
    h("button", { type: "button", class: "chip", onclick: useGps }, "📍 我的位置"),
    h("button", { type: "button", class: "chip", onclick: pickOnMap }, "在地图上点选"), select)];
}

// ---- place card on the map (our places + AMap POIs) -----------------------------------
function showCard(target) {
  current = target;
  const card = $("place-card"), from = routeOrigin(origin);
  const d = from && target.position ? distanceMeters(from, target.position) : null;
  const confirmed = target.position?.verification_status === "confirmed";
  const located = !!target.position;
  const asOrigin = () => setOrigin(target.place ? { type: "place", place: target.place } : { type: "map", position: target.position, label: target.name });
  const asDestination = () => { if (routeOrigin(origin)) go(target); else { pendingTarget = target; note(...originChooser(`终点：${target.name}。请选择起点：`)); } };
  card.replaceChildren(
    h("button", { type: "button", class: "card-close", "aria-label": "关闭", onclick: () => { card.hidden = true; current = null; } }, "×"),
    h("strong", {}, target.name),
    h("span", {}, [target.detail, d != null ? `距起点约 ${formatDistance(d)}` : null].filter(Boolean).join(" · ")),
    located && !confirmed ? h("span", { class: "ref-note" }, target.poi ? "高德地点 · 位置仅供参考" : "位置仅供参考，入口以现场为准") : null,
    located ? h("div", { class: "card-actions" },
      h("button", { type: "button", class: "chip", onclick: asOrigin }, "设为起点"),
      h("button", { type: "button", class: "chip", onclick: asDestination }, "设为终点"),
      h("button", { type: "button", class: "chip go", onclick: () => go(target) }, "带我去")) : h("span", { class: "ref-note" }, "暂无位置"));
  card.hidden = false;
}
function highlight(place) {
  map.focus(place);
  document.querySelectorAll(".place-row").forEach((c) => c.classList.toggle("active", c.dataset.placeId === place.place_id));
  showCard({ name: place.name, detail: place.campus || "", position: hasPosition(place) ? place.position : null, place });
}

// ---- routing + guidance ---------------------------------------------------------------
function note(...children) {
  const n = $("route-note"); n.replaceChildren(...children.filter(Boolean)); n.hidden = !n.childNodes.length;
  if (!n.hidden && !guiding) collapseForMap(); // on phones the map (and this note) must be visible
}
const asTarget = (t) => (t.place_id ? { name: t.name, position: hasPosition(t) ? t.position : null, place: t } : t);
async function go(raw) {
  const target = asTarget(raw);
  if (target.place) highlight(target.place);
  if (!target.position) { note(`${target.name} 暂无位置，无法规划路线。`); return; }
  if (!routeOrigin(origin)) {
    pendingTarget = target;
    note("正在获取你的位置（只在本机使用）…");
    if (!(await locate())) note(...originChooser(`去 ${target.name}：无法定位，请选择起点`));
    return; // a successful fix resumes the pending target through setOrigin
  }
  pendingTarget = null;
  note(`正在规划：${origin.label} → ${target.name}…`);
  const dest = target.place ? { place_id: target.place.place_id } : { position: toGcj02(target.position) };
  const r = await map.route(dest, routeOrigin(origin));
  const change = () => h("button", { type: "button", class: "chip ghost", onclick: () => note(...originChooser("换个起点：")) }, "换起点");
  if (r.status !== "success") { note(h("span", {}, r.message || "暂未取得步行路线，可换个起点再试。"), change()); return; }
  note(h("b", {}, `${origin.label} → ${target.name}`),
    h("span", {}, ` 步行约 ${Math.max(1, Math.round(r.time / 60))} 分钟 · ${Math.round(r.distance)} 米 `),
    h("button", { type: "button", class: "chip go", onclick: () => startGuidance(target, r) }, "开始步行引导"), change());
}
function startGuidance(target, r) {
  enableHeading(); // inside the click: iOS asks for motion permission only on a user gesture
  window.Guidance?.start({
    requestId: map.routeId, target: { name: target.name },
    detail: target.position?.verification_status === "confirmed" ? "" : "位置仅供参考，入口以现场为准",
    replan: (gps) => { setOrigin({ type: "use-gps" }); if (gps) setOrigin({ type: "gps", position: gps }); go(target); },
    route: { geometry: r.geometry, stepEnds: r.step_ends, distance: r.distance, time: r.time, steps: r.steps },
  });
}
// Guidance is a classic script whose own buttons call its internal stop(); observe the
// slot it renders into to drive the sheet and compass.
new MutationObserver(() => {
  const on = !!document.querySelector(".guidance-slot")?.childElementCount;
  if (on !== guiding) { guiding = on; guidanceChanged(on); }
}).observe(document.querySelector(".guidance-slot"), { childList: true });
function guidanceChanged(on) {
  document.body.classList.toggle("guiding", on);
  applySheet({ type: on ? "guidance-start" : "guidance-stop" });
  $("heading-toggle").hidden = !on;
  if (on) { note(); $("place-card").hidden = true; } else stopHeading();
}

// ---- compass heading ------------------------------------------------------------------
const tracker = createHeadingTracker();
let headingUp = false, headingOn = false, raf = 0, courseWatch = null;
const screenAngle = () => screen.orientation?.angle ?? window.orientation ?? 0;
function onOrientation(e) { tracker.compass(e, screenAngle()); schedule(); }
function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (tracker.value != null) map.heading(viewRotation(tracker.value, headingUp)); }); }
async function enableHeading() {
  if (headingOn) return; headingOn = true;
  const DOE = window.DeviceOrientationEvent;
  try { if (needsPermission(DOE) && (await DOE.requestPermission()) !== "granted") throw new Error("denied"); } catch { /* GPS course only */ }
  if ("ondeviceorientationabsolute" in window) window.addEventListener("deviceorientationabsolute", onOrientation);
  else window.addEventListener("deviceorientation", onOrientation);
  if (navigator.geolocation) courseWatch = navigator.geolocation.watchPosition((f) => { tracker.gps(f.coords); schedule(); }, () => {}, { enableHighAccuracy: true, maximumAge: 2000 });
}
function stopHeading() {
  if (!headingOn) return; headingOn = false;
  window.removeEventListener("deviceorientationabsolute", onOrientation); window.removeEventListener("deviceorientation", onOrientation);
  if (courseWatch != null) navigator.geolocation.clearWatch(courseWatch);
  courseWatch = null; map.northUp();
}
$("heading-toggle").addEventListener("click", (e) => {
  headingUp = !headingUp; e.currentTarget.setAttribute("aria-pressed", String(headingUp));
  e.currentTarget.textContent = headingUp ? "🧭 朝向朝上" : "🧭 北朝上";
  if (!headingUp) map.northUp();
  schedule();
});

// ---- mobile bottom sheet: follows the finger, snaps on release ---------------------
const chat = document.querySelector(".chat");
const PEEK = () => 66 + ($("safe-probe")?.offsetHeight || 0); // handle + header + home indicator
let sheetY = 0;
const sheetVisible = () => visibleHeight(chat.offsetHeight, sheetY);
function setSheetY(y, animate) {
  sheetY = y;
  chat.style.transition = animate ? "" : "none";
  chat.style.transform = `translate3d(0, ${Math.round(y)}px, 0)`;
  document.body.style.setProperty("--sheet-visible", (mobile() ? sheetVisible() : 0) + "px");
}
function applySheet(action) {
  sheet = reduceSheet(sheet, action);
  document.body.classList.toggle("sheet-collapsed", sheet.state === "collapsed");
  $("sheet-handle").setAttribute("aria-expanded", String(sheet.state === "expanded"));
  if (!mobile()) { chat.style.transform = ""; document.body.style.setProperty("--sheet-visible", "0px"); return; }
  setSheetY(sheetOffset(sheet.state, chat.offsetHeight, PEEK()), true);
  map.insets(sheetVisible() + 12);
}
const mobile = () => matchMedia("(max-width:760px)").matches;
const collapseForMap = () => mobile() && applySheet({ type: "collapse" });
addEventListener("resize", () => applySheet({ type: "noop" }));
$("sheet-handle").addEventListener("click", () => applySheet({ type: "toggle" }));
let drag = null;
chat.addEventListener("touchstart", (e) => {
  if (!mobile() || e.touches.length !== 1) return;
  // Drag from the handle/header anywhere; inside the thread only when it is scrolled to top.
  const inThread = e.target.closest(".thread"), onControl = e.target.closest("textarea,select,input");
  if (onControl || (inThread && thread.scrollTop > 0 && sheet.state === "expanded")) return;
  const y = e.touches[0].clientY;
  drag = { y0: y, base: sheetY, moved: false, inThread: !!inThread, samples: [[e.timeStamp, y]] };
}, { passive: true });
chat.addEventListener("touchmove", (e) => {
  if (!drag) return;
  const y = e.touches[0].clientY, dy = y - drag.y0;
  if (!drag.moved) {
    if (Math.abs(dy) < 6) return;
    // Scrolling the expanded thread upward stays a scroll.
    if (drag.inThread && sheet.state === "expanded" && dy < 0) { drag = null; return; }
    drag.moved = true;
  }
  e.preventDefault();
  drag.samples.push([e.timeStamp, y]); if (drag.samples.length > 8) drag.samples.shift();
  setSheetY(dragOffset(drag.base, dy, sheetOffset("collapsed", chat.offsetHeight, PEEK())), false);
}, { passive: false });
const endDrag = (e) => {
  if (!drag) return;
  const d = drag; drag = null;
  if (!d.moved) return;
  const y = e.changedTouches[0].clientY;
  d.samples.push([e.timeStamp, y]);
  const max = sheetOffset("collapsed", chat.offsetHeight, PEEK());
  // Position decides by default (past halfway → collapse); a flick overrides it.
  const v = releaseVelocity(d.samples), pos = sheetY > max / 2 ? 1 : -1;
  applySheet({ type: "drag-end", dy: pos * 100, velocity: v });
};
chat.addEventListener("touchend", endDrag, { passive: true });
chat.addEventListener("touchcancel", endDrag, { passive: true });
input.addEventListener("focus", () => applySheet({ type: "focus-input" }));
applySheet({ type: "noop" });

// ---- chat -----------------------------------------------------------------------------
function bubble(text) { const b = h("div", { class: "msg-user" }, text); thread.append(b); return b; }
function scrollEnd() { thread.scrollTo({ top: thread.scrollHeight, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }

async function submit(text) {
  if (busy || !ready || !text.trim()) return;
  busy = true; send.disabled = true; $("send-label").textContent = "思考中";
  $("empty")?.remove();
  bubble(text); scrollEnd();
  let state = initialPlan();
  const planHost = h("div", { class: "plan-host" });
  const live = h("p", { class: "conclusion streaming", "aria-live": "polite" });
  thread.append(planHost);
  const seen = new Set();
  const paint = () => {
    const card = planCard(state);
    if (!state.steps.length) return;
    planHost.replaceChildren(card);
    for (const li of card.querySelectorAll(".step")) {
      const key = li.dataset.key + ":" + [...li.classList].join(".");
      if (!seen.has(li.dataset.key)) stepIn(li);
      else if (li.classList.contains("done") && !seen.has(key)) tick(li.querySelector(".dot"));
      seen.add(li.dataset.key); seen.add(key);
    }
  };
  const result = await ask(text, (e) => {
    state = reducePlan(state, e);
    if (e.event === "answer_delta") { if (!live.isConnected) thread.append(live); live.textContent = state.answer; }
    else paint();
    scrollEnd();
  });
  live.remove();
  if (!result.ok) {
    thread.append(h("div", { class: "card error", role: "alert" }, result.body?.message || "暂时无法回答，请稍后再试。"));
  } else {
    if (!result.streamed) planHost.remove();
    else { state = reducePlan(state, { event: "final", data: {} }); paint(); }
    const cards = answerCards(result.body, { store, onFocus: highlight, onGo: go, onFrom: (p) => setOrigin({ type: "place", place: p }), origin: routeOrigin(origin) });
    for (const c of cards) if (c.update) placeCards.add(c);
    thread.append(...cards); cardsIn(cards);
    map.reveal((result.body.places || []).map((p) => p.place_id));
    const first = (result.body.places || []).find((p) => p.position);
    if (first) highlight(first);
  }
  busy = false; send.disabled = false; $("send-label").textContent = "发送";
  if (!mobile()) input.focus({ preventScroll: true });
}

form.addEventListener("submit", (e) => { e.preventDefault(); const t = input.value; input.value = ""; submit(t); });
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll("[data-question]").forEach((b) => b.addEventListener("click", () => submit(b.dataset.question)));
$("new-chat").addEventListener("click", async () => { await fetch("/api/session", { method: "POST", headers: HEADERS }); location.reload(); });
$("origin-button").addEventListener("click", () => note(...originChooser("选择起点：")));

// ---- map search: our places first, then AMap POIs near campus --------------------------
const searchBox = $("map-search"), results = $("search-results");
let searchTimer = 0, searchToken = 0;
function closeSearch() { results.hidden = true; results.replaceChildren(); }
function resultRow(label, sub, pick) {
  return h("li", { role: "option" }, h("button", { type: "button", onclick: () => { closeSearch(); searchBox.blur(); pick(); } }, h("b", {}, label), sub ? h("small", {}, sub) : null));
}
async function runSearch(q) {
  const token = ++searchToken;
  const local = searchPlaces(allPlaces, q);
  const rows = local.map((p) => resultRow(p.name, hasPosition(p) ? (p.campus || "校内地点") : "暂无位置", () => { map.reveal([p.place_id]); highlight(p); collapseForMap(); }));
  results.replaceChildren(...rows, ...(rows.length ? [] : [h("li", { class: "hint" }, "正在搜索高德地点…")])); results.hidden = false;
  const pois = await map.searchPoi(q);
  if (token !== searchToken) return;
  const names = new Set(local.map((p) => p.name));
  const extra = pois.filter((p) => !names.has(p.name)).slice(0, 6).map((poi) => resultRow(poi.name, `高德 · ${poi.address || "校园周边"}`, () => { map.centerOn(poi.position); showCard({ name: poi.name, detail: poi.address, position: poi.position, poi: true }); collapseForMap(); }));
  results.replaceChildren(...rows, ...extra);
  if (!rows.length && !extra.length) results.replaceChildren(h("li", { class: "hint" }, "没有找到，可直接点地图上的地点"));
}
searchBox.addEventListener("input", () => { clearTimeout(searchTimer); const q = searchBox.value.trim(); if (!q) { searchToken++; closeSearch(); return; } searchTimer = setTimeout(() => runSearch(q), 250); });
searchBox.addEventListener("keydown", (e) => { if (e.key === "Escape") { searchBox.value = ""; closeSearch(); } if (e.key === "Enter") { e.preventDefault(); results.querySelector("button")?.click(); } });
document.addEventListener("click", (e) => { if (!e.target.closest(".map-search")) closeSearch(); });

const filters = $("filters"), filterRow = $("filter-list");
function showFilterList(id) {
  const list = filterList(allPlaces, id);
  filterRow.replaceChildren(...list.map((p) => h("button", { type: "button", class: "chip", onclick: () => { map.reveal([p.place_id]); highlight(p); collapseForMap(); } }, p.name)));
  filterRow.hidden = !list.length; filterRow.scrollLeft = 0;
}
for (const f of FILTERS) {
  const b = h("button", { type: "button", class: `chip ${f.id === "all" ? "active" : ""}`, "aria-pressed": f.id === "all" ? "true" : "false" }, f.label);
  b.addEventListener("click", () => {
    filters.querySelectorAll("button").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-pressed", String(x === b)); });
    map.setFilter(f.id); showFilterList(f.id);
    if (f.id !== "all") collapseForMap();
  });
  filters.append(b);
}

(async () => {
  try {
    const s = await fetch("/api/session", { method: "POST", headers: HEADERS });
    ready = s.ok; send.disabled = !ready;
    $("status").textContent = ready ? "已连接" : "服务暂不可用";
    const res = await fetch("/api/places", { headers: HEADERS });
    allPlaces = (await res.json()).places || [];
  } catch { $("status").textContent = "服务暂不可用"; }
  map.init(allPlaces);
  // Use location silently only when already granted; otherwise ask on 带我去.
  try { if ((await navigator.permissions?.query({ name: "geolocation" }))?.state === "granted") locate({ quiet: true }); } catch { /* unsupported */ }
})();
