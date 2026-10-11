import test from "node:test";
import assert from "node:assert/strict";
const base = "../backend/src/campuspilot/web_assets/v2/";
const { parseSSE, ask } = await import(base + "sse.mjs");
const { initialPlan, reducePlan } = await import(base + "plan-state.mjs");
const { createChecklistStore, sessionId } = await import(base + "checklist-store.mjs");
const { FILTERS, matchesFilter, hasPosition, projector } = await import(base + "places.mjs");

const memory = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };
const sseText = (events) => events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");

test("parseSSE splits complete events and keeps the partial tail", () => {
  const { events, rest } = parseSSE('event: plan\ndata: {"steps":[]}\n\nevent: final\ndata: {"a"');
  assert.deepEqual(events, [{ event: "plan", data: { steps: [] } }]);
  assert.equal(rest, 'event: final\ndata: {"a"');
  assert.deepEqual(parseSSE("event: x\ndata: not-json\n\n").events, []);
  assert.deepEqual(parseSSE('data: {"k":1}\r\n\r\n').events, [{ event: "message", data: { k: 1 } }]);
});

test("plan reducer tracks understanding, plan, tools, composing and final", () => {
  let s = initialPlan();
  const feed = [
    ["understanding", { intent: "办事", slots: { service: "校园卡补办" } }],
    ["plan", { steps: [{ tool: "search_service", label: "查找办事事项" }, { tool: "make_checklist", label: "生成办理清单" }] }],
    ["tool_start", { tool: "search_service", label: "查找办事事项" }],
    ["tool_end", { tool: "search_service", label: "查找办事事项", status: "success" }],
    ["tool_start", { tool: "make_checklist", label: "生成办理清单" }],
  ];
  for (const [event, data] of feed) s = reducePlan(s, { event, data });
  assert.deepEqual(s.steps.map((x) => [x.key, x.status]), [["understanding", "done"], ["tool:search_service", "done"], ["tool:make_checklist", "running"]]);
  assert.equal(s.steps[0].meta, "办事 · 校园卡补办");
  s = reducePlan(s, { event: "composing", data: {} });
  assert.equal(s.steps.find((x) => x.key === "tool:make_checklist").status, "done");
  s = reducePlan(reducePlan(s, { event: "answer_delta", data: { text: "先挂失" } }), { event: "answer_delta", data: { text: "再补卡" } });
  assert.equal(s.answer, "先挂失再补卡");
  s = reducePlan(s, { event: "final", data: {} });
  assert.ok(s.done && s.steps.every((x) => x.status === "done"));
  const empty = reducePlan(initialPlan(), { event: "tool_end", data: { tool: "search_service", label: "查", status: "empty" } });
  assert.equal(empty.steps[0].status, "empty");
  assert.equal(reducePlan(s, { event: "unknown", data: {} }), s);
});

test("checklist store persists per session and survives bad storage", () => {
  const storage = memory();
  const a = createChecklistStore(storage, "s1"), b = createChecklistStore(storage, "s2");
  assert.equal(a.toggle("svc", "material-1"), true);
  assert.ok(a.isDone("svc", "material-1") && !b.isDone("svc", "material-1"));
  assert.equal(createChecklistStore(storage, "s1").count("svc", ["material-1", "step-2"]), 1);
  assert.equal(a.toggle("svc", "material-1"), false);
  storage.setItem("campuspilot:checklist:s3", "{broken");
  assert.equal(createChecklistStore(storage, "s3").isDone("svc", "x"), false);
  const sid = sessionId(storage); assert.equal(sessionId(storage), sid);
  const full = { getItem: () => null, setItem: () => { throw new Error("quota"); }, removeItem() {} };
  assert.doesNotThrow(() => createChecklistStore(full, "q").toggle("svc", "a"));
});

test("map filters and schematic projection", () => {
  const places = [
    { place_id: "a", category: "dining", tags: ["food"], position: { coordinate_system: "GCJ02", longitude: 104.14, latitude: 30.67 } },
    { place_id: "b", category: "service", tags: ["parcel"], position: { coordinate_system: "GCJ02", longitude: 104.15, latitude: 30.68 } },
    { place_id: "c", category: "library", tags: [], position: null },
  ];
  assert.deepEqual(FILTERS.map((f) => f.id), ["all", "building", "office", "dining", "parcel", "service"]);
  assert.deepEqual(places.filter((p) => matchesFilter(p, "parcel")).map((p) => p.place_id), ["b"]);
  assert.deepEqual(places.filter((p) => matchesFilter(p, "service")).map((p) => p.place_id), []);
  assert.deepEqual(places.filter((p) => matchesFilter(p, "building")).map((p) => p.place_id), ["c"]);
  assert.equal(hasPosition(places[2]), false);
  const project = projector(places, 1000, 700, 40);
  const pa = project(places[0].position), pb = project(places[1].position);
  assert.ok(pa.x < pb.x && pa.y > pb.y, "east is right, north is up");
  for (const p of [pa, pb]) assert.ok(p.x >= 0 && p.x <= 1000 && p.y >= 0 && p.y <= 700);
  assert.equal(project(null), null);
});

function streamResponse(text) {
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream({ start(c) { c.enqueue(bytes.slice(0, 20)); c.enqueue(bytes.slice(20)); c.close(); } }),
    { status: 200, headers: { "content-type": "text/event-stream" } });
}

test("ask streams events and returns the final body; message only, no position", async () => {
  const sent = [];
  const fetchImpl = async (url, init) => { sent.push([url, JSON.parse(init.body)]); return streamResponse(sseText([["plan", { steps: [] }], ["final", { answer: "ok", result_status: "success" }]])); };
  const seen = [];
  const r = await ask("校园卡丢了", (e) => seen.push(e.event), fetchImpl);
  assert.deepEqual(seen, ["plan", "final"]);
  assert.ok(r.ok && r.streamed && r.body.answer === "ok");
  assert.deepEqual(sent, [["/api/chat/stream", { message: "校园卡丢了" }]]);
});

test("ask falls back to /api/chat when the stream is unavailable", async () => {
  const urls = [];
  const fetchImpl = async (url) => {
    urls.push(url);
    if (url.endsWith("/stream")) return new Response(JSON.stringify({ error_code: "stream_unavailable" }), { status: 404 });
    return new Response(JSON.stringify({ answer: "legacy", result_status: "success" }), { status: 200 });
  };
  const r = await ask("你好", () => {}, fetchImpl);
  assert.deepEqual(urls, ["/api/chat/stream", "/api/chat"]);
  assert.ok(r.ok && !r.streamed && r.body.answer === "legacy");
  const net = await ask("你好", () => {}, async (url) => { if (url.endsWith("/stream")) throw new TypeError("network"); return new Response("{}", { status: 200 }); });
  assert.ok(net.ok && !net.streamed);
});

test("ask surfaces guard errors without falling back", async () => {
  const urls = [];
  const r = await ask("x", () => {}, async (url) => { urls.push(url); return new Response(JSON.stringify({ error_code: "busy", message: "上一条问题正在处理" }), { status: 409 }); });
  assert.deepEqual(urls, ["/api/chat/stream"]);
  assert.equal(r.status, 409); assert.equal(r.body.error_code, "busy");
});

test("guidance.js exposes Guidance on window and renders without classic journey card", async () => {
  const { readFileSync } = await import("node:fs");
  const vm = await import("node:vm");
  const slot = { children: [], replaceChildren() { this.children = []; }, append(...c) { this.children.push(...c); } };
  const el = () => ({ append() {}, setAttribute() {}, addEventListener() {}, classList: { add() {}, toggle() {} } });
  const document = { querySelector: (s) => (s === ".guidance-slot" ? slot : null), getElementById: () => null, addEventListener() {} };
  const window = { addEventListener() {} };
  const ctx = { document, window, navigator: {}, element: el, sendToMap() {}, console };
  ctx.window = Object.assign(window, ctx);
  vm.createContext(ctx);
  vm.runInContext(readFileSync(new URL("../backend/src/campuspilot/web_assets/guidance.js", import.meta.url), "utf8"), ctx);
  assert.equal(typeof ctx.window.Guidance?.start, "function");
  ctx.window.Guidance.start({ requestId: 1, target: { name: "珙桐餐厅" }, route: { geometry: [[104.1, 30.6], [104.101, 30.601]], stepEnds: [1], distance: 150, time: 120, steps: ["向西"] } });
  assert.ok(slot.children.length > 0);
  ctx.window.Guidance.stop();
});
