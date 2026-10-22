"use strict";
const Knowledge = (() => {
  let sequence = 0;
  const labels = {ended: "已结束", current: "适用期内", upcoming: "尚未开始", reference: "办事资料", undated: "时间未明确", superseded: "已有后续版本"};
  function sourceLink(record) {
    if (record.source_kind !== "official_wechat") return officialLink(record.source_url, "查看官方原文");
    try {
      const url = new URL(record.source_url);
      if (url.protocol !== "https:" || url.hostname !== "mp.weixin.qq.com" || !url.pathname.startsWith("/s") || url.username || url.password) return element("span", "原文链接不可用");
      const a = element("a", "查看公众号原文 ↗"); a.href = url.href; a.target = "_blank"; a.rel = "noopener noreferrer"; return a;
    } catch { return element("span", "原文链接不可用"); }
  }
  function card(record) {
    const article = element("article", undefined, "knowledge-card");
    const top = element("div", undefined, "knowledge-card-heading");
    top.append(element("h3", record.title), element("span", labels[record.time_status] || "资料", "knowledge-tag " + record.time_status));
    article.append(top, element("p", record.summary));
    if (record.registration_until) article.append(element("p", "报名／征集截止：" + record.registration_until, "knowledge-date"));
    if (record.event_from) article.append(element("p", "活动：" + record.event_from + (record.event_until && record.event_until !== record.event_from ? " 至 " + record.event_until : ""), "knowledge-date"));
    article.append(element("p", record.audience_text, "knowledge-meta"));
    const details = element("details", undefined, "source-details");
    details.append(element("summary", "要求与详情"));
    for (const text of record.details) details.append(element("p", text));
    if (record.location_text) details.append(element("p", "地点：" + record.location_text));
    details.append(element("p", `${record.publisher} · 发布 ${record.published_on || "日期未注明"} · 收录 ${record.collected_on}`, "knowledge-meta"));
    article.append(details);
    const actions = element("div", undefined, "knowledge-actions");
    actions.append(sourceLink(record));
    if (record.action_url) actions.append(officialLink(record.action_url, record.action_label));
    for (const id of record.place_ids || []) {
      const place = places.find((p) => p.place_id === id);
      if (!place) continue;
      const button = element("button", "查看地点 · " + place.name, "linked-card");
      button.addEventListener("click", () => selectPlace(place)); actions.append(button);
    }
    article.append(actions); return article;
  }
  async function search() {
    const ticket = ++sequence;
    $("knowledge-status").textContent = "正在查找官方资料…";
    $("knowledge-results").replaceChildren();
    try {
      await sessionReady;
      const data = await request("/api/knowledge/search", {query: $("knowledge-query").value.trim(), category: $("knowledge-category").value, period: $("knowledge-period").value, audience: $("knowledge-audience").value});
      if (ticket !== sequence) return;
      $("knowledge-status").textContent = `${data.knowledge.length} 条结果 · 按 ${data.as_of} 判断时间 · 已收录资料${data.collected_on ? "更新于 " + data.collected_on : ""}`;
      if (!data.knowledge.length) {
        $("knowledge-results").append(element("p", data.answer, "knowledge-empty"), officialLink("https://www.cdut.edu.cn/", "学校官网"));
      } else for (const record of data.knowledge) $("knowledge-results").append(card(record));
    } catch (error) {
      if (ticket !== sequence) return;
      $("knowledge-status").textContent = error.message;
      const retry = element("button", "重新查询", "linked-card"); retry.addEventListener("click", search); $("knowledge-results").append(retry);
    }
  }
  function open(query = "") {
    Journey.begin(); openPanel("knowledge-panel");
    $("knowledge-query").value = query;
    for (const id of ["knowledge-category", "knowledge-period", "knowledge-audience"]) $(id).value = "all";
    search();
  }
  $("knowledge-form").addEventListener("submit", (event) => {event.preventDefault(); search();});
  for (const id of ["knowledge-category", "knowledge-period", "knowledge-audience"]) $(id).addEventListener("change", search);
  return {open, card};
})();
