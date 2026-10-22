// The server resolves names independently of iframe/SDK readiness. No user GPS is sent.
const HEADERS = { "Content-Type": "application/json", "X-CampusPilot-Request": "1" };
export function navigationTarget(place) {
  return place?.transient || String(place?.place_id || "").startsWith("amap:poi:")
    ? { position: place.position } : { place_id: place.place_id };
}
export function createPlaceSearch(fetchImpl = fetch) {
  let revision = 0, active = null;
  return {
    cancel() { revision++; active?.abort(); active = null; },
    async search(query) {
      const ticket = ++revision;
      active?.abort(); const controller = new AbortController(); active = controller;
      try {
        const response = await fetchImpl("/api/places/search", {
          method: "POST", headers: HEADERS, credentials: "same-origin", signal: controller.signal,
          body: JSON.stringify({ query }),
        });
        const body = await response.json();
        if (ticket !== revision) return null;
        if (!response.ok) return { places: [], status: "unavailable", message: body.message || "地点搜索暂不可用，请重新连接后重试。" };
        return body;
      } catch {
        if (ticket !== revision) return null;
        return { places: [], status: "unavailable", provider_status: "unavailable", message: "地点搜索连接中断，请稍后重试。" };
      } finally { if (ticket === revision) active = null; }
    },
  };
}
