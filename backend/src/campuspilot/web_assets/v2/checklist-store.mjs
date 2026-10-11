// Checklist ticks persisted per browser session id in localStorage (no personal data).
const PREFIX = "campuspilot:checklist:";
export function createChecklistStore(storage, sessionId) {
  const key = PREFIX + sessionId;
  const read = () => { try { return JSON.parse(storage.getItem(key) || "{}") || {}; } catch { return {}; } };
  return {
    isDone(serviceId, itemId) { return !!read()[serviceId]?.includes(itemId); },
    toggle(serviceId, itemId) {
      const all = read(), set = new Set(all[serviceId] || []);
      set.has(itemId) ? set.delete(itemId) : set.add(itemId);
      all[serviceId] = [...set].sort();
      try { storage.setItem(key, JSON.stringify(all)); } catch { /* quota or private mode */ }
      return set.has(itemId);
    },
    count(serviceId, ids) { const done = new Set(read()[serviceId] || []); return ids.filter((i) => done.has(i)).length; },
    clear() { try { storage.removeItem(key); } catch { /* ignore */ } },
  };
}
export function sessionId(storage) {
  const k = "campuspilot:sid";
  let v = storage.getItem(k);
  if (!v) { v = Math.random().toString(36).slice(2, 10); storage.setItem(k, v); }
  return v;
}
