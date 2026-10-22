// Route origin selection (pure state): GPS when available, otherwise a point picked on the
// map or a place chosen from the list ("从…出发"). Manual choices win over later GPS fixes.
import { toGcj02, validPosition } from "./geo.mjs";

export const initialOrigin = () => ({ source: "none", position: null, label: "", picking: false });

export function reduceOrigin(state, action) {
  switch (action.type) {
    case "gps": {
      if (!validPosition(action.position)) return state;
      if (state.source === "map" || state.source === "place") return state; // user choice is kept
      return { source: "gps", position: action.position, label: "我的位置", picking: false };
    }
    case "pick-start": return { ...state, picking: true };
    case "pick-cancel": return { ...state, picking: false };
    case "map": {
      if (!validPosition(action.position)) return { ...state, picking: false };
      return { source: "map", position: toGcj02(action.position), label: action.label || "地图选点", picking: false };
    }
    case "place": {
      const p = action.place;
      if (!p || !validPosition(p.position)) return state;
      return { source: "place", position: toGcj02(p.position), label: p.name, placeId: p.place_id, picking: false };
    }
    case "use-gps": return initialOrigin(); // forget manual choice; next GPS fix fills it
    case "gps-denied": return state.source === "gps" ? initialOrigin() : state;
    default: return state;
  }
}
/** The origin to send for routing, or null when the user must choose one first. */
export function routeOrigin(state) { return state.position && validPosition(state.position) ? state.position : null; }
export function originLabel(state) {
  if (state.picking) return "在地图上点选起点…";
  return state.position ? `从 ${state.label} 出发` : "未设置起点";
}
