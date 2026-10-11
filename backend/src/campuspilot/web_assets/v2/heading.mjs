// Compass heading for walking guidance (pure helpers + a tiny tracker).
// iOS: webkitCompassHeading (degrees clockwise from north). Android/others:
// deviceorientationabsolute alpha (counter-clockwise) → 360 - alpha, corrected for
// screen rotation. Falls back to GPS course when no compass reading is available.
export const norm = (d) => ((d % 360) + 360) % 360;
/** Signed shortest angle from a to b in (-180, 180]. */
export function delta(a, b) { const d = norm(b) - norm(a); return d > 180 ? d - 360 : d <= -180 ? d + 360 : d; }
/** Heading in degrees clockwise from north, or null when the event has no absolute heading. */
export function headingFromEvent(e, screenAngle = 0) {
  if (!e) return null;
  if (Number.isFinite(e.webkitCompassHeading) && e.webkitCompassHeading >= 0) return norm(e.webkitCompassHeading);
  if (e.absolute === true && Number.isFinite(e.alpha)) return norm(360 - e.alpha + (Number(screenAngle) || 0));
  return null;
}
/** Exponential smoothing across the 0/360 wrap; large jumps settle faster. */
export function smoothHeading(prev, next, factor = 0.25) {
  if (!Number.isFinite(next)) return prev;
  if (!Number.isFinite(prev)) return norm(next);
  const d = delta(prev, next), f = Math.abs(d) > 90 ? Math.max(factor, 0.6) : factor;
  return norm(prev + d * f);
}
/** GPS course is only meaningful while moving (speed in m/s). */
export function courseFromFix(coords) {
  if (!coords || !Number.isFinite(coords.heading) || !Number.isFinite(coords.speed) || coords.speed < 0.7) return null;
  return norm(coords.heading);
}
/** Map rotation (AMap, clockwise degrees) and arrow rotation on screen for a heading. */
export function viewRotation(heading, headingUp) {
  if (!Number.isFinite(heading)) return { map: 0, arrow: 0 };
  return headingUp ? { map: norm(-heading), arrow: 0 } : { map: 0, arrow: norm(heading) };
}
/** True when the platform needs a user-gesture permission call (iOS 13+). */
export function needsPermission(DOE) { return typeof DOE?.requestPermission === "function"; }

export function createHeadingTracker({ now = () => Date.now(), staleMs = 3000, factor = 0.25 } = {}) {
  let value = null, compassAt = -Infinity, source = "none";
  return {
    compass(event, screenAngle) {
      const raw = headingFromEvent(event, screenAngle);
      if (raw == null) return value;
      value = smoothHeading(value, raw, factor); compassAt = now(); source = "compass"; return value;
    },
    gps(coords) {
      const course = courseFromFix(coords);
      if (course == null || now() - compassAt < staleMs) return value; // compass wins while fresh
      value = smoothHeading(value, course, 0.5); source = "gps"; return value;
    },
    get value() { return value; },
    get source() { return source; },
  };
}
