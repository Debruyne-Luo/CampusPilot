// Structured answer cards built from the /api/chat response contract.
import { h } from "./dom.mjs";
import { hasPosition } from "./places.mjs";
import { formatDistance, rankPlaces } from "./geo.mjs";

const STATUS = { success: "已核对引用", limited: "资料摘要（未生成答案）", needs_clarification: "需要补充信息", empty: "没有找到依据" };

export function planCard(state) {
  const list = h("ol", { class: "plan-steps", "aria-label": "执行计划" });
  for (const s of state.steps) {
    list.append(h("li", { class: `step ${s.status}`, "data-key": s.key },
      h("span", { class: "dot", "aria-hidden": "true" }),
      h("span", { class: "label" }, s.label),
      h("span", { class: "meta" }, s.status === "running" ? "进行中…" : s.meta || ""),
      h("span", { class: "sr-only" }, { done: "已完成", running: "进行中", pending: "等待", empty: "无结果", skipped: "跳过" }[s.status] || "")));
  }
  return h("section", { class: "card plan", "aria-label": "执行计划" }, h("h4", {}, "执行计划"), list);
}

/** Cited sources: the deduped citation cards (same as 引用来源 N 条); else unique source ids. */
export function citedCount(body) {
  if (Array.isArray(body?.citations)) return body.citations.length;
  return Array.isArray(body?.source_ids) ? new Set(body.source_ids).size : 0;
}

function conclusion(body) {
  const status = body.result_status || "success";
  const ok = status === "success";
  return h("section", { class: `card answer ${status}` },
    h("span", { class: `badge ${ok ? "ok" : "warn"}` }, ok ? `✓ ${STATUS.success}${citedCount(body) ? ` · ${citedCount(body)} 处` : ""}` : STATUS[status] || status),
    h("p", { class: "conclusion" }, body.answer || ""),
    body.degraded_reason ? h("p", { class: "fineprint" }, "模型答案未通过校验，以下为已收录资料。") : null);
}

function checklistCard(list, store) {
  // Steps have their own card; the checklist holds what to bring, know and watch out for.
  const items = (list.items || []).filter((i) => i.kind !== "step");
  const ids = items.map((i) => i.id);
  const counter = h("span", { class: "count" });
  const bar = h("i");
  const update = () => {
    const n = store.count(list.service_id, ids);
    counter.textContent = `${n}/${ids.length}`;
    bar.style.width = `${ids.length ? (n / ids.length) * 100 : 0}%`;
  };
  const ul = h("ul", { class: "checklist" });
  for (const item of items) {
    const box = h("input", { type: "checkbox", id: `ck-${list.service_id}-${item.id}` });
    box.checked = store.isDone(list.service_id, item.id);
    box.addEventListener("change", () => { box.checked = store.toggle(list.service_id, item.id); update(); });
    const kind = { material: "材料", input: "信息", limit: "注意", step: "步骤" }[item.kind] || "";
    ul.append(h("li", {}, box, h("label", { for: box.id }, h("span", { class: `kind ${item.kind}` }, kind), item.text)));
  }
  update();
  return h("section", { class: "card checklist-card", "aria-label": "办理清单" },
    h("h4", {}, list.title || "办理清单", " ", counter),
    h("div", { class: "progress", role: "presentation" }, bar), ul,
    list.fees_note?.length ? h("p", { class: "fineprint" }, "费用：", list.fees_note.join("；")) : null);
}

function stepsCard(services) {
  const steps = services.flatMap((s) => s.steps || []).slice(0, 6);
  if (!steps.length) return null;
  return h("section", { class: "card" }, h("h4", {}, "办理步骤"),
    h("ol", { class: "steps" }, steps.map((s) => h("li", {}, s.instruction))));
}

/**
 * "去哪办": every place is selectable, with its own distance and 带我去. When the origin is
 * known the list is nearest-first and the nearest is marked 推荐. `card.update(origin)`
 * re-ranks in place when the origin changes (GPS fix or manual choice).
 */
export function placesCard(places, { onFocus, onGo, onFrom, origin = null }) {
  if (!places.length) return null;
  const list = h("ul", { class: "place-list" });
  const card = h("section", { class: "card places-card", "aria-label": "去哪办" }, h("h4", {}, "去哪办"), list);
  card.update = (from) => {
    const { rows, recommended } = rankPlaces(places.slice(0, 8), from);
    list.replaceChildren(...rows.map(({ place: p, distance }) => {
      const located = hasPosition(p), best = recommended && p.place_id === recommended.place_id;
      return h("li", { class: `place-row ${best ? "best" : ""}`, "data-place-id": p.place_id },
        h("button", { type: "button", class: "place-name", onclick: () => onFocus(p), "aria-label": `${p.name}，在地图上查看` },
          h("b", {}, p.name), best ? h("span", { class: "tag-best" }, "推荐 · 最近") : null,
          h("small", {}, located ? (distance != null ? `约 ${formatDistance(distance)}` : "在地图上查看") : "暂无位置")),
        located ? h("span", { class: "row-actions" },
          onFrom ? h("button", { type: "button", class: "chip ghost", onclick: () => onFrom(p), title: `从${p.name}出发` }, "从这出发") : null,
          h("button", { type: "button", class: "chip go", onclick: () => onGo(p) }, "带我去")) : null);
    }));
  };
  card.update(origin);
  return card;
}

function citationsCard(citations) {
  if (!citations?.length) return null;
  const shown = citations.slice(0, 6);
  return h("details", { class: "card citations" },
    h("summary", {}, h("span", {}, "引用来源"), h("span", { class: "count-pill" }, `${citations.length} 条`)),
    shown.map((c, i) => h("details", {},
      h("summary", {}, `[${i + 1}] ${c.title || c.id}`),
      h("div", { class: "cite-meta" },
        [c.publisher, c.date ? `${c.date_kind === "retrieved" ? "采集于 " : ""}${c.date}` : null, c.audience ? `适用：${c.audience}` : null].filter(Boolean).join(" · "),
        c.url ? h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, " 查看原文") : null))));
}

export function answerCards(body, { store, onFocus, onGo, onFrom, origin = null }) {
  const teachers = (body.teachers || []).map((t) =>
    h("section", { class: "card" }, h("h4", {}, "老师"), h("p", { class: "conclusion" }, t.name),
      h("p", {}, [t.department, t.office].filter(Boolean).join(" · "))));
  return [
    conclusion(body),
    body.checklist?.items?.some((i) => i.kind !== "step") ? checklistCard(body.checklist, store) : null,
    stepsCard(body.services || []),
    ...teachers,
    placesCard(body.places || [], { onFocus, onGo, onFrom, origin }),
    citationsCard(body.citations),
  ].filter(Boolean);
}
