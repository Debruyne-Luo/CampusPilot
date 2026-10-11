// Geodesy helpers (pure): WGS84→GCJ02 so browser GPS fixes line up with AMap/GCJ02 places,
// great-circle distance and nearest-first ranking of "去哪办" places.
const A = 6378245.0, EE = 0.00669342162296594323;
function outOfChina(lng, lat) { return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271; }
function tLat(x, y) {
  let r = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  r += ((20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2) / 3;
  r += ((20 * Math.sin(y * Math.PI) + 40 * Math.sin((y / 3) * Math.PI)) * 2) / 3;
  r += ((160 * Math.sin((y / 12) * Math.PI) + 320 * Math.sin((y * Math.PI) / 30)) * 2) / 3;
  return r;
}
function tLng(x, y) {
  let r = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  r += ((20 * Math.sin(6 * x * Math.PI) + 20 * Math.sin(2 * x * Math.PI)) * 2) / 3;
  r += ((20 * Math.sin(x * Math.PI) + 40 * Math.sin((x / 3) * Math.PI)) * 2) / 3;
  r += ((150 * Math.sin((x / 12) * Math.PI) + 300 * Math.sin((x / 30) * Math.PI)) * 2) / 3;
  return r;
}
export function validPosition(p) {
  return !!p && ["GCJ02", "WGS84"].includes(p.coordinate_system) && Number.isFinite(p.longitude) && Number.isFinite(p.latitude) &&
    Math.abs(p.longitude) <= 180 && Math.abs(p.latitude) <= 90;
}
/** Any valid position as GCJ02 (WGS84 converted locally; outside China unchanged). */
export function toGcj02(p) {
  if (!validPosition(p)) return null;
  if (p.coordinate_system === "GCJ02") return { longitude: p.longitude, latitude: p.latitude, coordinate_system: "GCJ02" };
  const { longitude: lng, latitude: lat } = p;
  if (outOfChina(lng, lat)) return { longitude: lng, latitude: lat, coordinate_system: "GCJ02" };
  let dLat = tLat(lng - 105, lat - 35), dLng = tLng(lng - 105, lat - 35);
  const rad = (lat / 180) * Math.PI, m = 1 - EE * Math.sin(rad) ** 2, s = Math.sqrt(m);
  dLat = (dLat * 180) / (((A * (1 - EE)) / (m * s)) * Math.PI);
  dLng = (dLng * 180) / ((A / s) * Math.cos(rad) * Math.PI);
  return { longitude: lng + dLng, latitude: lat + dLat, coordinate_system: "GCJ02" };
}
/** Haversine metres between two positions (both converted to GCJ02 first). */
export function distanceMeters(a, b) {
  const p = toGcj02(a), q = toGcj02(b);
  if (!p || !q) return null;
  const R = 6371008.8, r = Math.PI / 180;
  const dLat = (q.latitude - p.latitude) * r, dLng = (q.longitude - p.longitude) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(p.latitude * r) * Math.cos(q.latitude * r) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}
export function formatDistance(m) {
  if (!Number.isFinite(m)) return "";
  return m < 1000 ? `${Math.max(10, Math.round(m / 10) * 10)} 米` : `${(m / 1000).toFixed(1)} 公里`;
}
/**
 * Places with a distance from origin (null when unknown); located places nearest first,
 * unlocated last, stable otherwise. `recommended` is the nearest located place (only
 * when the origin is known), else null.
 */
export function rankPlaces(places, origin) {
  const rows = places.map((place, index) => ({ place, index, distance: origin && place?.position ? distanceMeters(origin, place.position) : null }));
  if (origin) rows.sort((x, y) => (x.distance == null) - (y.distance == null) || (x.distance ?? 0) - (y.distance ?? 0) || x.index - y.index);
  const recommended = origin ? rows.find((r) => r.distance != null)?.place ?? null : null;
  return { rows, recommended };
}
