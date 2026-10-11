// Map panel: real AMap through the sandboxed /map-view frame when configured, otherwise
// a schematic SVG of recorded points. Personal positions stay in the browser: they are
// only posted to the same-origin map frame for AMap.Walking, never to /api.
import { h } from "./dom.mjs";
import { hasPosition, matchesFilter, projector } from "./places.mjs";

const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };

export function createMap({ frame, fallback, status, onSelect }) {
  const generation = Math.floor(Math.random() * 1e9);
  let mode = "loading", places = [], filter = "all", selected = null, routeSeq = 0, pendingRoute = null;
  const send = (data) => frame.contentWindow?.postMessage({ type: "campuspilot-map", ...data, frame_generation: generation }, location.origin);
  window.sendToMap = send; // guidance.js (classic script) talks to the frame through this global

  const visible = () => places.filter((p) => matchesFilter(p, filter));
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
    focus(place) {
      selected = place.place_id;
      if (mode === "amap" && hasPosition(place)) send({ action: "center", place_id: place.place_id, position: place.position });
      else push();
    },
    get ready() { return mode === "amap"; },
    /** Walking route from the browser's own position (asked only on click). */
    route(place) {
      return new Promise((resolve) => {
        if (mode !== "amap") { selected = place.place_id; push(); return resolve({ status: "unavailable", message: "步行路线需要高德地图；已在示意图上标出目的地" }); }
        if (!navigator.geolocation) return resolve({ status: "error", message: "当前浏览器无法定位" });
        navigator.geolocation.getCurrentPosition((fix) => {
          const origin = { longitude: fix.coords.longitude, latitude: fix.coords.latitude, coordinate_system: "WGS84" };
          routeSeq += 1; pendingRoute = resolve;
          send({ action: "route-request", request_id: routeSeq, origin, destination_place_id: place.place_id });
        }, () => resolve({ status: "error", message: "定位未允许，可在地图上查看目的地" }), { enableHighAccuracy: true, timeout: 10000 });
      });
    },
    get routeId() { return routeSeq; },
  };
}

export function legend() {
  return h("p", { class: "map-legend" }, "地点为建筑参考点，需现场核实入口。");
}
