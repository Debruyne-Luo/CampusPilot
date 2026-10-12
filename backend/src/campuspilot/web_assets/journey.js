"use strict";
// One transient query/route state. Personal origins never enter chat or storage.
const Journey = (() => {
  let result = null, target = null, route = null, epoch = 0, routeSequence = 0;
  let chatScroll = 0, pendingRoute = null, routeTimer, routeCompact = false;
  const located = (p) => p?.position?.coordinate_system === "GCJ02" &&
    Number.isFinite(p.position.longitude) && Number.isFinite(p.position.latitude);
  function button(text, action, primary = false) {
    const b = element("button", text, primary ? "journey-primary" : "journey-button");
    b.type = "button"; b.addEventListener("click", action); return b;
  }
  function invalidateRoute() {
    Guidance.stop();
    clearTimeout(routeTimer); routeSequence++; pendingRoute = null; route = null;
    routeCompact = false; $('journey-card').classList.remove('route-compact');
    sendToMap({action: "route-clear", request_id: routeSequence});
  }
  function begin() {
    if (typeof MapDiscovery !== "undefined") MapDiscovery.cancel();
    epoch++; invalidateRoute(); selectedPlaceId = null;
    sendToMap({action: "selection", place_id: null});
    if (result) render();
    return epoch;
  }
  function clearCategory() {
    $("place-category").value = "";
    document.querySelectorAll("[data-category].active").forEach((chip) => {chip.classList.remove("active"); chip.setAttribute("aria-pressed", "false");});
    const all = document.querySelector('.map-filters [data-category=""]');
    all.classList.add("active"); all.setAttribute("aria-pressed", "true");
  }
  function linkedTeacher(t, pool) {
    return pool.filter((p) => p.place_id === t.place_id);
  }
  function present(data, source = "places", ticket = null) {
    if (ticket !== null && ticket !== epoch) return;
    if (ticket === null) epoch++; // A manual selection supersedes any in-flight query.
    invalidateRoute(); target = null; selectedPlaceId = null; clearCategory();
    result = {teachers: [], services: [], places: [], ...data, source};
    closePanels(); $("place-detail").hidden = true;
    document.activeElement?.blur();
    $("map-stage").classList.add("journey-active");
    renderPlaces(result.places);
    if (result.result_status === "success" && result.teachers.length <= 1 &&
        result.services.length <= 1 && result.places.length === 1) target = result.places[0];
    focusTarget(); render();
    $("journey-title").focus({preventScroll: true});
    $("map-stage").scrollIntoView({block: "nearest", behavior: "smooth"});
  }
  function focusTarget() {
    selectedPlaceId = target?.place_id || null;
    if (mapState !== "ready") return;
    renderPlaces(result?.places || visiblePlaces);
    if (located(target)) sendToMap({action: "center", position: target.position, place_id: target.place_id});
  }
  function select(place) {
    begin();
    if (!result || !result.places.some((p) => p.place_id === place.place_id) || result.result_status !== "success") {
      result = {teachers: [], services: [], places: [place], result_status: "success", source: "places"};
    }
    target = place; clearCategory(); closePanels(); $("place-detail").hidden = true;
    $("map-stage").classList.add("journey-active"); focusTarget(); render();
  }
  function externalLink(parent, href, text, allowed) {
    try {
      const u = new URL(href);
      if (u.protocol !== "https:" || u.username || u.password || !allowed(u)) return;
      const a = element("a", text); a.href = u.href; a.target = "_blank"; a.rel = "noopener noreferrer";
      parent.append(a);
    } catch { /* Missing or invalid optional source. */ }
  }
  function render() {
    const card = $("journey-card"); card.replaceChildren(); card.hidden = !result;
    if (!result) return;
    card.classList.toggle('route-compact',routeCompact);
    const head = element("div", undefined, "journey-heading");
    const title = element("h2", route ? "步行参考路线" : "查询结果"); title.id = "journey-title"; title.tabIndex = -1;
    const controls = element('div',undefined,'journey-heading-actions');
    if (route?.phase === 'ready') {
      const toggle=button(routeCompact ? '展开' : '收起',() => {
        routeCompact=!routeCompact; render();
        document.querySelector('.route-card-toggle')?.focus({preventScroll:true});
      });
      toggle.classList.add('route-card-toggle'); toggle.setAttribute('aria-label',routeCompact ? '展开路线卡片' : '收起路线卡片');
      toggle.setAttribute('aria-expanded',String(!routeCompact)); toggle.setAttribute('aria-controls','journey-body');
      controls.append(toggle);
    }
    controls.append(button("查看全部地点", all)); head.append(title,controls); card.append(head);
    const body = element("div", undefined, "journey-body"); body.id='journey-body'; card.append(body);
    let placeDetails = null;
    const ambiguous = result.result_status === "needs_clarification" || result.teachers.length > 1 || result.services.length > 1;
    if (ambiguous) {
      body.append(element("p", "请选择你要找的结果", "journey-hint"));
      for (const teacher of result.teachers) body.append(button(`${teacher.name} · ${teacher.department} · ${teacher.office || "办公室暂未收录"}`, () => {
        present({teachers: [teacher], places: linkedTeacher(teacher, [...result.places, ...places].filter((p, i, a) => a.findIndex((x) => x.place_id === p.place_id) === i)), result_status: "success"}, result.source);
      }));
      for (const service of result.services) body.append(button(service.name, () => {
        const ids = new Set(service.steps.flatMap((s) => s.place_ids || []));
        present({services: [service], places: result.places.filter((p) => ids.has(p.place_id)), result_status: "success"}, result.source);
      }));
    } else {
      for (const teacher of result.teachers) {
        body.append(element("h3", teacher.name), element("p", teacher.office || "办公室暂未收录", "teacher-location"));
      }
      for (const service of result.services) {
        body.append(element("h3", service.name));
        if (!route) {
          const steps = element("ol", undefined, "journey-steps");
          service.steps.slice(0, 3).forEach((step) => steps.append(element("li", step.instruction)));
          body.append(steps, button("完整办理步骤", () => showService(service)));
        }
      }
    }
    if (!ambiguous && target) {
      body.append(element("h3", target.name), element("p", target.campus || "校园地点", "detail-meta"));
      if (!located(target)) body.append(element("p", "地图位置暂未收录。", "journey-hint"));
      else if (!route) body.append(button("查看路线", startRoute, true));
      const details = element("details", undefined, "source-details"); details.append(element("summary", "地点资料与高德入口"));
      if (target.address_detail) details.append(element("p", target.address_detail));
      for (const note of target.notes || []) details.append(element("p", note));
      if (target.position) {
        externalLink(details, target.position.source_url, "打开高德地点 ↗", (u) => u.hostname === "ditu.amap.com" && /^\/place\/[A-Za-z0-9]+$/.test(u.pathname));
        if (target.navigation_url) externalLink(details, target.navigation_url, "高德导航 ↗", (u) => u.hostname === "uri.amap.com" && u.pathname === "/navigation");
      }
      const ids = new Set((target.field_evidence || []).flatMap((f) => f.evidence_ids));
      for (const source of placeSources.filter((s) => ids.has(s.evidence_id))) details.append(officialLink(source.source_url, source.source_reference));
      placeDetails = details;
    } else if (!ambiguous && !result.places.length) body.append(element("p", result.provider_error ? "高德地点搜索暂不可用。" : result.result_status === "empty" ? "没有找到匹配结果，请换个名称。" : "地图位置暂未收录。", "journey-hint"));
    if ((!ambiguous || (!result.teachers.length && !result.services.length)) && result.places.length > 1) {
      const choices = element("div", undefined, "journey-choices");
      for (const p of result.places) choices.append(button(p.name + (located(p) ? "" : " · 位置暂未收录"), () => select(p)));
      body.append(choices);
    }
    if (route) renderRoute(body);
    if (!route && result.source === "amap") body.append(button("重试高德搜索", MapDiscovery.retry), button("地图选目的地", MapDiscovery.pick));
    else if (!route && result.source === "places" && $("place-query").value.trim()) body.append(button("搜索更多高德地点", () => MapDiscovery.search()));
    if (placeDetails) body.append(placeDetails);
    const actions = element("div", undefined, "journey-actions");
    if (result.source === "assistant") actions.append(button("返回对话", () => {openPanel("assistant"); $("messages").scrollTop = chatScroll;}));
    if (result.source === "teachers") actions.append(button("返回教师查询", () => openPanel("teacher-panel")));
    card.append(actions);
    // Refit geometry using the actual overlay height on both desktop and phone.
    requestAnimationFrame(() => sendToMap({action: "route-insets", bottom: card.offsetHeight + 24}));
  }
  function startRoute() {
    if (!located(target)) return;
    invalidateRoute(); route = {phase: "origin", origin: null, originName: "", message: "选择出发地点"}; render();
  }
  function renderRoute(body) {
    const box = element("section", undefined, "route-box"); box.setAttribute("aria-label", "步行路线");
    const status = element("p", route.message, "route-status"); status.setAttribute("role", "status"); box.append(status);
    if (route.phase === "ready") {
      box.append(element("strong", `${route.distance < 1000 ? Math.round(route.distance) + " 米" : (route.distance / 1000).toFixed(1) + " 公里"} · 约 ${Math.max(1, Math.ceil(route.time / 60))} 分钟`, "route-summary"));
      box.append(element("p", `${route.originName} → ${target.name}`, "detail-meta"));
      box.append(element("div", undefined, "guidance-slot"));
      const start = button("开始步行引导", () => Guidance.start({requestId:routeSequence, route, target,
        detail:result.teachers.map(t => t.office || "").filter(Boolean).join("；") || result.services[0]?.name || "",
        replan:(origin) => plan(origin, "我的位置")}), true); start.classList.add("start-guidance"); start.disabled=!!route.mapUnavailable; box.append(start);
      box.append(element("p", route.mapUnavailable ? "地图暂不可用，可继续查看分步指引。" : "前台持续定位；切换页面或锁屏时暂停。", "route-guidance-note"));
      const details = element("details", undefined, "route-instructions"); details.append(element("summary", "分步指引"));
      details.open=!!route.mapUnavailable;
      const list = element("ol"); route.steps.forEach((s) => list.append(element("li", s))); details.append(list); box.append(details);
      const options = element("div", undefined, "route-options");
      options.append(button("更换起点", startRoute), button("重新规划", () => plan(route.origin, route.originName))); box.append(options);
    } else {
      const controls = element("div", undefined, "origin-controls");
      controls.append(button("我的位置", locate), button(route.phase === "picking" ? "请点击地图选择起点" : "地图选点", pick));
      const label = element("label", "校园地点起点"); label.htmlFor = "route-origin";
      const selectOrigin = element("select"); selectOrigin.id = "route-origin";
      const empty = element("option", "选择校园地点…"); empty.value = ""; selectOrigin.append(empty);
      for (const p of places.filter(located)) {const o = element("option", p.name); o.value = p.place_id; selectOrigin.append(o);}
      selectOrigin.addEventListener("change", () => {const p = places.find((p) => p.place_id === selectOrigin.value); if (p) plan(p.position, p.name);});
      controls.append(label, selectOrigin); box.append(controls);
      if (route.phase === "error" && route.origin) box.append(button("重试路线", () => plan(route.origin, route.originName), true));
    }
    box.append(button("退出路线", exitRoute)); body.append(box);
    if (route.phase === 'ready') Guidance.render();
  }
  function exitRoute() {invalidateRoute(); focusTarget(); render();}
  function plan(origin, name) {
    if (!route || !located(target)) return;
    Guidance.stop(); routeCompact=false;
    clearTimeout(routeTimer); const id = ++routeSequence;
    sendToMap({action: "route-clear", request_id: id});
    route = {phase: "loading", origin, originName: name, message: mapState === "ready" ? "正在规划步行路线…" : "正在等待地图…"};
    pendingRoute = {action: "route-request", request_id: id, origin, destination_place_id: target.place_id};
    if (mapState === "ready") {sendToMap(pendingRoute); pendingRoute = null;}
    else if (mapState !== "loading") {route.phase = "error"; route.message = "地图暂不可用，可更换起点或稍后重试。"; pendingRoute = null;}
    routeTimer = setTimeout(() => {
      if (id !== routeSequence || !route || route.phase !== "loading") return;
      routeSequence++; pendingRoute = null; sendToMap({action: "route-clear", request_id: routeSequence});
      route.phase = "error"; route.message = "路线等待超时，请重试。"; render();
    }, 35000);
    render();
  }
  function locate() {
    if (!route) return;
    invalidatePending(); const id = routeSequence;
    if (!navigator.geolocation) {route.message = "浏览器不支持定位，请选择校园地点或地图选点。"; render(); return;}
    route.phase = "locating"; route.message = "正在获取当前位置…"; render();
    navigator.geolocation.getCurrentPosition((position) => {
      if (!route || id !== routeSequence) return;
      plan({longitude: position.coords.longitude, latitude: position.coords.latitude, coordinate_system: "WGS84"}, "我的位置");
    }, () => {
      if (!route || id !== routeSequence) return;
      route.phase = "origin"; route.message = "无法获取当前位置，请选择校园地点或地图选点。"; render();
    }, {enableHighAccuracy: true, timeout: 10000, maximumAge: 30000});
  }
  function invalidatePending() {
    clearTimeout(routeTimer); routeSequence++; pendingRoute = null;
    sendToMap({action: "route-clear", request_id: routeSequence});
  }
  function pick() {
    if (!route) return;
    invalidatePending();
    if (mapState !== "ready") {route.message = "地图尚未就绪，请选择校园地点起点。"; render(); return;}
    route.phase = "picking"; route.message = "点击地图上的出发位置"; render();
    sendToMap({action: "route-pick", request_id: routeSequence});
  }
  function receive(data) {
    if (!route || data.request_id !== routeSequence) return;
    if (data.action === "route-origin" && route.phase === "picking") plan(data.position, data.name || "地图选点");
    if (data.action === "route-result" && route.phase === "loading") {
      clearTimeout(routeTimer);
      if (data.status === "success" && Number.isFinite(data.distance) && Number.isFinite(data.time) && Array.isArray(data.steps)) {
        route.phase = "ready"; route.distance = data.distance; route.time = data.time; route.steps = data.steps;
        route.geometry = data.geometry; route.stepEnds = data.step_ends;
        route.message = "参考路线 · 步行至建筑";
      } else {route.phase = "error"; route.message = "暂未取得步行路线，请更换起点或重试。";}
      render();
    }
  }
  function ready() {
    if (result) focusTarget();
    if (route?.mapUnavailable) {plan(route.origin,route.originName); return;}
    if (pendingRoute) {sendToMap(pendingRoute); pendingRoute = null;}
  }
  function failed() {
    if (!route) return;
    Guidance.stop(); routeCompact=false; invalidatePending();
    if (route.phase === 'ready') {route.mapUnavailable=true; route.message='地图暂不可用，已保留分步指引。';}
    else {route.phase = "error"; route.message = "地图加载失败，请稍后重试。";}
    render();
  }
  function all(reset = true) {
    begin(); result = null; target = null; $("journey-card").hidden = true;
    $("map-stage").classList.remove("journey-active"); $("place-detail").hidden = true;
    if (reset) {$("place-query").value = ""; clearCategory();}
    renderPlaces(places);
  }
  return {begin, present, select, receive, ready, failed, all, located, exitRoute, refresh:render,
    active: () => !!result, current: (id) => id === epoch,
    saveChat: () => {chatScroll = $("messages").scrollTop;}};
})();
