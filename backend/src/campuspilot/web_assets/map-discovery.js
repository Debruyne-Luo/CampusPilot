"use strict";
// Provider discoveries are transient destinations; they never alter school business records.
const MapDiscovery = (() => {
  let sequence = 0, pending = null, timer = null, picking = false, lastQuery = "";
  function status(text, retry = false) {
    const box = $("map-discovery-status"); box.replaceChildren(); box.hidden = !text;
    if (!text) return;
    box.append(document.createTextNode(text));
    if (retry) {const b = element("button", "重试"); b.type = "button"; b.addEventListener("click", () => {if (mapState === 'failed') restartMap(); search(lastQuery);}); box.append(b);}
    const close = element("button", "取消"); close.type = "button"; close.addEventListener("click", cancel); box.append(close);
  }
  function cancel() {
    clearTimeout(timer); pending = null; picking = false; sequence++;
    $("map-pick-destination").setAttribute("aria-pressed", "false");
    status(""); sendToMap({action:"discovery-cancel", request_id:sequence});
  }
  function search(query = $("place-query").value.trim()) {
    if (!query.trim()) {status("输入一个地点名称，再搜索校园及周边高德地点。"); return;}
    Journey.all(false);
    const ticket = Journey.begin(); const id = ++sequence; lastQuery = query.slice(0,120);
    pending = {action:"place-search", request_id:id, query:lastQuery, ticket};
    status(mapState === "loading" ? "等待地图后搜索高德地点…" : "正在搜索校园及周边高德地点…");
    if (mapState === "ready") sendToMap(pending);
    else if (mapState !== "loading") {pending = null; status("地图暂不可用，可查询已收录目录。", true); return;}
    timer = setTimeout(() => {
      if (!pending || id !== sequence) return;
      cancel(); status("高德地点搜索超时，请重试。", true);
    }, 22000);
  }
  function pick() {
    if (picking) {cancel(); return;}
    Journey.begin(); Journey.refresh();
    picking = true; sequence++;
    $("map-pick-destination").setAttribute("aria-pressed", "true");
    status("点击地图上的目的地；地图文字地点也可直接点击。");
    sendToMap({action:"destination-pick", request_id:sequence});
  }
  function providerPlace(value) {
    const position = value?.position;
    if (!Journey.located(value) || Math.abs(position.longitude) > 180 || Math.abs(position.latitude) > 90 ||
        typeof value.name !== "string" || !value.name.trim() || !/^[A-Za-z0-9]{8,32}$/.test(value.poi_id || "")) return null;
    const url = "https://ditu.amap.com/place/" + value.poi_id;
    return {place_id:"amap:poi:" + value.poi_id, name:value.name.slice(0,120), aliases:[],
      campus:"校园及周边 · 高德地点", category:"service", address_detail:String(value.address || "").slice(0,300),
      notes:[], field_evidence:[], provider:"amap", position:{...position, source_url:url, verification_status:"provider_candidate"}};
  }
  function receive(data) {
    if (data.action === "place-search-result") {
      if (!pending || data.request_id !== sequence || !Journey.current(pending.ticket)) return;
      const ticket = pending.ticket; pending = null; clearTimeout(timer); status("");
      const records = (Array.isArray(data.places) ? data.places.slice(0,10) : []).map(providerPlace).filter(Boolean);
      Journey.present({places:records, result_status:records.length === 1 ? "success" : records.length ? "needs_clarification" : "empty", provider_error:data.status === "error"}, "amap", ticket);
    } else if (data.action === "poi-selection") {
      if (data.request_id !== sequence) return;
      const place = providerPlace(data.place);
      if (place) {cancel(); Journey.select(place);}
      else status("暂未取得该地点资料，可使用地图选目的地。");
    } else if (data.action === "map-destination") {
      if (!picking || data.request_id !== sequence || !Journey.located({position:data.position})) return;
      const point = data.position;
      if (Math.abs(point.longitude) > 180 || Math.abs(point.latitude) > 90) return;
      const place = {place_id:"map:point:" + sequence, name:"地图选定地点", aliases:[], category:"service",
        campus:"地图选点", notes:[], field_evidence:[], provider:"map_point", position:{...point, verification_status:"map_selection"}};
      cancel(); Journey.select(place);
    }
  }
  $("map-pick-destination").addEventListener("click", pick);
  function failed() {
    if (!pending && !picking) return;
    cancel(); status('地图未能加载，可使用已收录目录。',!!lastQuery);
  }
  return {search, pick, cancel, receive, failed,
    ready: () => {if (pending) sendToMap(pending); else sendToMap({action:'discovery-cancel',request_id:sequence});},
    retry: () => {if (mapState === 'failed') restartMap(); search(lastQuery);}};
})();
