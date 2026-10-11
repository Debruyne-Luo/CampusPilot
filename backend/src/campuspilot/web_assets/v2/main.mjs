// CampusPilot v2 entry: chat (SSE with fallback) + map, wired with ES modules.
import { ask } from "./sse.mjs";
import { initialPlan, reducePlan } from "./plan-state.mjs";
import { createChecklistStore, sessionId } from "./checklist-store.mjs";
import { FILTERS, hasPosition } from "./places.mjs";
import { h } from "./dom.mjs";
import { answerCards, planCard } from "./render.mjs";
import { cardsIn, stepIn, tick } from "./motion.mjs";
import { createMap } from "./map.mjs";

const $ = (id) => document.getElementById(id);
const thread = $("thread"), form = $("chat-form"), input = $("question"), send = $("send");
const store = createChecklistStore(localStorage, sessionId(sessionStorage));
const HEADERS = { "Content-Type": "application/json", "X-CampusPilot-Request": "1" };
let busy = false, ready = false, allPlaces = [];

window.element = (tag, text, className) => h(tag, { class: className }, text ?? ""); // for guidance.js

const map = createMap({
  frame: $("map-frame"), fallback: $("map-fallback"),
  status: (text) => { $("map-status").textContent = text; $("map-status").hidden = !text; },
  onSelect: (place) => highlight(place),
});

function highlight(place) {
  map.focus(place);
  document.querySelectorAll(".chip[data-place-id]").forEach((c) => c.classList.toggle("active", c.dataset.placeId === place.place_id));
  const card = $("place-card");
  card.replaceChildren(...[h("strong", {}, place.name),
    h("span", {}, place.campus || ""),
    hasPosition(place) ? h("span", {}, "建筑参考点 · 入口以现场为准") : h("span", { class: "warn" }, "位置待核实")]);
  card.hidden = false;
}

async function go(place) {
  highlight(place);
  const note = $("route-note");
  note.hidden = false; note.textContent = "正在获取你的位置（只在本机使用）…";
  const r = await map.route(place);
  if (r.status === "success") {
    note.textContent = `步行约 ${Math.max(1, Math.round(r.time / 60))} 分钟 · ${Math.round(r.distance)} 米`;
    const start = h("button", { type: "button", class: "chip go" }, "开始步行引导");
    start.addEventListener("click", () => window.Guidance?.start({
      requestId: map.routeId,
      route: { geometry: r.geometry, stepEnds: r.step_ends, distance: r.distance, time: r.time, steps: r.steps },
    }));
    note.append(" ", start);
  } else note.textContent = r.message || "暂未取得步行路线";
}

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
    const cards = answerCards(result.body, { store, onFocus: highlight, onGo: go });
    thread.append(...cards); cardsIn(cards);
    const first = (result.body.places || []).find((p) => p.position);
    if (first) highlight(first);
  }
  busy = false; send.disabled = false; $("send-label").textContent = "发送"; input.focus();
}

form.addEventListener("submit", (e) => { e.preventDefault(); const t = input.value; input.value = ""; submit(t); });
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll("[data-question]").forEach((b) => b.addEventListener("click", () => submit(b.dataset.question)));
$("new-chat").addEventListener("click", async () => { await fetch("/api/session", { method: "POST", headers: HEADERS }); location.reload(); });

const filters = $("filters");
for (const f of FILTERS) {
  const b = h("button", { type: "button", class: `chip ${f.id === "all" ? "active" : ""}`, "aria-pressed": f.id === "all" ? "true" : "false" }, f.label);
  b.addEventListener("click", () => {
    filters.querySelectorAll("button").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-pressed", String(x === b)); });
    map.setFilter(f.id);
  });
  filters.append(b);
}
$("sheet-handle").addEventListener("click", () => document.body.classList.toggle("sheet-collapsed"));

(async () => {
  try {
    const s = await fetch("/api/session", { method: "POST", headers: HEADERS });
    ready = s.ok; send.disabled = !ready;
    $("status").textContent = ready ? "已连接" : "服务暂不可用";
    const res = await fetch("/api/places", { headers: HEADERS });
    allPlaces = (await res.json()).places || [];
    $("unlocated").textContent = `${allPlaces.filter((p) => !p.position).length} 个地点位置待核实`;
  } catch { $("status").textContent = "服务暂不可用"; }
  map.init(allPlaces);
})();
