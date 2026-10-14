// 理小龙 CDUTdino v2 entry: chat (SSE with fallback) + map, wired with ES modules.
import { ask } from "./sse.mjs";
import { createAttachmentComposer } from "./attachments.mjs";
import { createPlaceSearch, navigationTarget } from "./place-search.mjs";
import { initialPlan, reducePlan } from "./plan-state.mjs";
import { createHandlingStore, HANDLING_KEY, legacyTicks } from "./handling-store.mjs";
import { createHandlingUI } from "./handling-ui.mjs";
import { FILTERS, filterList, hasPosition } from "./places.mjs";
import { h } from "./dom.mjs";
import { answerCards, planCard } from "./render.mjs";
import { cardsIn, stepIn, tick } from "./motion.mjs";
import { createMap } from "./map.mjs";
import { distanceMeters, formatDistance, toGcj02 } from "./geo.mjs";
import { initialOrigin, reduceOrigin, routeOrigin } from "./origin.mjs";
import { dragOffset, initialSheet, reduceSheet, releaseVelocity, sheetOffset, visibleHeight } from "./sheet.mjs";
import { createHeadingTracker, needsPermission, viewRotation } from "./heading.mjs";

const $ = (id) => document.getElementById(id);
const thread = $("thread"), form = $("chat-form"), input = $("question"), send = $("send");
// Access storage lazily: a denied browser storage getter must not prevent chat boot.
const local = { getItem: (k) => window.localStorage.getItem(k), setItem: (k, v) => window.localStorage.setItem(k, v) };
const handlingStore = createHandlingStore(local);
addEventListener("storage", (e) => { if (e.key === HANDLING_KEY || e.key === null) handlingStore.refresh(); });
const HEADERS = { "Content-Type": "application/json", "X-CampusPilot-Request": "1" };
let busy = false, ready = false, allPlaces = [];
let conversationRevision = 0, chatController = null;
const placeSearch = createPlaceSearch();
let attachments;
attachments = createAttachmentComposer({ form, input, canEdit: () => ready && !busy,
  onChange: () => { send.disabled = busy || !ready || !attachments?.ready; } });
let origin = initialOrigin(), sheet = initialSheet(), pendingTarget = null, current = null, guiding = false;
const placeCards = new Set();

window.element = (tag, text, className) => h(tag, { class: className }, text ?? ""); // for guidance.js

const map = createMap({
  frame: $("map-frame"), fallback: $("map-fallback"),
  status: (text) => { $("map-status").textContent = text; $("map-status").hidden = !text; },
  onSelect: (place) => highlight(place),
  onOrigin: (position, name) => setOrigin({ type: "map", position, label: name }),
  onPoi: (poi) => showCard({ name: poi.name, position: poi.position, poi: true }),
  onArrive: () => { if (guideTarget) showArrival(guideTarget); },
  onGuide: (kind) => { document.body.dataset.guide = kind; },
});

// ---- origin ---------------------------------------------------------------------------
function setOrigin(action) {
  const before = origin; origin = reduceOrigin(origin, action);
  if (origin === before) return;
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
  const bottom = mobile() ? sheetVisible() : 0, top = 60;
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
    h("button", { type: "button", class: "chip", onclick: useGps }, "我的位置"),
    h("button", { type: "button", class: "chip", onclick: pickOnMap }, "在地图上点选"), select)];
}

// ---- place card on the map (our places + AMap POIs) -----------------------------------
function pinIcon() {
  const NS = "http://www.w3.org/2000/svg", el = (t, a) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; };
  const svg = el("svg", { viewBox: "0 0 24 24", width: 18, height: 18, "aria-hidden": "true" });
  svg.append(el("circle", { cx: 12, cy: 12, r: 3.5, fill: "currentColor" }), el("circle", { cx: 12, cy: 12, r: 8, fill: "none", stroke: "currentColor", "stroke-width": 2 }));
  return svg;
}
function showCard(target) {
  current = target; $("place-card").classList.remove("arrival");
  const card = $("place-card"), from = routeOrigin(origin);
  const d = from && target.position ? distanceMeters(from, target.position) : null;
  const asOrigin = () => setOrigin(target.place ? { type: "place", place: target.place } : { type: "map", position: target.position, label: target.name });
  const fromBtn = h("button", { type: "button", class: "icon-button", "aria-label": "设为起点", title: "设为起点", onclick: asOrigin }, pinIcon());
  card.replaceChildren(
    h("div", { class: "card-head" },
      h("strong", {}, target.name),
      d != null ? h("small", {}, formatDistance(d)) : null,
      h("button", { type: "button", class: "card-close", "aria-label": "关闭", onclick: () => { card.hidden = true; current = null; } }, "×")),
    target.position ? h("div", { class: "card-actions" },
      h("button", { type: "button", class: "chip go", onclick: () => go(target) }, "带我去"), fromBtn) : null);
  card.hidden = false;
}
/** Arrival: drop stale cards/notes and show only 已到达 + name + 完成 (理小龙 idles). */
function showArrival(target) {
  document.body.classList.add("arrived"); current = null; note();
  const card = $("place-card");
  card.classList.add("arrival");
  card.replaceChildren(
    h("div", { class: "card-head" }, h("small", { class: "arrived-label" }, "已到达"), h("strong", {}, target.name)),
    h("div", { class: "card-actions" }, h("button", { type: "button", class: "chip go", onclick: finishArrival }, "完成")));
  card.hidden = false;
}
function finishArrival() {
  const card = $("place-card"); card.hidden = true; card.classList.remove("arrival");
  window.Guidance?.stop(); map.dinoStop(); guideTarget = null; document.body.classList.remove("arrived");
}
function highlight(place) {
  map.focus(place);
  document.querySelectorAll(".place-row").forEach((c) => c.classList.toggle("active", c.dataset.placeId === place.place_id));
  showCard({ name: place.name, position: hasPosition(place) ? place.position : null, place });
}

new MutationObserver(() => document.body.classList.toggle("card-open", !$("place-card").hidden)).observe($("place-card"), { attributes: true, attributeFilter: ["hidden"] });

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
    if (!(await locate())) note(...originChooser(`从哪出发去 ${target.name}？`));
    return; // a successful fix resumes the pending target through setOrigin
  }
  pendingTarget = null;
  note(`正在规划：${origin.label} → ${target.name}…`);
  const dest = target.place ? navigationTarget(target.place) : { position: toGcj02(target.position) };
  const r = await map.route(dest, routeOrigin(origin));
  const change = () => h("button", { type: "button", class: "chip ghost", onclick: () => note(...originChooser("换个起点：")) }, "换起点");
  if (r.status !== "success") { note(h("span", {}, r.message || "暂未取得步行路线，可换个起点再试。"), change()); return; }
  note(h("b", {}, `${origin.label} → ${target.name}`),
    h("span", {}, ` 步行约 ${Math.max(1, Math.round(r.time / 60))} 分钟 · ${Math.round(r.distance)} 米 `),
    h("button", { type: "button", class: "chip go", onclick: () => startGuidance(target, r) }, "开始步行引导"), change());
}
// ?demo=1 makes 理小龙 walk the route by itself; ?speed= metres per second (default 9).
const params = new URLSearchParams(location.search);
// Without continuous location (desktop, no permission) the guide walks in demo mode.
let demo = params.get("demo") === "1" || !navigator.geolocation || !window.isSecureContext, guideTarget = null;
const demoSpeed = Number(params.get("speed")) || undefined;
function setDemo(on) {
  demo = on; document.body.classList.toggle("demo", on); $("dino-demo").setAttribute("aria-pressed", String(on)); $("dino-demo").classList.toggle("active", on);
  map.dinoMode(on, demoSpeed);
}
$("dino-demo").addEventListener("click", () => setDemo(!demo));
function startGuidance(target, r) {
  enableHeading(); // inside the click: iOS asks for motion permission only on a user gesture
  guideTarget = target; document.body.classList.remove("arrived");
  window.Guidance?.start({
    requestId: map.routeId, target: { name: target.name },
    replan: (gps) => { setOrigin({ type: "use-gps" }); if (gps) setOrigin({ type: "gps", position: gps }); go(target); },
    route: { geometry: r.geometry, stepEnds: r.step_ends, distance: r.distance, time: r.time, steps: r.steps },
  });
  setDemo(demo); map.dino(demo, demoSpeed, params.get("guide") || undefined);
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
  $("heading-toggle").hidden = !on; $("dino-demo").hidden = !on;
  if (!on) { map.dinoStop(); guideTarget = null; document.body.classList.remove("arrived"); delete document.body.dataset.guide; }
  if (on) { note(); $("place-card").hidden = true; } else { stopHeading(); if ($("place-card").classList.contains("arrival")) { $("place-card").hidden = true; $("place-card").classList.remove("arrival"); } }
}

// ---- compass heading ------------------------------------------------------------------
const tracker = createHeadingTracker();
let headingUp = false, headingOn = false, raf = 0, courseWatch = null;
const screenAngle = () => screen.orientation?.angle ?? window.orientation ?? 0;
function onOrientation(e) { tracker.compass(e, screenAngle()); schedule(); }
function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (tracker.value != null) map.heading({ ...viewRotation(tracker.value, headingUp), value: tracker.value }); }); }
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
  const inThread = e.target.closest(".thread, .handling-scroll"), onControl = e.target.closest("textarea,select,input,button,a,label,summary");
  if ((onControl && onControl.id !== "sheet-handle") || (inThread && inThread.scrollTop > 0 && sheet.state === "expanded")) return;
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

const handling = createHandlingUI({
  store: handlingStore, entry: $("handling-entry"), panel: $("handling-panel"), toast: $("handling-toast"), thread, form,
  getPlaces: () => allPlaces,
  getLegacyTicks: (task) => legacyTicks(task, local, { getItem: (k) => window.sessionStorage.getItem(k) }),
  onExpand: () => applySheet({ type: "focus-input" }),
  onFocus: (p) => { map.reveal([p.place_id]); highlight(p); collapseForMap(); },
  onGo: go,
});

// ---- chat -----------------------------------------------------------------------------
function bubble(text, images = []) {
  const b = h("div", { class: "msg-user" }, text,
    images.length ? h("div", { class: "message-images" }, images.map((p) => h("img", { src: p.url, alt: p.name }))) : null);
  thread.append(b); return b;
}
function pickDestination() {
  if (!map.pickDestination()) { note("地图尚未加载，可稍后重试。地点搜索不需要等待地图。"); return; }
  collapseForMap(); note("点击地图上的目的地，地图文字地点也可直接点击。");
}
function scrollEnd() { if (!handling.active) thread.scrollTo({ top: thread.scrollHeight, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }

async function submit(text) {
  if (busy || !ready || (!text.trim() && !attachments.count)) return;
  if (!attachments.ready) { attachments.report("请等待图片上传完成，或重试／移除失败的图片。"); return; }
  const ticket = conversationRevision;
  const attachmentIds = attachments.ids(), images = attachments.previews();
  chatController = new AbortController();
  busy = true; send.disabled = true; $("send-label").textContent = "思考中";
  $("new-chat").disabled = true; attachments.refresh();
  $("empty")?.remove();
  bubble(text, images); scrollEnd();
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
    if (ticket !== conversationRevision) return;
    state = reducePlan(state, e);
    if (e.event === "answer_delta") { if (!live.isConnected) thread.append(live); live.textContent = state.answer; }
    else paint();
    scrollEnd();
  }, fetch, { attachmentIds, signal: chatController.signal });
  if (ticket !== conversationRevision) return;
  live.remove();
  if (!result.ok) {
    thread.append(h("div", { class: "card error", role: "alert" }, result.body?.message || "暂时无法回答，请稍后再试。"));
  } else {
    if (!result.streamed) planHost.remove();
    else { state = reducePlan(state, { event: "final", data: {} }); paint(); }
    attachments.sent();
    const cards = answerCards(result.body, { checklistPreview: handling.preview, onFocus: highlight, onGo: go, onMapPick: pickDestination, onFrom: (p) => setOrigin({ type: "place", place: p }), origin: routeOrigin(origin) });
    for (const c of cards) if (c.update) placeCards.add(c);
    thread.append(...cards); cardsIn(cards);
    map.addPlaces(result.body.places || []);
    map.reveal((result.body.places || []).map((p) => p.place_id));
  }
  busy = false; chatController = null; $("new-chat").disabled = false; $("send-label").textContent = "发送"; attachments.refresh();
  if (!mobile() && !handling.active) input.focus({ preventScroll: true });
}

form.addEventListener("submit", (e) => { e.preventDefault(); if (busy || !ready || !attachments.ready || (!input.value.trim() && !attachments.count)) return; const t = input.value; input.value = ""; submit(t); });
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll("[data-question]").forEach((b) => b.addEventListener("click", () => submit(b.dataset.question)));
$("new-chat").addEventListener("click", async () => {
  if (busy) return;
  $("new-chat").disabled = true;
  try {
    const response = await fetch("/api/session/reset", { method: "POST", headers: HEADERS, credentials: "same-origin" });
    if (!response.ok) throw new Error("reset failed");
    conversationRevision++; chatController?.abort(); placeSearch.cancel(); attachments.clear(); location.reload();
  } catch { $("status").textContent = "新对话未能创建，请重试"; $("new-chat").disabled = false; }
});
$("locate").addEventListener("click", async () => {
  if (await locate()) { const p = routeOrigin(origin); if (p) map.centerOn(toGcj02(p)); }
  else note(...originChooser("无法定位，可这样选起点："));
});

// ---- one search bar: focus shows category shortcuts + results; hidden otherwise -------
const searchBox = $("map-search"), results = $("search-results"), panel = $("search-panel"), filters = $("filters"), clearBtn = $("filter-clear");
let searchTimer = 0, searchToken = 0, filterId = "all";
function openPanel() { panel.hidden = false; }
function closeSearch() { clearTimeout(searchTimer); searchToken++; placeSearch.cancel(); panel.hidden = true; results.replaceChildren(); }
function resultRow(label, sub, pick) {
  return h("li", { role: "option" }, h("button", { type: "button", onclick: () => { closeSearch(); searchBox.value = ""; searchBox.blur(); pick(); } }, h("b", {}, label), sub ? h("small", {}, sub) : null));
}
const pickPlace = (p) => { map.reveal([p.place_id]); highlight(p); collapseForMap(); };
async function runSearch(q) {
  const token = ++searchToken;
  results.replaceChildren(h("li", { class: "hint" }, "正在搜索…")); openPanel();
  const found = await placeSearch.search(q);
  if (token !== searchToken || !found) return;
  const places = found.places || [];
  map.addPlaces(places);
  results.replaceChildren(...places.map((p) => resultRow(p.name, p.source_provider === "amap" ? `高德地图${p.address ? ` · ${p.address}` : ""}` : p.address_detail || null, () => pickPlace(p))));
  if (found.message) results.append(h("li", { class: "hint" }, found.message));
  if (!places.length) results.append(resultRow("在地图上选择地点", "地图文字地点也可直接点击", pickDestination));
}
function setFilter(id) {
  filterId = id; map.setFilter(id);
  filters.querySelectorAll("button").forEach((x) => { x.classList.toggle("active", x.dataset.id === id); x.setAttribute("aria-pressed", String(x.dataset.id === id)); });
  const f = FILTERS.find((x) => x.id === id);
  clearBtn.hidden = id === "all"; clearBtn.textContent = id === "all" ? "" : `${f.label} ×`;
  clearBtn.setAttribute("aria-label", `清除分类：${f.label}`);
  results.replaceChildren(...filterList(allPlaces, id).map((p) => resultRow(p.name, null, () => pickPlace(p))));
}
for (const f of FILTERS) {
  const b = h("button", { type: "button", class: `chip ${f.id === "all" ? "active" : ""}`, "data-id": f.id, "aria-pressed": f.id === "all" ? "true" : "false" }, f.label);
  b.addEventListener("click", () => { searchBox.value = ""; searchToken++; setFilter(f.id); if (f.id === "all") closeSearch(); });
  filters.append(b);
}
clearBtn.addEventListener("click", () => { setFilter("all"); closeSearch(); });
searchBox.addEventListener("focus", () => { openPanel(); if (!searchBox.value.trim()) setFilter(filterId); });
searchBox.addEventListener("input", () => { clearTimeout(searchTimer); searchToken++; placeSearch.cancel(); const q = searchBox.value.trim(); if (!q) { setFilter(filterId); return; } searchTimer = setTimeout(() => runSearch(q), 250); });
searchBox.addEventListener("keydown", (e) => { if (e.key === "Escape") { searchBox.value = ""; closeSearch(); searchBox.blur(); } if (e.key === "Enter") { e.preventDefault(); results.querySelector("button")?.click(); } });
document.addEventListener("pointerdown", (e) => { if (!e.target.closest(".map-search")) closeSearch(); });

(async () => {
  try {
    const s = await fetch("/api/session", { method: "POST", headers: HEADERS });
    const sessionConfig = await s.json();
    attachments.setEnabled(sessionConfig.images_enabled === true);
    ready = s.ok; attachments.refresh();
    $("status").textContent = ready ? "已连接" : "服务暂不可用";
    const res = await fetch("/api/places", { headers: HEADERS });
    allPlaces = (await res.json()).places || [];
  } catch { $("status").textContent = "服务暂不可用"; }
  map.init(allPlaces);
  // Use location silently only when already granted; otherwise ask on 带我去.
  try { if ((await navigator.permissions?.query({ name: "geolocation" }))?.state === "granted") locate({ quiet: true }); } catch { /* unsupported */ }
})();
