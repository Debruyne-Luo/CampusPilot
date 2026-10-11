// Mobile chat bottom sheet states (pure): expanded ↔ collapsed (small handle).
// Swipe down collapses, swipe up expands; guidance collapses it and restores on stop.
export const initialSheet = () => ({ state: "expanded", beforeGuidance: null, guiding: false });
const SWIPE = 40, FLICK = 0.5; // px, px/ms

export function reduceSheet(s, action) {
  switch (action.type) {
    case "toggle": return { ...s, state: s.state === "expanded" ? "collapsed" : "expanded" };
    case "drag-end": {
      const dy = Number(action.dy) || 0, v = Number(action.velocity) || 0;
      if (dy > SWIPE || v > FLICK) return { ...s, state: "collapsed" };
      if (dy < -SWIPE || v < -FLICK) return { ...s, state: "expanded" };
      return s;
    }
    case "guidance-start": return s.guiding ? s : { state: "collapsed", beforeGuidance: s.state, guiding: true };
    case "guidance-stop": return s.guiding ? { state: s.beforeGuidance || "expanded", beforeGuidance: null, guiding: false } : s;
    case "focus-input": return { ...s, state: "expanded" };
    default: return s;
  }
}
