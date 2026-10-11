// Map panel: real AMap through the sandboxed /map-view frame when configured, otherwise
// a schematic SVG of recorded points. Personal positions stay in the browser: they are
// only posted to the same-origin map frame for AMap.Walking, never to /api.
import { h } from "./dom.mjs";
import { hasPosition, projector, visiblePlaces } from "./places.mjs";

const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

export function createMap({ frame, fallback, status, onSelect, onOrigin = () => {}, onPoi = () => {} }) {
  const generation = Math.floor(Math.random() * 1e9);
  let mode = "loading", places = [], filter = "all", selected = null, routeSeq = 0, pendingRoute = null;
  let extra = new Set(), searchSeq = 0, pendingSearch = null;
  const send = (data) => frame.contentWindow?.postMessage({ type: "campuspilot-map", ...data, frame_generation: generation }, location.origin);
  window.sendToMap = send; // guidance.js (classic script) talks to the frame through this global

  const visible = () => visiblePlaces(places, filter, extra, selected);
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
    if (mode === "amap") send({ action: "places", places: visible(), selected_place_id: selected });
    else if (mode === "fallback") drawFallback();
  }
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin || event.source !== frame.contentWindow || event.data?.type !== "campuspilot-map") return;
    const d = event.data;
    if (d.action !== "frame-ready" && d.frame_generation !== generation) return;
    if (d.action === "frame-ready" && mode === "loading" && config) send({ action: "init", config });
    else if (d.action === "ready") { mode = "amap"; status(""); push(); }
    else if (d.action === "failed") useFallback("底图加载失败，显示示意图");
    else if (d.action === "select") { const p = places.find((x) => x.place_id === d.place_id); if (p) onSelect(p); }
    else if (d.action === "route-origin" && d.request_id === routeSeq) onOrigin(d.position, d.name);
    else if (d.action === "poi-selection" && d.place) onPoi(d.place);
    else if (d.action === "place-search-result" && pendingSearch && d.request_id === searchSeq) { pendingSearch(d.status === "success" ? d.places : []); pendingSearch = null; }
    else if (d.action === "route-result" && pendingRoute && d.request_id === routeSeq) { pendingRoute(d); pendingRoute = null; }
    else if (d.action === "guidance-position") window.Guidance?.receive(d);
  });
  let config = null;
  function useFallback(message) { mode = "fallback"; frame.hidden = true; fallback.hidden = false; status(message); push(); }

  return {
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
      const known = extra.has(place.place_id) || place.hotspot === true;
      selected = place.place_id; extra.add(place.place_id);
      if (mode === "amap" && hasPosition(place)) {
        if (!known) push(); // draw it first; "center" then highlights the new marker
        send({ action: "center", place_id: place.place_id, position: place.position });
      } else push();
    },
    get ready() { return mode === "amap"; },
    /** Walking route from an explicit origin (GPS or user-chosen) to a place or a POI/point. */
    route(target, origin) {
      return new Promise((resolve) => {
        if (mode !== "amap") { if (target.place_id) { selected = target.place_id; push(); } return resolve({ status: "unavailable", message: "步行路线需要高德地图；已在示意图上标出目的地" }); }
        if (!origin) return resolve({ status: "need_origin" });
        routeSeq += 1; pendingRoute = resolve;
        send({ action: "route-request", request_id: routeSeq, origin,
          ...(target.place_id ? { destination_place_id: target.place_id } : { destination_position: target.position }) });
      });
    },
    /** Next map click (or marker) becomes the route origin; answered through onOrigin. */
    pickOrigin() { if (mode !== "amap") return false; routeSeq += 1; send({ action: "route-pick", request_id: routeSeq }); return true; },
    cancelPick() { routeSeq += 1; send({ action: "route-clear", request_id: routeSeq }); },
    heading(rotation) { if (mode === "amap") send({ action: "heading", ...rotation, arrow: rotation.arrow, rotation: rotation.map }); },
    centerOn(position) { if (mode === "amap" && position) send({ action: "center", place_id: null, position }); },
    northUp() { if (mode === "amap") send({ action: "north-up" }); },
    insets(bottom) { if (mode === "amap") send({ action: "route-insets", bottom }); },
    get routeId() { return routeSeq; },
  };
}

export function legend() {
  return h("p", { class: "map-legend" }, "地点为建筑参考点，需现场核实入口。");
}
