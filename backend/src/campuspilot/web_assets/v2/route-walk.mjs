// Walking a route polyline (pure): metres along the path → position + bearing.
// Used by the map frame to move the guide dinosaur (3D layer or 2D sprite).
const R = 6371008.8, rad = Math.PI / 180;
export function meters(a, b) {
  const dLat = (b[1] - a[1]) * rad, dLng = (b[0] - a[0]) * rad, m = Math.cos(((a[1] + b[1]) / 2) * rad);
  return R * Math.hypot(dLat, dLng * m);
}
/** Bearing in degrees clockwise from north from a to b ([lng, lat]). */
export function bearing(a, b) {
  const m = Math.cos(((a[1] + b[1]) / 2) * rad);
  const d = Math.atan2((b[0] - a[0]) * m, b[1] - a[1]) / rad;
  return (d + 360) % 360;
}
/** Precomputed cumulative distances; consecutive duplicate points are dropped. */
export function buildTrack(points) {
  const pts = [];
  for (const p of points || []) {
    if (!Array.isArray(p) || !Number.isFinite(p[0]) || !Number.isFinite(p[1])) continue;
    if (!pts.length || meters(pts[pts.length - 1], p) > 0.01) pts.push([p[0], p[1]]);
  }
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + meters(pts[i - 1], pts[i]));
  return { pts, cum, total: cum[cum.length - 1] || 0 };
}
/** Position, bearing and segment index `d` metres along the track (clamped). */
export function pointAt(track, d) {
  const { pts, cum, total } = track;
  if (!pts.length) return null;
  if (pts.length === 1) return { lng: pts[0][0], lat: pts[0][1], bearing: 0, index: 0, done: true };
  const x = Math.max(0, Math.min(total, d));
  let lo = 0, hi = cum.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (cum[mid] <= x) lo = mid; else hi = mid; }
  const seg = cum[hi] - cum[lo] || 1, f = (x - cum[lo]) / seg, a = pts[lo], b = pts[hi];
  return { lng: a[0] + (b[0] - a[0]) * f, lat: a[1] + (b[1] - a[1]) * f, bearing: bearing(a, b), index: lo, done: x >= total };
}
/** Distance along the track of the point closest to p (projection onto segments). */
export function project(track, p) {
  const { pts, cum } = track;
  let best = { d: 0, off: Infinity };
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], m = Math.cos(a[1] * rad);
    const ax = (b[0] - a[0]) * m, ay = b[1] - a[1], px = (p[0] - a[0]) * m, py = p[1] - a[1];
    const t = Math.max(0, Math.min(1, (px * ax + py * ay) / (ax * ax + ay * ay || 1)));
    const q = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], off = meters(q, p);
    if (off < best.off) best = { d: cum[i - 1] + (cum[i] - cum[i - 1]) * t, off };
  }
  return best;
}
/** Shortest signed turn from a to b in degrees. */
const turn = (a, b) => ((((b - a) % 360) + 540) % 360) - 180;
/** Frame-rate independent easing of a bearing toward a target (tau seconds). */
export function easeBearing(current, target, dt, tau = 0.35) {
  if (!Number.isFinite(current)) return target;
  const k = 1 - Math.exp(-Math.max(0, dt) / tau);
  return (current + turn(current, target) * k + 360) % 360;
}
/** 3D only with WebGL, some headroom, and no reduced-motion preference. */
export function canUse3d({ webgl, cores, memory, reducedMotion }) {
  if (!webgl || reducedMotion) return false;
  if (Number.isFinite(cores) && cores <= 2) return false;
  if (Number.isFinite(memory) && memory <= 2) return false;
  return true;
}
