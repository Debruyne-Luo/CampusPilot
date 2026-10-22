// Structured answer cards built from the /api/chat response contract.
import { h } from "./dom.mjs";
import { hasPosition } from "./places.mjs";
import { distanceMeters, formatDistance, rankPlaces } from "./geo.mjs";
import { normalizeServiceLinks, safeServiceUrl } from "./service-links.mjs";

const STATUS = { success: "已核对引用", limited: "目前可确认的信息", needs_clarification: "需要补充信息", empty: "没有找到依据" };
const DEGRADED = { upstream_timeout: "模型响应超时。", upstream_unavailable: "模型暂不可用。", output_truncated: "模型回复未完整返回。", invalid_response: "模型返回格式异常。", tool_rounds_exceeded: "本轮查询已达到次数限制。", evidence_insufficient: "当前证据不足以回答全部问题。", agent_timeout: "本轮处理超时。", agent_error: "本轮处理暂不可用。", model_not_configured: "模型尚未配置。", model_timeout: "模型响应超时。", model_failed: "模型暂不可用。", model_format: "模型返回格式异常。", invalid_format: "模型返回格式异常。", answer_validation: "部分内容未通过依据校验。", validation_failed: "部分内容未通过依据校验。", insufficient_evidence: "当前证据不足以回答全部问题。", web_search_failed: "联网搜索未完成。" };

export function answerBadge(body) {
  if (body.answer_mode === "agent_place") return "已找到地点";
  if (body.answer_mode === "agent_image" || body.answer_mode === "image") return "图片内容";
  const count = citedCount(body);
  return count ? `✓ ${STATUS.success} · ${count} 处` : "引用 0 条";
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
  return state.done
    ? h("details", { class: "card plan", "aria-label": "执行计划" }, h("summary", {}, "查看处理过程"), list)
    : h("section", { class: "card plan", "aria-label": "执行计划" }, h("h4", {}, "正在处理"), list);
}

/** Cited sources: the deduped citation cards (same as 引用来源 N 条); else unique source ids. */
export function citedCount(body) {
  if (Array.isArray(body?.citations)) return body.citations.length;
  return Array.isArray(body?.source_ids) ? new Set(body.source_ids).size : 0;
}

// Only paired, nonempty inline **labels** become nodes. Everything else stays text.
// Never interpret model HTML or consume markers across paragraph boundaries.
function answerText(text) {
  const parts = [], pattern = /\*\*([^*\r\n]+)\*\*/g;
  let end = 0;
  for (const match of text.matchAll(pattern)) {
    parts.push(text.slice(end, match.index), h("strong", {}, match[1]));
    end = match.index + match[0].length;
  }
  parts.push(text.slice(end));
  return parts;
}

function answerParagraphs(text) {
  return text.split(/(\n[\t ]*\n)/).map((part, i) => i % 2
    ? part : h("p", { class: "answer-paragraph" }, answerText(part)));
}

function conclusion(body) {
  const status = body.result_status || "success";
  const ok = status === "success";
  const n = citedCount(body);
  const title = (body.services || [])[0]?.name || (body.places || [])[0]?.name || "";
  return h("section", { class: `card answer ${status}` },
    h("div", { class: "stream-line", "aria-hidden": "true" }, h("i", {})),
    h("div", { class: "kicker" }, ok ? `${n ? "已核对 · " : ""}引用 ${n} 条` : (STATUS[status] || status)),
    title ? h("h2", { class: "bigq" }, title) : null,
    h("div", { class: "conclusion" }, answerParagraphs(body.answer || "")),
    body.degraded_reason ? h("p", { class: "fineprint" }, DEGRADED[body.degraded_reason] || "当前只提供能够确认的信息。") : null);
}

function stepsCard(services) {
  const procedures = services.filter((s) => s.information_level === "procedure" && s.steps?.length);
  if (!procedures.length) return null;
  return h("details", { class: "card procedure-details" },
    h("summary", { "aria-label": "查看办理步骤，展开材料与具体操作" }, "查看办理步骤"),
    procedures.map((service) => {
      const preparation = [...(service.required_materials || []), ...(service.required_inputs || [])];
      const notes = [...(service.limits || []), ...(service.fees || []).map(f => `费用：${f}`), ...(service.notes || [])];
      return h("section", { class: "procedure-content" },
        procedures.length > 1 ? h("h3", {}, service.name) : null,
        preparation.length ? h("div", {}, h("h4", {}, "需要准备"),
          h("ul", {}, preparation.map(item => h("li", {}, item)))) : null,
        service.required_materials == null || service.required_inputs == null
          ? h("p", { class: "fineprint" }, "部分准备要求待核实。") : null,
        h("h4", {}, "具体步骤"),
        h("ol", { class: "numsteps" }, service.steps.map((step, i) => h("li", {},
          h("span", { class: "no" }, String(i + 1).padStart(2, "0")),
          h("span", {}, step.instruction,
            step.condition ? h("small", { class: "step-condition" }, `适用：${step.condition}`) : null)))),
        notes.length ? h("div", {}, h("h4", {}, "注意事项"), h("ul", {}, notes.map(note => h("li", {}, note)))) : null);
    }));
}

export function serviceGuideCards(services) {
  return services.filter((s) => s.information_level !== "procedure").map((s) =>
    h("details", { class: "card service-guide", "aria-label": "办事指南" },
      h("summary", {}, s.name || "办事事项"),
      h("p", { class: "fineprint" }, s.information_level === "directory" ? "事项目录" : "办事指南"),
      h("p", {}, [s.department, s.audience, s.academic_year ? `${s.academic_year} 学年` : null].filter(Boolean).join(" · ")),
      s.summary ? h("p", {}, s.summary) : null,
      ...(s.contacts || []).map((contact) => h("p", {}, `${contact.label}：${contact.value}`)),
      ...[...(s.required_materials || []).map((x) => `材料：${x}`),
        ...(s.required_inputs || []).map((x) => `需准备的信息：${x}`),
        ...(s.limits || []), ...(s.fees || []).map((x) => `费用：${x}`)].map((x) => h("p", {}, x)),
      (s.entry_points || []).length ? h("div", {}, h("h5", {}, "已知入口"),
        ...s.entry_points.map((entry) => h("p", {}, safeServiceUrl(entry)
          ? h("a", { href: safeServiceUrl(entry), target: "_blank", rel: "noopener noreferrer" }, entry)
          : entry))) : null,
      h("p", { class: "fineprint" }, s.procedure_note || "完整办理流程尚未核验，请查阅官方指南。"),
      ...(s.source_links || []).filter((source) => {
        try { const u = new URL(source.url); return u.protocol === "https:" && !u.username && !u.password; } catch { return false; }
      }).map((source) => h("a", { href: source.url, target: "_blank", rel: "noopener noreferrer" }, source.title || "官方指南"))));
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
        h("button", { type: "button", class: "place-name", onclick: () => onFocus(p), "aria-pressed": "false", "aria-label": `${p.name}，在地图上查看` },
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
  const shown = citations;
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
    ...serviceGuideCards(body.services || []),
    stepsCard(body.services || []),
    ...teachers,
    placesCard(body.places || [], { onFocus, onGo, onFrom, origin }),
    body.map_pick_available && onMapPick ? h("section", { class: "card" }, h("button", { type: "button", class: "chip", onclick: onMapPick }, "在地图上选择地点")) : null,
    citationsCard(body.citations),
    webSourcesCard(body.web_sources),
  ].filter(Boolean);
}
