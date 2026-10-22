// Map categories and place helpers (pure).
export const FILTERS = [
  { id: "all", label: "全部" },
  { id: "building", label: "教学楼宇" },
  { id: "office", label: "办公" },
  { id: "dining", label: "食堂" },
  { id: "parcel", label: "快递" },
  { id: "service", label: "服务" },
];
export function hasPosition(p) {
  const q = p?.position;
  return !!q && q.coordinate_system === "GCJ02" && Number.isFinite(q.longitude) && Number.isFinite(q.latitude);
}
export function matchesFilter(place, id) {
  const tags = place.tags || [];
  switch (id) {
    case "all": return true;
    case "building": return ["teaching", "library"].includes(place.category);
    case "office": return place.category === "office";
    case "dining": return place.category === "dining" || tags.includes("food");
    case "parcel": return tags.includes("parcel");
    case "service": return place.category === "service" && !tags.includes("parcel");
    default: return false;
  }
}
/** Linear projection of GCJ02 points into an SVG box (schematic fallback when AMap is off). */
export function projector(places, width, height, pad = 40) {
  const pts = places.filter(hasPosition).map((p) => p.position);
  if (!pts.length) return () => null;
  const xs = pts.map((p) => p.longitude), ys = pts.map((p) => p.latitude);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (width - 2 * pad) / (x1 - x0 || 1), sy = (height - 2 * pad) / (y1 - y0 || 1), s = Math.min(sx, sy);
  const ox = (width - (x1 - x0) * s) / 2, oy = (height - (y1 - y0) * s) / 2;
  return (pos) => (pos ? { x: ox + (pos.longitude - x0) * s, y: height - (oy + (pos.latitude - y0) * s) } : null);
}
/**
 * Places drawn on the map. "全部" keeps it uncluttered: hotspot places plus places the
 * current answer (or a search) referenced and the selected one. A category chip shows
 * every place of that category.
 */
export function visiblePlaces(places, filter = "all", extraIds = new Set(), selected = null) {
  if (filter !== "all") return places.filter((p) => matchesFilter(p, filter));
  return places.filter((p) => p.hotspot === true || extraIds.has(p.place_id) || p.place_id === selected);
}
const fold = (s) => String(s || "").toLowerCase().replace(/\s+/g, "");
/** Local search over names and aliases: exact > prefix > substring; at most `limit`. */
export function searchPlaces(places, query, limit = 8) {
  const q = fold(query);
  if (!q) return [];
  const score = (p) => Math.min(...[p.name, ...(p.aliases || [])].map((n) => { const f = fold(n); return f === q ? 0 : f.startsWith(q) ? 1 : f.includes(q) ? 2 : 9; }));
  return places.map((p, i) => [score(p), i, p]).filter(([s]) => s < 9).sort((a, b) => a[0] - b[0] || a[1] - b[1]).slice(0, limit).map(([, , p]) => p);
}
const TRANSIT = /公交|地铁|车站|站台|停车场|出入口|加油站|充电站/;
/**
 * AMap POIs shown after our own places: transit/parking POIs dropped, duplicates of our
 * places dropped, exact name matches first, then prefix, then the rest in AMap order.
 */
export function rankPois(pois, local, query) {
  const q = fold(query), ours = local.flatMap((p) => [p.name, ...(p.aliases || [])]).map(fold);
  const rank = (n) => (n === q ? 0 : n.startsWith(q) ? 1 : 2);
  return (pois || [])
    .filter((p) => p && !TRANSIT.test(String(p.name || "")) && !/交通设施|公交|地铁|停车/.test(String(p.type || "")))
    .filter((p) => { const n = fold(p.name); return !ours.some((o) => o === n || n.endsWith(o) || o.endsWith(n)); })
    .map((p, i) => [rank(fold(p.name)), i, p]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(([, , p]) => p);
}
/** Pin glyph for a place: parcel box, medical cross, campus card, bowl, book, building. */
export function glyphFor(place) {
  const tags = place?.tags || [], name = String(place?.name || "");
  if (tags.includes("parcel")) return "parcel";
  if (/医院|医务室|卫生/.test(name)) return "medical";
  if (/一卡通|校园卡/.test(name)) return "card";
  if (place?.category === "dining" || tags.includes("food")) return "dining";
  if (place?.category === "library") return "library";
  if (place?.category === "teaching") return "teaching";
  if (place?.category === "office") return "office";
  return "service";
}
/** Places listed under a category chip ("全部" lists none: the map stays the overview). */
export function filterList(places, id, limit = 30) {
  if (id === "all") return [];
  return places.filter((p) => hasPosition(p) && matchesFilter(p, id))
    .sort((a, b) => (b.hotspot === true) - (a.hotspot === true)).slice(0, limit);
}
