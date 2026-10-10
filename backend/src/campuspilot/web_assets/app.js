"use strict";
const $ = (id) => document.getElementById(id);
let configured = false;
let busy = false;
let catalogue = { services: [], sources: [] };
let places = [];
let placeSources = [];
let mapState = "loading";
let mapConfig = null;
let mapTimer;
let visiblePlaces = [];
let selectedPlaceId = null;
let searchMode = "places";
// crypto.randomUUID is secure-context only: a plain-HTTP LAN address would throw here and
// take the whole application down. The value only correlates map-frame generations.
function newGeneration() {
  return globalThis.crypto?.randomUUID?.() || `gen-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
let mapGeneration = newGeneration();
let assistantPanelId = "assistant", savedChatScroll = 0;
function setWorkspace(mode) {
  if (mode !== "map" && mode !== "assistant") return;
  if (!$('assistant').hidden) {savedChatScroll = $('messages').scrollTop; Journey.saveChat();}
  document.body.dataset.workspace = mode;
  $('assistant-tools').hidden = mode !== "assistant";
  $('campus-map').setAttribute('aria-hidden', String(mode !== 'map'));
  document.querySelectorAll('[data-workspace]').forEach((button) => {
    if (button === document.body) return;
    const active = button.dataset.workspace === mode;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  });
  if (mode === 'assistant') {
    expandMap(false);
    Guidance.pause('已返回事务助手，步行引导已暂停。');
  }
  requestAnimationFrame(() => sendToMap({action: 'resize'}));
}
function openPanel(id) {
  assistantPanelId = id;
  setWorkspace("assistant");
  document.querySelectorAll(".workspace-panel").forEach((panel) => { panel.hidden = panel.id !== id; });
  document.querySelectorAll("[data-panel]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.panel === id)));
  $("place-detail").hidden = true;
  if (id === 'assistant') $('messages').scrollTop = savedChatScroll;
}
function closePanels() {
  setWorkspace("map");
  document.querySelectorAll(".workspace-panel").forEach((panel) => { panel.hidden = true; });
  document.querySelectorAll("[data-panel]").forEach((button) => button.setAttribute("aria-pressed", "false"));
}
document.querySelectorAll("[data-panel]").forEach((button) => button.addEventListener("click", () => button.dataset.panel === 'knowledge-panel' ? Knowledge.open() : openPanel(button.dataset.panel)));
document.querySelectorAll("[data-close-panel]").forEach((button) => button.addEventListener("click", () => button.closest('.workspace-panel').id === 'assistant' ? closePanels() : openPanel('assistant')));
document.querySelectorAll("button[data-workspace]").forEach((button) => button.addEventListener("click", () => {
  MapDiscovery.cancel();
  if (button.dataset.workspace === 'map') closePanels(); else openPanel(assistantPanelId);
}));
document.querySelector('.brand').addEventListener('click', closePanels);
function expandMap(expanded) {
  $("map-stage").classList.toggle("expanded", expanded);
  document.body.classList.toggle("map-expanded", expanded);
  $("map-expand").setAttribute("aria-pressed", String(expanded));
  $("map-expand").setAttribute("aria-label", expanded ? "收起地图" : "展开地图");
  sendToMap({action: "resize"});
}
$("map-expand").addEventListener("click", () => expandMap(!$("map-stage").classList.contains("expanded")));
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if ($("map-stage").classList.contains("expanded")) expandMap(false);
  else { closePanels(); $("place-detail").hidden = true; }
});
$("map-zoom-in").addEventListener("click", () => sendToMap({action: "zoom", delta: 1}));
$("map-zoom-out").addEventListener("click", () => sendToMap({action: "zoom", delta: -1}));
$("map-overview").addEventListener("click", () => sendToMap({action: "overview"}));
$("places-prev").addEventListener("click", () => $("place-list").scrollBy({left: -$("place-list").clientWidth * .8, behavior: "smooth"}));
$("places-next").addEventListener("click", () => $("place-list").scrollBy({left: $("place-list").clientWidth * .8, behavior: "smooth"}));
new ResizeObserver(() => {
  if (!$("journey-card").hidden) sendToMap({action:"route-insets",bottom:$("journey-card").offsetHeight+24});
}).observe($("journey-card"));
function sendToMap(data) {
  $("map-frame").contentWindow?.postMessage({type: "campuspilot-map", ...data, frame_generation:mapGeneration}, location.origin);
}
window.addEventListener("message", (event) => {
  if (event.origin !== location.origin || event.source !== $("map-frame").contentWindow || event.data?.type !== "campuspilot-map") return;
  const data = event.data;
  if (data.action !== 'frame-ready' && data.frame_generation !== mapGeneration) return;
  if (data.action === "frame-ready" && mapConfig && mapState === "loading") sendToMap({action: "init", config: mapConfig});
  else if (data.action === "ready" && mapState === "loading") {
    clearTimeout(mapTimer); mapState = "ready"; $("map-notice").hidden = true; renderPlaces(visiblePlaces);
    Journey.ready();
    MapDiscovery.ready();
    for (const id of ["map-zoom-in", "map-zoom-out", "map-overview", "map-pick-destination"]) $(id).disabled = false;
  } else if (data.action === "failed" && mapState === "loading") {
    clearTimeout(mapTimer); mapState = "failed"; mapNotice("底图暂时无法加载", "请继续使用地点列表和文字资料。");
    Journey.failed();
    MapDiscovery.failed();
  } else if (data.action === "select" && mapState === "ready") {
    const place = places.find((p) => p.place_id === data.place_id);
    if (place) selectPlace(place);
  } else if (["route-result", "route-origin"].includes(data.action)) {
    Journey.receive(data);
  } else if (data.action === 'nearby-origin-result') {
    Nearby.receive(data);
  } else if (["place-search-result", "map-destination", "poi-selection"].includes(data.action)) {
    MapDiscovery.receive(data);
  } else if (data.action === 'guidance-position') {
    Guidance.receive(data);
  }
});

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function send(path, body = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 105000);
  try {
    const response = await fetch(path, { method: "POST", credentials: "same-origin", signal: controller.signal,
      headers: { "Content-Type": "application/json", "X-CampusPilot-Request": "1" }, body: JSON.stringify(body) });
    let data = {};
    // A proxy or gateway error page is not JSON; never surface a parse error to the user.
    try { data = await response.json(); } catch { data = {}; }
    return { response, data };
  } finally { clearTimeout(timer); }
}
async function request(path, body = {}) {
  try {
    const first = await send(path, body);
    // Restarting the single worker clears in-memory sessions. Re-establish the cookie once
    // instead of telling the user to reload, which would lose the visible conversation.
    if (first.response.status === 401 && path !== "/api/session") {
      const renewed = await send("/api/session");
      if (renewed.data.context_notice) message("已开启新会话，请重新说明身份、学年或办理事项。", "assistant");
      const second = await send(path, body);
      if (!second.response.ok) throw new Error(second.data.message || "会话已重置，请重新提问。");
      return second.data;
    }
    if (!first.response.ok) throw new Error(first.data.message || "服务暂不可用，请稍后再试。");
    return first.data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("等待回答超时，服务可能仍在处理，请稍后开启新对话。");
    throw error;
  }
}
function updateState() {
  $("send").disabled = busy || !configured;
  $("new-chat").disabled = busy;
  $("question").disabled = busy;
  $("send-label").textContent = busy ? "等待中" : "发送";
}
function showStatus(data) {
  configured = data.configured || data.knowledge_available;
  $("status-text").textContent = data.configured ? "办事助手可提问" : "官方资料可查询";
  $("connection-note").hidden = data.configured && !data.context_notice;
  $("connection-note").textContent = "AI 对话暂未连接，可查询已收录的官方资料，或查看事务、地点与老师目录。";
  if (data.context_notice) $("connection-note").textContent = "已开启新的会话，请重新说明本次办理事项、身份和学年。";
  updateState();
}
function message(text, role) {
  const node = element("article", undefined, "message " + role);
  node.append(element("div", role === "user" ? "你" : "CampusPilot", "message-label"));
  const body = element("div", undefined, "message-body");
  if (role === "assistant") {
    // Render the small prose subset we request, without interpreting HTML or URLs.
    for (const line of text.split("\n")) {
      if (!line.trim()) continue;
      const row = element("p");
      for (const part of line.split(/(\*\*[^*\n]+\*\*)/g)) {
        row.append(part.startsWith("**") && part.endsWith("**") ? element("strong", part.slice(2, -2)) : document.createTextNode(part));
      }
      body.append(row);
    }
  } else body.textContent = text;
  node.append(body);
  $("messages").append(node);
  node.scrollIntoView({ block: "nearest" });
  return node;
}
$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = $("question").value.trim();
  if (!text || busy || !configured) return;
  Journey.begin();
  Nearby.cancel();
  document.querySelector(".welcome")?.remove();
  message(text, "user");
  $("question").value = "";
  busy = true; updateState();
  const pending = message("正在查找…", "pending");
  try {
    const data = await request("/api/chat", { message: text });
    pending.remove();
    const answer = message(data.answer, "assistant");
    if (data.nearby_kind) Nearby.attach(answer, data.places || [], {replacement:'补卡点',food:'餐饮地点',parcel:'快递点'}[data.nearby_kind] || '地点', 'assistant');
    for (const record of data.knowledge || []) answer.append(Knowledge.card(record));
    for (const service of data.services || []) {
      appendServiceLinks(answer, service);
      const button = element("button", service.name + " · 详细说明 ↗", "linked-card");
      button.addEventListener("click", () => showService(service)); answer.append(button);
    }
    for (const teacher of data.teachers || []) answer.append(teacherCard(teacher));
    const placeActions = element("div", undefined, "assistant-actions assistant-map-actions");
    for (const place of data.places || []) {
      const button = element("button", place.name + " · 查看地图 ↗", "linked-card");
      button.addEventListener("click", () => {
        Journey.present({...data, places: [place], result_status: "success"}, "assistant");
      }); placeActions.append(button);
    }
    if (placeActions.childElementCount) answer.append(placeActions);
    if (data.excerpts?.length) {
      const details = element("details");
      details.className = "source-details";
      details.append(element("summary", "参考资料"));
      for (const excerpt of data.excerpts) {
        const block = element("div", undefined, "excerpt");
        block.append(element("strong", excerpt.document), element("p", excerpt.content));
        details.append(block);
      }
      answer.append(details);
    }
    $("status-text").textContent = data.answer_mode === "campus_retrieval" ? "校园资料查询完成" : data.answer_mode === "official_retrieval" ? "官方资料查询完成" : "AI 对话已连接";
    $("status-dot").classList.add("ready");
    Journey.saveChat();
    // Keep the answer visible. A place button opens the map only when the user chooses it.
  } catch (error) {
    pending.remove(); message(error.message || "网络连接失败，请检查本地服务。", "error");
    $("status-text").textContent = "本次对话未完成";
    $("status-dot").classList.remove("ready");
  } finally { busy = false; updateState(); if (!$("assistant").hidden) $("question").focus(); }
});
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("chat-form").requestSubmit(); }
});
document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => {
  openPanel("assistant"); $("question").value = button.dataset.question; $("question").focus();
}));
async function resetChat() {
  Nearby.cancel();
  if (busy) return;
  Journey.all();
  busy = true; updateState();
  try { const data = await request("/api/session/reset"); $("messages").replaceChildren(); message("新的对话已准备好。你想办理什么？", "assistant"); showStatus(data); }
  catch (error) { message(error.message, "error"); }
  finally { busy = false; updateState(); }
}
$("new-chat").addEventListener("click", resetChat);
function appendServiceLinks(parent, service) {
  const actions = element("div", undefined, "assistant-actions");
  const links = service.source_links || [];
  const guide = links.find(link => /指南|操作流程|操作手册/.test(link.title) && !/寒假|暑假/.test(link.title))
    || links.find(link => /补办|补卡|办理/.test(link.title)) || links[0];
  if (guide) actions.append(officialLink(guide.url, "官方办理指南"));
  const location = links.find(link => /补卡等相关事宜/.test(link.title));
  if (location && location.url !== guide?.url) actions.append(officialLink(location.url, "补卡地点说明"));
  for (const contact of service.contacts || []) {
    const number = contact.value.replace(/[\s-]/g, "");
    if (!/^\+?\d{7,15}$/.test(number)) continue;
    const link = element("a", `${contact.label} ${contact.value}`);
    link.href = "tel:" + number; actions.append(link);
  }
  if (actions.childElementCount) parent.append(actions);
}
function showService(service) {
  // Tolerate a record missing an optional field instead of breaking the demo panel.
  const content = $("detail-content"); content.replaceChildren();
  const audience = service.audience || "";
  const steps = service.steps || [];
  content.append(element("h2", service.name || "事务"));
  content.append(element("p", `${service.department || ""} · ${audience.split(/[；;]/)[0]}`, "detail-meta"));
  if (service.limits?.length) {
    content.append(element("h3", "办理前须知"));
    for (const limit of service.limits) content.append(element("p", limit));
  }
  if (service.required_materials?.length) {
    content.append(element("h3", "准备材料"));
    for (const material of service.required_materials) content.append(element("p", material));
  }
  appendServiceLinks(content, service);
  content.append(element("h3", "办理步骤"));
  const list = element("ol");
  for (const step of steps) {
    const row = element("li", step.instruction);
    if (step.condition && !/(指南|通知|待复核|未知)/.test(step.condition)) row.append(element("span", step.condition, "condition"));
    for (const pid of step.place_ids || []) {
      const place = places.find((p) => p.place_id === pid);
      if (place) { const button = element("button", place.name + " · 查看地图 ↗", "linked-card"); button.addEventListener("click", () => Journey.present({services: [service], places: [place], result_status: "success"}, "services")); row.append(button); }
    }
    list.append(row);
  }
  content.append(list);
  const details = element("details", undefined, "source-details");
  details.append(element("summary", "来源与补充说明"));
  details.append(element("p", audience));
  for (const step of steps) {
    if (step.condition && /(指南|通知|待复核|未知)/.test(step.condition)) details.append(element("p", step.condition));
  }
  for (const note of service.notes || []) details.append(element("p", note));
  const ids = new Set((service.field_evidence || []).flatMap((field) => field.evidence_ids || []));
  const seen = new Set();
  for (const source of catalogue.sources.filter((item) => ids.has(item.evidence_id))) {
    if (!source.source_url || !source.source_authority.startsWith('official_')) {
      details.append(element('p', source.source_reference + ' · ' + source.publisher)); continue;
    }
    if (seen.has(source.source_url)) continue;
    seen.add(source.source_url);
    const url = new URL(source.source_url);
    if (url.protocol !== "https:" || !(url.hostname === "cdut.edu.cn" || url.hostname.endsWith(".cdut.edu.cn"))) continue;
    const row = element("p"); const link = element("a", source.source_reference + " ↗");
    link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
    row.append(link, element("span", ` · ${source.publisher}${source.source_published_at ? " · " + source.source_published_at : ""}`));
    details.append(row);
  }
  content.append(details);
  openPanel("detail");
}
$("close-detail").addEventListener("click", () => openPanel('guides-panel'));
async function loadCatalogue() {
  try {
    const response = await fetch("/api/catalog");
    if (!response.ok) throw new Error();
    catalogue = await response.json(); $("service-list").replaceChildren();
    catalogue.services.forEach((service) => {
      const card = element("button", undefined, "service-card");
      const top = element("div", undefined, "card-top");
      top.append(element("span", "▤", "card-icon"));
      const bottom = element("div", undefined, "card-bottom");
      bottom.append(element("span", service.department || ""), element("span", "查看步骤 ↗"));
      card.append(top, element("h3", service.name), element("p", service.steps[0]?.instruction || "查看已收录的公开办理说明"), bottom);
      card.addEventListener("click", () => showService(service)); $("service-list").append(card);
    });
  } catch { $("service-list").replaceChildren(element("p", "事务资料暂时无法加载，请检查服务后刷新。", "loading")); }
}
const sessionReady = request("/api/session").then(showStatus).catch(() => { $("status-text").textContent = "本地服务未连接"; $("connection-note").hidden = false; $("connection-note").textContent = "无法建立会话，请检查服务并刷新页面。"; });
loadCatalogue();

const categories = {teaching: "教学", office: "院系与办公", library: "图书馆", dining: "餐厅", service: "服务", sports: "运动", gate: "校门"};
async function getJson(path) {
  const response = await fetch(path, {credentials: "same-origin"});
  if (!response.ok) throw new Error("资料暂时无法读取，请稍后再试。");
  return response.json();
}
function officialLink(urlString, text) {
  try {
    const url = new URL(urlString);
    if (url.protocol !== "https:" || !(url.hostname === "cdut.edu.cn" || url.hostname.endsWith(".cdut.edu.cn"))) return element("span", text);
    const link = element("a", text + " ↗"); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; return link;
  } catch { return element("span", text); }
}
function selectPlace(place) { Journey.select(place); }
function renderPlaces(records) {
  visiblePlaces = records;
  $("place-list").replaceChildren();
  $("place-count").textContent = `${records.length} 个地点`;
  const icons = {teaching: "▤", office: "▥", library: "▣", dining: "♧", service: "⌘", sports: "◎", gate: "⇥"};
  for (const place of records) {
    const row = element("button", undefined, "place-row"); row.dataset.placeId = place.place_id;
    row.dataset.category = place.category; row.setAttribute("aria-pressed", String(place.place_id === selectedPlaceId));
    row.classList.toggle("selected", place.place_id === selectedPlaceId);
    const icon = element("span", icons[place.category] || "⌖", "place-icon"); icon.setAttribute("aria-hidden", "true");
    row.append(icon, element("strong", place.name), element("span", categories[place.category] || "地点", "place-category"), element("small", place.position ? "查看地图 ↗" : "查看详情 ↗"));
    row.addEventListener("click", () => selectPlace(place)); $("place-list").append(row);
  }
  if (!records.length) $("place-list").append(element("p", "目录未收录；点击查找搜索高德地点，或地图选目的地。", "loading"));
  if (mapState === "ready") {
    const located = records.filter((p) => p.position?.coordinate_system === "GCJ02");
    sendToMap({action: "places", selected_place_id: selectedPlaceId, places: records.map((p) => ({place_id: p.place_id, name: p.name, category: p.category, position: p.position}))});
    if (!located.length && records.length) mapNotice("暂未收录地图位置", "可查看地点详情。", true);
    else $("map-notice").hidden = true;
  }
}
async function loadPlaces() {
  try {
    const data = await getJson("/api/places"); places = data.places; placeSources = data.sources; renderPlaces(places);
  } catch (error) { $("place-list").replaceChildren(element("p", error.message, "loading")); }
}
function filterPlaces() {
  if (Journey.active()) Journey.all(false); else Journey.begin();
  const q = $("place-query").value.trim().toLowerCase(); const category = $("place-category").value;
  renderPlaces(Nearby.match(places,q).filter((p) => !category || p.category === category));
}
function setSearchMode(mode) {
  searchMode = mode;
  document.querySelectorAll("[data-search-mode]").forEach((button) => {
    const active = button.dataset.searchMode === mode;
    button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active));
  });
  $("place-query").placeholder = {places: "想去哪里？搜索图书馆、网安楼、餐厅…", teachers: "输入老师姓名，优先计算机与网络安全学院", assistant: "校园卡需要补办，应该怎么做，去哪里？", knowledge: "查通知、活动、借书、校园网或正版软件…"}[mode];
  $("place-query").focus();
}
document.querySelectorAll("[data-search-mode]").forEach((button) => button.addEventListener("click", () => setSearchMode(button.dataset.searchMode)));
document.querySelectorAll(".map-filters [data-category]").forEach((button) => button.addEventListener("click", () => {
  setSearchMode("places"); $("place-category").value = button.dataset.category;
  document.querySelectorAll(".map-filters [data-category]").forEach((chip) => {
    const active = chip.dataset.category === button.dataset.category;
    chip.classList.toggle("active", active); chip.setAttribute("aria-pressed", String(active));
  });
  filterPlaces();
}));
$("place-search").addEventListener("submit", (event) => {
  event.preventDefault(); const query = $("place-query").value.trim();
  if (searchMode === "teachers") {
    openPanel("teacher-panel"); $("teacher-query").value = query; loadTeachers(query, true);
  } else if (searchMode === "knowledge") {
    Knowledge.open(query);
  } else if (searchMode === "assistant") {
    openPanel("assistant"); $("question").value = query; $("question").focus();
    if (query && configured && !busy) $("chat-form").requestSubmit();
  } else {
    closePanels(); $("place-detail").hidden = true;
    const records = Nearby.match(places,query);
    if (query && !records.length) MapDiscovery.search(query);
    else if (query) { MapDiscovery.cancel(); Journey.begin(); Journey.present({places: records, result_status: records.length === 1 ? "success" : "needs_clarification"}); }
    else Journey.all();
  }
});
$("place-category").addEventListener("change", filterPlaces);
$("place-query").addEventListener("input", () => { if (searchMode === "places") filterPlaces(); });
function teacherCard(teacher) {
  const card = element("article", undefined, "teacher-card");
  card.append(element("h3", teacher.name), element("p", teacher.department, "detail-meta"), element("p", teacher.office || "办公室暂未收录", "teacher-location"));
  if (teacher.campus) card.append(element("p", teacher.campus, "detail-meta"));
  const place = places.find((p) => p.place_id === teacher.place_id);
  if (place) { const button = element("button", place.name + " · 查看地点 ↗", "linked-card"); button.addEventListener("click", () => Journey.present({teachers: [teacher], places: [place], result_status: "success"}, "teachers")); card.append(button); }
  const details = element("details", undefined, "source-details");
  details.append(element("summary", "教师资料"));
  for (const note of teacher.notes || []) details.append(element("p", note));
  details.append(officialLink(teacher.profile_url, "教师主页"));
  card.append(details);
  return card;
}
let teacherRequest = 0;
async function loadTeachers(query = "", committed = false) {
  const requestId = ++teacherRequest;
  const ticket = committed ? Journey.begin() : null;
  try {
    const data = await getJson("/api/teachers?q=" + encodeURIComponent(query));
    if (requestId !== teacherRequest || (committed && !Journey.current(ticket))) return;
    $("teacher-list").replaceChildren();
    for (const teacher of data.teachers) $("teacher-list").append(teacherCard(teacher));
    if (!data.teachers.length) $("teacher-list").append(element("p", "未收录这位老师；请核对姓名，或查看学院官方名录。", "loading"));
    if (committed && query) Journey.present({teachers: data.teachers, places: places.filter((p) => data.teachers.some((t) => t.place_id === p.place_id)), result_status: data.teachers.length === 1 ? "success" : data.teachers.length ? "needs_clarification" : "empty"}, "teachers", ticket);
  } catch (error) { $("teacher-list").replaceChildren(element("p", error.message, "loading")); }
}
$("teacher-search").addEventListener("submit", (event) => { event.preventDefault(); loadTeachers($("teacher-query").value.trim(), true); });
function mapNotice(title, text, compact = false) {
  $("map-notice").classList.toggle("map-note", compact);
  $("map-notice").hidden = false; $("map-notice").replaceChildren(element("span", "⌖"), element("h3", title), element("p", text));
  if (mapState === 'failed') {const retry=element('button','重新加载地图','journey-button');retry.type='button';retry.addEventListener('click',restartMap);$('map-notice').append(retry);}
}
function restartMap() {
  Nearby.cancel();
  clearTimeout(mapTimer); mapGeneration=newGeneration(); mapState='loading';
  for (const id of ['map-zoom-in','map-zoom-out','map-overview','map-pick-destination']) $(id).disabled=true;
  mapNotice('正在重新加载地图','对话和资料会保留。');
  $('map-frame').src='/map-view';
  mapTimer=setTimeout(() => {
    if (mapState !== 'loading') return;
    mapState='failed';mapNotice('底图暂时无法加载','请继续使用文字资料。');Journey.failed();MapDiscovery.failed();
  },35000);
}
async function initMap() {
  try {
    const config = await getJson("/api/map-config");
    if (!config.configured) { mapState = "unconfigured"; mapNotice("地图暂未连接", "地点与老师资料仍可查询。"); return; }
    mapConfig = {key: config.key};
    $("map-frame").addEventListener("load", () => sendToMap({action: "ping"}));
    sendToMap({action: "ping"});
    mapTimer = setTimeout(() => {
      if (mapState !== "loading") return;
      mapState = "failed"; mapNotice("底图暂时无法加载", "地图加载超时，请继续使用地点列表和文字资料。");
      Journey.failed();
      MapDiscovery.failed();
    }, 35000);
  } catch (error) {
    mapState = "failed";
    mapNotice("底图暂时无法加载", "请继续使用地点列表和文字资料。" + (error.message || ""));
  }
}
loadPlaces().then(() => {loadTeachers(); initMap();});
document.querySelectorAll('[data-campus-collection]').forEach(button=>button.addEventListener('click',()=>{
  MapDiscovery.cancel();Nearby.cancel();Journey.begin();
  const kind=button.dataset.campusCollection;
  const service=catalogue.services.find(s=>s.service_id==='cdut:service:campus-card-replacement');
  const ids=new Set((service?.steps||[]).flatMap(s=>s.place_ids||[]));
  const records=places.filter(p=>kind==='replacement' ? ids.has(p.place_id) : (p.tags||[]).includes(kind));
  Journey.present({places:records,result_status:'needs_clarification'});
  if (kind!=='east-teaching') {
    const holder=element('div');$('journey-body').prepend(holder);
    if(kind==='replacement') holder.append(element('p','补卡前：带身份证，卡内余额须大于20元。'));
    Nearby.attach(holder,records,{replacement:'补卡点',food:'餐饮地点',parcel:'快递点'}[kind]);
  }
}));
document.addEventListener('visibilitychange',()=>{if(document.hidden) Nearby.cancel();});
window.addEventListener('pagehide',()=>Nearby.cancel());
