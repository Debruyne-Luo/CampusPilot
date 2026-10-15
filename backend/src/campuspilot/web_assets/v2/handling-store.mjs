// Saved public service snapshots, independent of chat/session ids. No personal input.
export const HANDLING_KEY = "campuspilot:handling:v1";
const strings = (xs) => Array.isArray(xs) ? xs.filter((x) => typeof x === "string" && x.trim()) : [];
const text = (x) => typeof x === "string" ? x : "";
export function sourceUrl(value) {
  try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) && !u.username && !u.password ? u.href : null; }
  catch { return null; }
}

/** Only the structured service matching the checklist can become a saved task. */
export function taskSnapshot(body, places = [], now = Date.now()) {
  const list = body?.checklist;
  if (list?.status !== "success" || !Array.isArray(list.items)) return null;
  const service = body.services?.find((s) => s.service_id === list.service_id);
  if (!service?.name || !service.steps?.length) return null;
  const steps = service.steps.map((s) => ({
    mode: text(s.mode), instruction: text(s.instruction), condition: text(s.condition), place_ids: strings(s.place_ids),
  }));
  const placeIds = new Set(steps.flatMap((s) => s.place_ids));
  const linkedPlaces = new Map();
  for (const p of [...(body.places || []), ...places]) {
    if (!placeIds.has(p.place_id) || linkedPlaces.has(p.place_id)) continue;
    const position = p.position ? Object.fromEntries([
      "longitude", "latitude", "coordinate_system", "source_kind", "source_url", "retrieved_at",
      "verification_status", "confirmed_at", "reviewer", "note",
    ].filter((key) => p.position[key] != null).map((key) => [key, p.position[key]])) : null;
    linkedPlaces.set(p.place_id, { place_id: p.place_id, name: text(p.name), position });
  }
  const seen = new Set();
  const items = list.items.filter((i) => ["material", "input"].includes(i.kind) && i.id && i.text)
    .filter((i) => !seen.has(i.id) && seen.add(i.id))
    .map((i) => ({ id: text(i.id), kind: i.kind, text: text(i.text) }));
  return {
    service_id: list.service_id, title: service.name,
    audience: [text(service.audience), service.academic_year ? `${service.academic_year} 学年` : ""].filter(Boolean).join(" · "),
    savedAt: now, items, checked: [],
    preparationUnknown: service.required_materials == null || service.required_inputs == null,
    steps, entryPoints: strings(service.entry_points),
    notes: [...new Set([
      ...strings(service.limits), ...strings(service.fees).map((f) => `费用：${f}`),
      ...(service.availability || []).map((a) => [a.condition, a.wait].filter(Boolean).join("：")),
    ])],
    sources: (service.source_links || []).filter((s) => sourceUrl(s.url)).map((s) => ({ title: text(s.title) || "官方原文", url: sourceUrl(s.url) })),
    sourceNotes: strings(service.notes),
    places: [...linkedPlaces.values()],
  };
}

export function preparationLabel(task) {
  const total = task.items.length;
  if (!total) return task.preparationUnknown ? "准备要求待核实" : "无须准备材料或信息";
  const count = task.items.filter((i) => task.checked.includes(i.id)).length;
  return count === total && !task.preparationUnknown ? "准备齐了" : `已准备 ${count}/${total}`;
}

function validTask(t) {
  return t && typeof t.service_id === "string" && typeof t.title === "string" && Number.isFinite(t.savedAt)
    && typeof t.preparationUnknown === "boolean" && typeof t.audience === "string"
    && Array.isArray(t.items) && t.items.every((i) => i && typeof i.id === "string" && typeof i.text === "string" && ["material", "input"].includes(i.kind))
    && Array.isArray(t.checked) && t.checked.every((id) => typeof id === "string")
    && Array.isArray(t.steps) && t.steps.every((s) => s && typeof s.instruction === "string" && typeof s.condition === "string" && typeof s.mode === "string" && Array.isArray(s.place_ids))
    && Array.isArray(t.sources) && t.sources.every((s) => s && typeof s.title === "string" && sourceUrl(s.url))
    && (t.sourceNotes == null || Array.isArray(t.sourceNotes) && t.sourceNotes.every((s) => typeof s === "string"))
    && Array.isArray(t.places) && t.places.every((p) => p && typeof p.place_id === "string" && typeof p.name === "string")
    && Array.isArray(t.notes) && t.notes.every((n) => typeof n === "string")
    && Array.isArray(t.entryPoints) && t.entryPoints.every((n) => typeof n === "string");
}

export function createHandlingStore(storage) {
  const listeners = new Set();
  function read() {
    let raw;
    try { raw = JSON.parse(storage.getItem(HANDLING_KEY) || "null"); }
    catch (e) { if (!(e instanceof SyntaxError)) throw e; }
    if (raw?.version != null && raw.version !== 1) throw new Error("unsupported version");
    const tasks = Array.isArray(raw?.tasks) ? raw.tasks.filter(validTask) : [];
    return { version: 1, noticed: raw?.noticed === true, tasks: [...new Map(tasks.map((t) => [t.service_id, t])).values()] };
  }
  const notify = () => listeners.forEach((fn) => fn());
  function mutate(fn) {
    try {
      const state = read(), result = fn(state);
      if (result.ok === false || result.existing) return result;
      storage.setItem(HANDLING_KEY, JSON.stringify(state));
      notify();
      return { ok: true, ...result };
    } catch { return { ok: false, message: "未能保存，请重试。请确认浏览器允许保存网站数据。" }; }
  }
  return {
    list() { try { return read().tasks.sort((a, b) => b.savedAt - a.savedAt); } catch { return []; } },
    get(id) { return this.list().find((t) => t.service_id === id); },
    add(task) {
      return mutate((s) => {
        const existing = s.tasks.find((t) => t.service_id === task?.service_id);
        if (existing) return { ok: true, existing: true, task: existing };
        if (!validTask(task)) return { ok: false, message: "事务资料不完整，暂时无法加入。" };
        s.tasks.unshift(JSON.parse(JSON.stringify(task)));
        return { task };
      });
    },
    toggle(id, itemId) {
      return mutate((s) => {
        const task = s.tasks.find((t) => t.service_id === id);
        if (!task?.items.some((i) => i.id === itemId)) return { ok: false, message: "该事务已移出清单。" };
        const checked = new Set(task.checked);
        checked.has(itemId) ? checked.delete(itemId) : checked.add(itemId);
        task.checked = [...checked];
        return { task };
      });
    },
    remove(id) {
      return mutate((s) => {
        const task = s.tasks.find((t) => t.service_id === id);
        if (!task) return { ok: false, message: "该事务已移出清单。" };
        s.tasks = s.tasks.filter((t) => t.service_id !== id);
        return { task };
      });
    },
    // Undo is kept only in UI memory. Never overwrite a task re-added elsewhere.
    restore(task) { return this.add(task); },
    notice() {
      try {
        const state = read();
        if (state.noticed) return false;
        state.noticed = true;
        storage.setItem(HANDLING_KEY, JSON.stringify(state));
      } catch { /* An unavailable store must not prevent viewing the empty list. */ }
      return true;
    },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    refresh: notify,
  };
}

/** Old session ticks are imported only on an explicit add, never as saved tasks. */
export function legacyTicks(task, local, session) {
  try {
    const sid = session.getItem("campuspilot:sid");
    if (!sid) return [];
    const ids = JSON.parse(local.getItem(`campuspilot:checklist:${sid}`) || "{}")[task.service_id];
    return task.items.filter((i) => Array.isArray(ids) && ids.includes(i.id)).map((i) => i.id);
  } catch { return []; }
}
