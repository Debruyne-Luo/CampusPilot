// Structured answer cards built from the /api/chat response contract.
import { h } from "./dom.mjs";
import { hasPosition } from "./places.mjs";
import { distanceMeters, formatDistance, rankPlaces } from "./geo.mjs";
import { normalizeServiceLinks } from "./service-links.mjs";

const STATUS = { success: "已核对引用", limited: "目前可确认的信息", needs_clarification: "需要补充信息", empty: "没有找到依据" };
const DEGRADED = { upstream_timeout: "模型响应超时。", upstream_unavailable: "模型暂不可用。", output_truncated: "模型回复未完整返回。", invalid_response: "模型返回格式异常。", tool_rounds_exceeded: "本轮查询已达到次数限制。", evidence_insufficient: "当前证据不足以回答全部问题。", agent_timeout: "本轮处理超时。", agent_error: "本轮处理暂不可用。", model_not_configured: "模型尚未配置。", model_timeout: "模型响应超时。", model_failed: "模型暂不可用。", model_format: "模型返回格式异常。", invalid_format: "模型返回格式异常。", answer_validation: "部分内容未通过依据校验。", validation_failed: "部分内容未通过依据校验。", insufficient_evidence: "当前证据不足以回答全部问题。", web_search_failed: "联网搜索未完成。" };

export function answerBadge(body) {
  if (body.answer_mode === "agent_place") return "已找到地点";
  if (body.answer_mode === "agent_image" || body.answer_mode === "image") return "图片内容";
  return `✓ ${STATUS.success}${citedCount(body) ? ` · ${citedCount(body)} 处` : ""}`;
}

export function planCard(state) {
  const list = h("ol", { class: "plan-steps", "aria-label": "执行计划" });
  for (const s of state.steps) {
    const runningText = s.status === "running" ? `${s.label?.includes("查") || s.label?.includes("搜") ? "" : "正在"}${s.label}…` : (s.meta || "");
    list.append(h("li", { class: `step ${s.status}`, "data-key": s.key },
      h("span", { class: "dot", "aria-hidden": "true" }),
      h("span", { class: "label" }, s.label),
      h("span", { class: "meta" }, s.status === "running" ? (s.meta || "进行中…") : s.meta || ""),
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
  const n = citedCount(body);
  const title = (body.places || [])[0]?.name || "";
  const rail = (body.citations || []).slice(0, 3);
  return h("section", { class: `card answer ${status}` },
    h("div", { class: "stream-line", "aria-hidden": "true" }, h("i", {})),
    h("div", { class: "kicker" }, ok ? `已核对 · 引用 ${n} 条` : (STATUS[status] || status)),
    title ? h("h3", { class: "bigq" }, title) : null,
    h("p", { class: "conclusion" }, body.answer || ""),
    rail.length ? h("div", { class: "srcs" }, rail.map((c, i) =>
      h("div", { class: "src" }, h("b", {}, `[${i + 1}] ${c.title || c.id}`),
        h("span", {}, [c.source_label || "官方材料", c.date || null].filter(Boolean).join(" · "),
          c.url ? h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, " ↗") : null)))) : null,
    body.degraded_reason ? h("p", { class: "fineprint" }, DEGRADED[body.degraded_reason] || "当前只提供能够确认的信息。") : null);
}

function stepsCard(services) {
  const steps = services.flatMap((s) => s.steps || []);
  if (!steps.length) return null;
  return h("section", { class: "card" }, h("div", { class: "kicker" }, "办理方式"),
    h("ol", { class: "numsteps" }, steps.map((s, i) => h("li", {},
      h("span", { class: "no" }, String(i + 1).padStart(2, "0")),
      h("span", {}, s.condition ? `${s.instruction}（适用：${s.condition}）` : s.instruction)))));
}

export function serviceLinksCard(body) {
  const links = normalizeServiceLinks(body);
  if (!links.length) return null;
  return h("section", { class: "card service-links", "aria-label": "网上办理" },
    h("h4", {}, "网上办理"),
    links.map((link) => h("div", { class: "service-link-row" },
      h("p", {}, h("strong", {}, link.title)),
      h("a", { class: "chip go", href: link.url, target: "_blank", rel: "noopener noreferrer", "aria-label": `${link.action_label}：${link.title}` }, link.action_label),
      h("p", { class: "fineprint" }, link.hints.join(" · ")),
      h("p", { class: "fineprint" }, `依据：${link.source_title || "官方材料"} `,
        link.source_url ? h("a", { href: link.source_url, target: "_blank", rel: "noopener noreferrer" }, "查看入口依据") : null))),
    h("p", { class: "fineprint" }, "入口来自已引用的官方材料；当前可用性未核实，请以平台提示为准。"));
}

/**
 * "去哪办": every place is selectable, with its own distance and 带我去. When the origin is
 * known the list is nearest-first and the nearest is marked 推荐. `card.update(origin)`
 * re-ranks in place when the origin changes (GPS fix or manual choice).
 */
export function placesCard(places, { onFocus, onGo, onFrom, origin = null }) {
  if (!places.length) return null;
  const list = h("ul", { class: "place-list" });
  const label = places.some((p) => p.transient) ? "目的地" : "去哪办";
  const card = h("section", { class: "card places-card", "aria-label": label }, h("h4", {}, label), list);
  card.update = (from) => {
    const ambiguous = places.length > 1 && places.some((p) => p.transient);
    const { rows, recommended } = ambiguous
      ? { rows: places.slice(0, 10).map((place) => ({ place, distance: from && place.position ? distanceMeters(from, place.position) : null })), recommended: null }
      : rankPlaces(places.slice(0, 10), from);
    list.replaceChildren(...rows.map(({ place: p, distance }) => {
      const located = hasPosition(p), best = recommended && p.place_id === recommended.place_id;
      return h("li", { class: `place-row ${best ? "best" : ""}`, "data-place-id": p.place_id },
        h("button", { type: "button", class: "place-name", onclick: () => onFocus(p), "aria-label": `${p.name}，在地图上查看` },
          h("b", {}, p.name), best ? h("span", { class: "tag-best" }, "推荐 · 最近") : null,
          h("small", {}, located ? (distance != null ? `约 ${formatDistance(distance)}` : "在地图上查看") : "暂无位置"),
          p.source_provider === "amap" ? h("small", { class: "place-source" }, `来源：高德地图${p.address ? ` · ${p.address}` : ""}`) : null),
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
  const official = citations.filter((c) => String(c.source_label || "").includes("官方") || String(c.authority || "").startsWith("official_") || c.official).length;
  const third = citations.length - official;
  const mix = official && third ? ` · 官方 ${official} / 第三方 ${third}` : official ? ` · 官方 ${official}` : "";
  return h("details", { class: "card citations" },
    h("summary", {}, h("span", {}, "全部引用来源"), h("span", { class: "count-pill" }, `${citations.length} 条${mix}`)),
    shown.map((c, i) => h("details", { id: `cite-${i + 1}` },
      h("summary", {}, `[${i + 1}] ${c.title || c.id}`),
      h("div", { class: "cite-meta" },
        [c.source_label, c.publisher, c.date ? `${c.date_kind === "retrieved" ? "采集于 " : ""}${c.date}` : null, c.audience ? `适用：${c.audience}` : null].filter(Boolean).join(" · "),
        c.url ? h("a", { href: c.url, target: "_blank", rel: "noopener noreferrer" }, " 查看原文↗") : null))));
}

function webSourcesCard(sources) {
  if (!sources?.length) return null;
  return h("details", { class: "card web-sources" }, h("summary", {}, "联网搜索线索（待核对）"),
    sources.slice(0, 6).map((s) => h("p", { class: "cite-meta" },
      h("span", {}, `${s.source_label || (s.authority?.startsWith("official_") || s.official ? "待核对官方材料" : "第三方辅助")} · `),
      s.url ? h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.title || "查看搜索来源") : s.title || "搜索来源")));
}

export function answerCards(body, { checklistPreview, onFocus, onGo, onFrom, onMapPick, origin = null }) {
  const teachers = (body.teachers || []).map((t) =>
    h("section", { class: "card" }, h("h4", {}, "老师"), h("p", { class: "conclusion" }, t.name),
      h("p", {}, [t.department, t.office].filter(Boolean).join(" · "))));
  return [
    conclusion(body),
    checklistPreview?.(body),
    serviceLinksCard(body),
    stepsCard(body.services || []),
    ...teachers,
    placesCard(body.places || [], { onFocus, onGo, onFrom, origin }),
    body.map_pick_available && onMapPick ? h("section", { class: "card" }, h("button", { type: "button", class: "chip", onclick: onMapPick }, "在地图上选择地点")) : null,
    citationsCard(body.citations),
    webSourcesCard(body.web_sources),
  ].filter(Boolean);
}
