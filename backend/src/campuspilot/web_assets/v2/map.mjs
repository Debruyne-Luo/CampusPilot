// Map panel: real AMap through the sandboxed /map-view frame when configured, otherwise
// a schematic SVG of recorded points. Personal positions stay in the browser: they are
// only posted to the same-origin map frame for AMap.Walking, never to /api.
import { h } from "./dom.mjs";
import { glyphFor, hasPosition, projector, visiblePlaces } from "./places.mjs";

const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

export function createMap({ frame, fallback, status, onSelect, onOrigin = () => {}, onPoi = () => {}, onArrive = () => {}, onGuide = () => {} }) {
  const generation = Math.floor(Math.random() * 1e9);
  let mode = "loading", places = [], filter = "all", selected = null, routeSeq = 0, pendingRoute = null;
  let extra = new Set(), searchSeq = 0, pendingSearch = null, fit = true, cameraSeq = 0;
  let preferences = {desktop:matchMedia('(min-width:1280px)').matches,reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches}, viewport = null;
  const send = (data) => frame.contentWindow?.postMessage({ type: "campuspilot-map", ...data, frame_generation: generation }, location.origin);
  window.sendToMap = send; // guidance.js (classic script) talks to the frame through this global

  const visible = () => {
    const list = visiblePlaces(places, filter, extra, selected);
    const current = places.find(p=>p.place_id===selected);
    return preferences.desktop && current && !list.includes(current) ? [...list,current] : list;
  };
  function drawFallback() {
    const W = 1000, H = 700, list = visible(), project = projector(places, W, H, 70);
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "schematic", role: "img", "aria-label": "校园地点示意图（未接入高德地图）" });
    for (let i = 1; i < 6; i++) svg.append(svgEl("line", { x1: 0, y1: i * 120, x2: W, y2: i * 120 - 20, class: "road" }), svgEl("line", { x1: i * 170, y1: 0, x2: i * 170 + 15, y2: H, class: "road" }));
    for (const p of [...list].sort((a, b) => (a.place_id === selected) - (b.place_id === selected))) {
      const pt = project(p.position); if (!pt) continue;
      const g = svgEl("g", { class: `marker ${p.place_id === selected ? "selected" : ""}`, tabindex: "0", role: "button", "aria-label": p.name });
      g.append(svgEl("circle", { cx: pt.x, cy: pt.y, r: p.place_id === selected ? 12 : 8 }));
      if (p.place_id === selected || list.length <= 14) { const t = svgEl("text", { x: pt.x + 16, y: pt.y + 5 }); t.textContent = p.name; g.append(t); }
      else { const t = svgEl("title", {}); t.textContent = p.name; g.append(t); }
      const pick = () => onSelect(p); g.addEventListener("click", pick); g.addEventListener("keydown", (e) => e.key === "Enter" && pick());
      svg.append(g);
    }
    fallback.replaceChildren(svg);
  }
  function push() {
    if (mode === "amap") send({ action: "places", places: visible().map((p) => ({ place_id: p.place_id, name: p.name, category: p.category, tags: p.tags || [], position: p.position, glyph: glyphFor(p) })), selected_place_id: selected, fit:preferences.desktop?false:fit });
    else if (mode === "fallback") drawFallback();
    fit = true;
  }
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin || event.source !== frame.contentWindow || event.data?.type !== "campuspilot-map") return;
    const d = event.data;
    if (d.action !== "frame-ready" && d.frame_generation !== generation) return;
    if (d.action === "frame-ready" && mode === "loading" && config) send({ action: "init", config });
    else if (d.action === "ready") { mode = "amap"; status(""); send({action:'preferences',...preferences});if(viewport)send({action:'viewport-insets',...viewport}); push(); }
    else if (d.action === "failed") useFallback("底图加载失败，显示示意图");
    else if (d.action === "select") { const p = places.find((x) => x.place_id === d.place_id); if (p) onSelect(p); }
    else if (d.action === "route-origin" && d.request_id === routeSeq) onOrigin(d.position, d.name);
    else if (d.action === "poi-selection" && d.place) onPoi(d.place);
    else if (d.action === "place-search-result" && pendingSearch && d.request_id === searchSeq) { pendingSearch(d.status === "success" ? d.places : []); pendingSearch = null; }
    else if (d.action === "route-result" && pendingRoute && d.request_id === routeSeq) { pendingRoute(d); pendingRoute = null; }
    else if (d.action === "guidance-position") window.Guidance?.receive(d);
    else if (d.action === "dino-arrived") onArrive();
    else if (d.action === "dino-ready") onGuide(d.kind);
    else if (d.action === "dino-progress") window.Guidance?.receiveDemo(d);
    else if (d.action === "dino-failed") {window.Guidance?.stop();status("引导模型暂不可用，可重新开始路线演示。");}
  });
  let config = null;
  function cancelPending() {if(pendingRoute){pendingRoute({status:'cancelled'});pendingRoute=null;}}
  function useFallback(message) { mode = "fallback"; frame.hidden = true; fallback.hidden = false; status(message); push(); }

  return {
    preferences(value) {preferences=value;if(mode==='amap')send({action:'preferences',...value});},
    viewportInsets(value) {viewport=value;if(mode==='amap')send({action:'viewport-insets',...value});},
    resize() {if(mode==='amap')send({action:'resize'});},
    layout(changing) {if(mode==='amap')send({action:'layout',changing});},
    overview() {if(mode==='amap')send({action:'overview',operation_id:++cameraSeq});},
    clearSelection() {selected=null;cameraSeq++;cancelPending();routeSeq++;if(mode==='amap'){send({action:'selection',place_id:null,operation_id:cameraSeq});send({action:'route-clear',request_id:routeSeq});}else push();},
    async init(list) {
      places = list;
      try {
        const res = await fetch("/api/map-config");
        const c = await res.json();
        if (c.configured && c.key) { config = { key: c.key }; send({ action: "ping" }); setTimeout(() => mode === "loading" && useFallback("底图加载超时，显示示意图"), 15000); }
        else useFallback("未配置高德地图密钥：显示地点示意图，步行路线需要高德地图");
      } catch { useFallback("地图配置读取失败，显示示意图"); }
    },
    setFilter(id) { filter = id; push(); },
    /** Places referenced by the current answer or a search are drawn in addition to hotspots. */
    reveal(ids) { for (const id of ids) extra.add(id); push(); },
    /** AMap POI search near campus (frame-side); resolves [] when the map is unavailable. */
    searchPoi(query) {
      if (mode !== "amap") return Promise.resolve([]);
      if (pendingSearch) pendingSearch([]);
      return new Promise((resolve) => { searchSeq += 1; pendingSearch = resolve; send({ action: "place-search", request_id: searchSeq, query }); setTimeout(() => { if (pendingSearch === resolve) { pendingSearch = null; resolve([]); } }, 8000); });
    },
    focus(place) {
      if(preferences.desktop){cancelPending();routeSeq++;if(mode==='amap')send({action:'route-clear',request_id:routeSeq});}
      if(place.place_id&&!places.some(p=>p.place_id===place.place_id)&&hasPosition(place))places.push(place);
      const known = extra.has(place.place_id) || place.hotspot === true;
      selected = place.place_id; extra.add(place.place_id);
      if (mode === "amap" && hasPosition(place)) {
        if (!known || preferences.desktop) { fit = false; push(); }
        send({ action: "center", place_id: place.place_id, position: place.position, operation_id:++cameraSeq });
      } else push();
    },
    get ready() { return mode === "amap"; },
    /** Walking route from an explicit origin (GPS or user-chosen) to a place or a POI/point. */
    route(target, origin) {
      return new Promise((resolve) => {
        cancelPending();
        if (mode !== "amap") { if (target.place_id) { selected = target.place_id; push(); } return resolve({ status: "unavailable", message: "步行路线需要高德地图；已在示意图上标出目的地" }); }
        if (!origin) return resolve({ status: "need_origin" });
        routeSeq += 1; pendingRoute = resolve;
        const requestId=routeSeq;
        setTimeout(()=>{if(pendingRoute===resolve&&routeSeq===requestId){pendingRoute=null;routeSeq++;send({action:'route-clear',request_id:routeSeq});resolve({status:'error',message:'路线请求超时，请重试。'});}},20000);
        send({ action: "route-request", request_id: routeSeq, origin, operation_id:++cameraSeq,
          ...(target.place_id ? { destination_place_id: target.place_id } : { destination_position: target.position }) });
      });
    },
    /** Next map click (or marker) becomes the route origin; answered through onOrigin. */
    pickOrigin() { if (mode !== "amap") return false; cancelPending();routeSeq += 1; send({ action: "route-pick", request_id: routeSeq }); return true; },
    /** Use the map point under the on-screen crosshair (frame pixels) as the origin. */
    pickAt(x, y) { if (mode === "amap") send({ action: "route-pick-point", request_id: routeSeq, x, y }); },
    cancelPick() { cancelPending();routeSeq += 1; send({ action: "route-clear", request_id: routeSeq }); },
    heading(rotation) { if (mode === "amap") send({ action: "heading", ...rotation, arrow: rotation.arrow, rotation: rotation.map, heading_value: rotation.value }); },
    /** Start the 理小龙 guide on the current route: demo walks by itself, else follows GPS. */
    dino(demo, speed, guide) { if (mode === "amap") send({ action: "dino-start", demo, speed, guide }); },
    dinoStop() { if (mode === "amap") send({ action: "dino-stop" }); },
    dinoMode(demo, speed) { if (mode === "amap") send({ action: "dino-mode", demo, speed }); },
    centerOn(position) { if (mode === "amap" && position) send({ action: "center", place_id: null, position, operation_id:++cameraSeq }); },
    northUp() { if (mode === "amap") send({ action: "north-up" }); },
    insets(bottom) { if (mode === "amap") send({ action: "route-insets", bottom }); },
    get routeId() { return routeSeq; },
  };
}
