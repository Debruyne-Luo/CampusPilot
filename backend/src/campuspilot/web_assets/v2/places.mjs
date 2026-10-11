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
