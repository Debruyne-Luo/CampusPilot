import test from "node:test";
import assert from "node:assert/strict";
import { createHandlingStore, taskSnapshot, preparationLabel, legacyTicks, sourceUrl, HANDLING_KEY } from "../backend/src/campuspilot/web_assets/v2/handling-store.mjs";

const memory = () => { const data = new Map(); return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v) }; };
// Explicitly synthetic fixtures; not university records or verified map destinations.
const fixture = () => ({
  answer: "SYNTHETIC private conversation must not be stored", result_status: "limited",
  checklist: { status: "success", service_id: "synthetic:service:a", items: [
    { id: "material-1", kind: "material", text: "合成材料 A" },
    { id: "input-2", kind: "input", text: "合成信息 B" },
    { id: "limit-3", kind: "limit", text: "合成限制" },
    { id: "step-4", kind: "step", text: "合成步骤" },
  ] },
  services: [{ service_id: "synthetic:service:a", name: "合成测试事务", audience: "测试对象",
    information_level: "procedure",
    required_materials: ["合成材料 A"], required_inputs: ["合成信息 B"], entry_points: ["合成入口"],
    limits: ["合成限制"], fees: ["合成费用"], availability: [{ condition: "合成条件", wait: "合成等待" }],
    source_links: [{ title: "合成来源", url: "https://example.org/synthetic" }, { title: "不安全链接", url: "javascript:alert(1)" }],
    steps: [
      { mode: "online", instruction: "合成线上方式", condition: "合成适用条件", place_ids: [] },
      { mode: "in_person", instruction: "合成线下方式", condition: null, place_ids: ["synthetic:place:a"] },
    ],
  }],
  places: [
    { place_id: "synthetic:place:a", name: "合成地点 A", position: null, unrelated: "do not copy" },
    { place_id: "synthetic:place:unrelated", name: "不相关地点", position: null },
  ],
  citations: [{ title: "其他回答来源", url: "https://example.org/unrelated" }],
});
const task = (now = 1) => taskSnapshot(fixture(), [], now);

test("snapshot preserves conditions and provenance, excludes conversation and unrelated places", () => {
  const saved = task();
  assert.equal(saved.items.length, 2);
  assert.deepEqual(saved.steps.map((s) => s.mode), ["online", "in_person"]);
  assert.equal(saved.steps[0].condition, "合成适用条件");
  assert.deepEqual(saved.notes, ["合成限制", "费用：合成费用", "合成条件：合成等待"]);
  assert.equal(saved.sources.length, 1);
  assert.equal(saved.sources[0].url, "https://example.org/synthetic");
  assert.deepEqual(saved.places, [{ place_id: "synthetic:place:a", name: "合成地点 A", position: null }]);
  assert.doesNotMatch(JSON.stringify(saved), /private conversation|unrelated/);
});

test("academic year and service source limitations survive independently of the conversation", () => {
  const body = fixture(); body.services[0].academic_year = "2098-2099";
  body.services[0].notes = ["SYNTHETIC source limitation"];
  const snapshot = taskSnapshot(body);
  assert.match(snapshot.audience, /2098-2099 学年/);
  assert.deepEqual(snapshot.sourceNotes, ["SYNTHETIC source limitation"]);
});

test("only a matching structured checklist is saveable; limited model answers remain saveable", () => {
  assert.ok(taskSnapshot(fixture()));
  assert.equal(taskSnapshot({ answer: "plain text" }), null);
  const body = fixture(); body.checklist.status = "empty";
  assert.equal(taskSnapshot(body), null);
  body.checklist.status = "success"; body.checklist.service_id = "different";
  assert.equal(taskSnapshot(body), null);
});

test("the first matched procedure can be saved without asking the model for a checklist", () => {
  const body = fixture(); delete body.checklist;
  const saved = taskSnapshot(body, [], 42);
  assert.ok(saved);
  assert.equal(saved.service_id, body.services[0].service_id);
  assert.deepEqual(saved.items.map(i => [i.id, i.kind, i.text]), [
    ["material-1", "material", "合成材料 A"], ["input-2", "input", "合成信息 B"],
  ]);
  assert.deepEqual(saved.steps, task(42).steps);
  assert.deepEqual(saved.notes, task(42).notes);
  assert.deepEqual(saved.sources, task(42).sources);
  assert.doesNotMatch(JSON.stringify(saved), /private conversation/);
});

test("first-answer saving rejects ambiguous, non-procedure and unsuccessful responses", () => {
  for (const result_status of [undefined, "needs_clarification", "empty", "error", "refused"]) {
    const body = fixture(); delete body.checklist; body.result_status = result_status;
    assert.equal(taskSnapshot(body), null);
  }
  for (const level of [undefined, "directory", "guide"]) {
    const body = fixture(); delete body.checklist; body.services[0].information_level = level;
    assert.equal(taskSnapshot(body), null);
  }
  const body = fixture(); delete body.checklist;
  body.services.push({ ...body.services[0], service_id: "synthetic:service:b" });
  assert.equal(taskSnapshot(body), null);
});

test("public place fallback is limited to service-linked ids and retains coordinate provenance", () => {
  const body = fixture(); body.places = [];
  const position = { longitude: 0, latitude: 0, coordinate_system: "GCJ02", source_kind: "map_provider", source_url: "https://example.org/synthetic-map", verification_status: "needs_review", note: "synthetic", personal: "never copy" };
  const snapshot = taskSnapshot(body, [{ place_id: "synthetic:place:a", name: "合成地点", position }]);
  assert.equal(snapshot.places[0].position.source_url, position.source_url);
  assert.equal(snapshot.places[0].position.verification_status, "needs_review");
  assert.equal(snapshot.places[0].position.personal, undefined);
});

test("unknown preparation is never represented as 0/0 or ready, and a steps-only task is saveable", () => {
  const body = fixture(); body.services[0].required_materials = null;
  const partial = taskSnapshot(body); partial.checked = partial.items.map((i) => i.id);
  assert.equal(preparationLabel(partial), "已准备 2/2");
  body.checklist.items = body.checklist.items.filter((i) => i.kind === "step");
  body.services[0].required_inputs = null;
  const unknown = taskSnapshot(body);
  assert.ok(unknown);
  assert.equal(preparationLabel(unknown), "准备要求待核实");
  body.services[0].required_materials = []; body.services[0].required_inputs = [];
  assert.equal(preparationLabel(taskSnapshot(body)), "无须准备材料或信息");
});

test("tasks survive store recreation; duplicates preserve original content and progress", () => {
  const storage = memory(), first = createHandlingStore(storage);
  first.add(task()); first.toggle(task().service_id, "material-1");
  const reloaded = createHandlingStore(storage);
  assert.equal(preparationLabel(reloaded.list()[0]), "已准备 1/2");
  const changed = task(10); changed.title = "后来不同的答案"; changed.items.reverse();
  assert.equal(reloaded.add(changed).existing, true);
  assert.equal(reloaded.list().length, 1);
  assert.equal(reloaded.list()[0].title, "合成测试事务");
  assert.deepEqual(reloaded.list()[0].checked, ["material-1"]);
  assert.equal(reloaded.list()[0].savedAt, 1);
});

test("checking all preparation does not remove a task; completion and undo retain the snapshot", () => {
  const store = createHandlingStore(memory()); store.add(task());
  for (const item of task().items) assert.equal(store.toggle(task().service_id, item.id).ok, true);
  assert.equal(preparationLabel(store.list()[0]), "准备齐了");
  assert.equal(store.list().length, 1);
  const removed = store.remove(task().service_id);
  assert.equal(store.list().length, 0);
  assert.equal(store.restore(removed.task).ok, true);
  assert.equal(preparationLabel(store.list()[0]), "准备齐了");
  store.remove(task().service_id); store.add(task(20));
  assert.equal(store.restore(removed.task).existing, true);
  assert.deepEqual(store.list()[0].checked, []);
});

test("failed writes never report success or change stored task progress/removal", () => {
  const storage = memory(), store = createHandlingStore(storage); store.add(task());
  storage.setItem = () => { throw new Error("quota"); };
  assert.equal(store.toggle(task().service_id, "material-1").ok, false);
  assert.deepEqual(store.list()[0].checked, []);
  assert.equal(store.remove(task().service_id).ok, false);
  assert.equal(store.list().length, 1);
  const other = task(); other.service_id = "synthetic:service:b";
  assert.equal(store.add(other).ok, false);
  assert.equal(store.list().length, 1);
});

test("blocked storage and corrupt records cannot crash chat; future versions are not overwritten", () => {
  const blocked = createHandlingStore({ getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } });
  assert.deepEqual(blocked.list(), []); assert.equal(blocked.add(task()).ok, false);
  const storage = memory(); storage.setItem(HANDLING_KEY, "{bad");
  const store = createHandlingStore(storage);
  assert.deepEqual(store.list(), []); assert.equal(store.add(task()).ok, true);
  storage.setItem(HANDLING_KEY, JSON.stringify({ version: 1, tasks: [null, {}, { ...task(), steps: [null] }, task()] }));
  assert.equal(store.list().length, 1);
  const future = JSON.stringify({ version: 2, tasks: [task()] }); storage.setItem(HANDLING_KEY, future);
  assert.equal(store.add(task()).ok, false); assert.equal(storage.getItem(HANDLING_KEY), future);
});

test("legacy ticks are imported only on explicit add and filter out limitations", () => {
  const local = memory(), session = memory(); session.setItem("campuspilot:sid", "old-session");
  local.setItem("campuspilot:checklist:old-session", JSON.stringify({ [task().service_id]: ["material-1", "limit-3", "unknown"] }));
  const store = createHandlingStore(local); assert.equal(store.list().length, 0);
  const saved = task(); saved.checked = legacyTicks(saved, local, session); store.add(saved);
  assert.deepEqual(store.list()[0].checked, ["material-1"]);
  assert.deepEqual(legacyTicks(saved, local, memory()), []);
  assert.equal(createHandlingStore(local).list().length, 1);
});

test("one-time browser notice persists; listeners run only for successful mutations", () => {
  const storage = memory(), store = createHandlingStore(storage); let changes = 0;
  store.subscribe(() => changes++);
  assert.equal(store.notice(), true); assert.equal(createHandlingStore(storage).notice(), false);
  store.add(task()); store.add(task());
  assert.equal(changes, 1);
  assert.equal(store.toggle(task().service_id, "limit-3").ok, false);
  assert.equal(changes, 1);
  store.refresh(); assert.equal(changes, 2);
  assert.equal(sourceUrl("javascript:alert(1)"), null);
  assert.equal(sourceUrl("https://user:password@example.org"), null);
});

test("only explicitly classified procedures create new tasks; legacy and guides keep their facts", () => {
  for (const level of [undefined, "directory", "guide"]) {
    const body = fixture(); body.services[0].information_level = level;
    assert.equal(taskSnapshot(body), null);
  }
  const body = fixture(); body.checklist.checklist_available = false;
  assert.equal(taskSnapshot(body), null);
});

test("old v1 saved snapshots remain byte-for-byte readable with all progress", () => {
  const storage = memory(), old = task(); old.checked = ["material-1"];
  delete old.information_level; delete old.sourceNotes;
  const serialized = JSON.stringify({ version: 1, noticed: true, tasks: [old] });
  storage.setItem(HANDLING_KEY, serialized);
  const store = createHandlingStore(storage);
  assert.deepEqual(store.list(), [old]);
  assert.equal(storage.getItem(HANDLING_KEY), serialized);
  assert.deepEqual(createHandlingStore(storage).get(old.service_id).checked, ["material-1"]);
  assert.equal(store.toggle(old.service_id, "input-2").ok, true);
  assert.deepEqual(store.get(old.service_id).checked, ["material-1", "input-2"]);
});
