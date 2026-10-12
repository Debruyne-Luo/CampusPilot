// Mobile chat bottom sheet (pure): expanded ↔ collapsed (peek: handle + header).
// The sheet follows the finger while dragging; release snaps by distance or flick velocity.
// Guidance collapses it and restores the previous state on stop.
export const initialSheet = () => ({ state: "expanded", beforeGuidance: null, guiding: false });
const SWIPE = 40, FLICK = 0.5; // px, px/ms

export function reduceSheet(s, action) {
  switch (action.type) {
    case "toggle": return { ...s, state: s.state === "expanded" ? "collapsed" : "expanded" };
    case "drag-end": {
      const dy = Number(action.dy) || 0, v = Number(action.velocity) || 0;
      if (v > FLICK) return { ...s, state: "collapsed" };
      if (v < -FLICK) return { ...s, state: "expanded" };
      if (dy > SWIPE) return { ...s, state: "collapsed" };
      if (dy < -SWIPE) return { ...s, state: "expanded" };
      return s;
    }
    case "collapse": return { ...s, state: "collapsed" };
    case "guidance-start": return s.guiding ? s : { state: "collapsed", beforeGuidance: s.state, guiding: true };
    case "guidance-stop": return s.guiding ? { state: s.beforeGuidance || "expanded", beforeGuidance: null, guiding: false } : s;
    case "focus-input": return { ...s, state: "expanded" };
    default: return s;
  }
}
/** Downward translation (px) of a sheet of `height` showing only `peek` px when collapsed. */
export function sheetOffset(state, height, peek) {
  return state === "collapsed" ? Math.max(0, height - peek) : 0;
}
/** Live drag position: base + dy, clamped to [0, max] with a soft rubber band past the ends. */
export function dragOffset(base, dy, max) {
  const y = base + dy;
  if (y < 0) return -Math.min(24, -y * 0.25);
  if (y > max) return max + Math.min(24, (y - max) * 0.25);
  return y;
}
/** Release velocity (px/ms, + = down) from the last ~100 ms of [time, y] samples. */
export function releaseVelocity(samples) {
  if (samples.length < 2) return 0;
  const last = samples[samples.length - 1];
  let first = samples[0];
  for (const s of samples) if (last[0] - s[0] <= 100) { first = s; break; }
  const dt = last[0] - first[0];
  return dt > 0 ? (last[1] - first[1]) / dt : 0;
}
/** Visible sheet height for a translation; overlays on the map sit above it. */
export const visibleHeight = (height, offset) => Math.max(0, Math.round(height - offset));
