"use strict";
let map = null;
let markers = [];
let started = false;
let frameGeneration = null;
let placeRecords = new Map();
let routeId = 0, pickingOrigin = false, routeLayers = [], routeBottom = 200;
let discoveryId = 0, pickingDestination = false, hotspotSequence = 0;
let navigationId = null, locationLayer = null, followingLocation = true, locationSequence = 0;
// Viewport only; not a service/office destination. Amap campus POI B001C7X6H7,
// https://ditu.amap.com/place/B001C7X6H7, retrieved 2026-10-08 (GCJ02).
const CAMPUS_CENTER = [104.147531, 30.675012];
const CAMPUS_ZOOM = 15;
function notify(action, data = {}) {
  parent.postMessage({type: "campuspilot-map", action, ...data,frame_generation:frameGeneration}, location.origin);
}
async function timed(operation, message) {
  let timer;
  try {
    return await Promise.race([operation, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(message)), 15000);
    })]);
  } finally {clearTimeout(timer);}
}
async function init(config) {
  try {
    window._AMapSecurityConfig = {serviceHost: location.origin + "/_AMapService"};
    await timed(new Promise((resolve, reject) => {
      const script = document.createElement("script"); script.src = "https://webapi.amap.com/loader.js";
      script.onload = resolve; script.onerror = () => reject(new Error("地图组件加载失败"));
      document.head.append(script);
    }), "地图组件加载超时");
    await timed(window.AMapLoader.load({key: config.key, version: "2.0"}), "地图组件加载超时");
    map = new AMap.Map("map-view", {center: CAMPUS_CENTER, zoom: CAMPUS_ZOOM, viewMode: "2D", isHotspot:true});
    await timed(new Promise((resolve) => map.on("complete", resolve)), "地图图像加载超时");
    map.on("click", (event) => {
      if (!event.lnglat) return;
      const position = {longitude:event.lnglat.lng, latitude:event.lnglat.lat, coordinate_system:"GCJ02"};
      if (pickingOrigin) {
        pickingOrigin = false; map.setDefaultCursor("default");
        notify("route-origin", {request_id:routeId, position});
      } else if (pickingDestination) {
        pickingDestination = false; map.setDefaultCursor("default");
        notify("map-destination", {request_id:discoveryId, position});
      }
    });
    map.on("hotspotclick", selectHotspot);
    map.on("dragstart", () => {followingLocation = false;});
    map.on("resize", () => requestAnimationFrame(fitRoute));
    notify("ready");
  } catch {
    if (map) {map.destroy(); map = null;}
    notify("failed");
  }
}
function validPosition(position) {
  return position?.coordinate_system === "GCJ02" &&
    Number.isFinite(position.longitude) && Number.isFinite(position.latitude) &&
    Math.abs(position.longitude) <= 180 && Math.abs(position.latitude) <= 90;
}
function highlightMarker(placeId) {
  for (const content of document.querySelectorAll(".campus-marker")) {
    content.classList.toggle("selected", content.dataset.placeId === placeId);
  }
}
function fitMarkers() {
  // Keep points clear of the category chips and bottom result cards.
  map.setFitView(markers, true, [65, 140, 35, 45], 17);
}
// The SDK may clone marker content. Delegate to its rendered buttons so mouse,
// touch and native keyboard clicks all select the same authoritative place ID.
document.getElementById("map-view").addEventListener("click", (event) => {
  const button = event.target instanceof Element ? event.target.closest("button.campus-marker") : null;
  if (!button) return;
  if (pickingOrigin) {
    const p = placeRecords.get(button.dataset.placeId);
    if (p && validPosition(p.position)) {
      pickingOrigin = false; map.setDefaultCursor("default");
      notify("route-origin", {request_id: routeId, position: p.position, name: p.name});
    }
    event.stopPropagation(); return;
  }
  highlightMarker(button.dataset.placeId);
  pickingDestination = false;
  notify("select", {place_id: button.dataset.placeId});
}, true);
window.addEventListener("message", (event) => {
  if (event.origin !== location.origin || event.source !== parent || event.data?.type !== "campuspilot-map") return;
  const data = event.data;
  if (started && !['init','ping'].includes(data.action) && data.frame_generation !== frameGeneration) return;
  if (data.action === "ping") notify("frame-ready");
  else if (data.action === "init" && !started && typeof data.config?.key === "string") {
    frameGeneration=data.frame_generation; started = true; init(data.config);
  } else if (data.action === "places" && map && Array.isArray(data.places)) {
    placeRecords = new Map(data.places.map((p) => [p.place_id, p]));
    map.remove(markers); markers = [];
    for (const place of data.places.slice(0, 100).filter((p) => validPosition(p.position))) {
      const reviewed = place.position.verification_status === "confirmed";
      const content = document.createElement("button");
      content.className = "campus-marker" + (reviewed ? " confirmed" : " candidate");
      content.type = "button";
      content.dataset.placeId = place.place_id;
      const title = String(place.name);
      content.setAttribute("aria-label", title);
      const icons = {teaching: "▤", office: "▥", library: "▣", dining: "♧", service: "⌘", sports: "◎", gate: "⇥"};
      const icon = document.createElement("span"); icon.textContent = icons[place.category] || "⌖"; icon.setAttribute("aria-hidden", "true");
      const label = document.createElement("span"); label.className = "campus-marker-label";
      label.textContent = String(place.name);
      content.append(icon, label);
      const marker = new AMap.Marker({position: [place.position.longitude, place.position.latitude], title, content, anchor: "bottom-center"});
      markers.push(marker);
    }
    map.add(markers); if (markers.length) fitMarkers();
    highlightMarker(data.selected_place_id);
  } else if (data.action === "center" && map && validPosition(data.position)) {
    highlightMarker(data.place_id);
    map.setZoomAndCenter(17, [data.position.longitude, data.position.latitude]);
    map.panBy(0, -Math.min(110, window.innerHeight * .16));
  } else if (data.action === "selection" && map) {
    highlightMarker(data.place_id);
  } else if (data.action === "route-clear" && Number.isSafeInteger(data.request_id)) {
    routeId = data.request_id; clearRoute();
  } else if (data.action === "route-pick" && map && Number.isSafeInteger(data.request_id)) {
    routeId = data.request_id; pickingOrigin = true; map.setDefaultCursor("crosshair");
  } else if (data.action === "route-request" && map && Number.isSafeInteger(data.request_id)) {
    routeId = data.request_id; clearRoute(); planWalking(data);
  } else if (data.action === "discovery-cancel" && Number.isSafeInteger(data.request_id)) {
    discoveryId = data.request_id; pickingDestination = false; hotspotSequence++;
    if (map && !pickingOrigin) map.setDefaultCursor("default");
  } else if (data.action === "destination-pick" && map && Number.isSafeInteger(data.request_id)) {
    discoveryId = data.request_id; pickingDestination = true; pickingOrigin = false; map.setDefaultCursor("crosshair");
  } else if (data.action === "place-search" && map && Number.isSafeInteger(data.request_id) && typeof data.query === "string" && data.query.length <= 120) {
    discoveryId = data.request_id; pickingDestination = false; searchPlaces(data);
  } else if (data.action === "guidance-start" && data.request_id === routeId && Number.isSafeInteger(data.navigation_id)) {
    navigationId = data.navigation_id; followingLocation = true;
  } else if (data.action === "guidance-stop" && data.navigation_id === navigationId) {
    clearLocation();
  } else if (data.action === "guidance-update" && data.request_id === routeId && data.navigation_id === navigationId && navigationId !== null) {
    updateLocation(data);
  } else if (data.action === "guidance-follow" && data.navigation_id === navigationId) {
    followingLocation = true;
    if (map && locationLayer) followPosition(locationLayer.getPosition());
  } else if (data.action === "route-insets" && map && Number.isFinite(data.bottom)) {
    routeBottom = Math.min(Math.max(80, data.bottom), window.innerHeight * .55);
    fitRoute();
  } else if (data.action === "zoom" && map && (data.delta === 1 || data.delta === -1)) {
    map.setZoom(Math.max(3, Math.min(20, map.getZoom() + data.delta)));
  } else if (data.action === "overview" && map) {
    if (routeLayers.length) fitRoute();
    else if (markers.length) fitMarkers();
    else map.setZoomAndCenter(CAMPUS_ZOOM, CAMPUS_CENTER);
  } else if (data.action === "resize" && map) {
    window.dispatchEvent(new Event("resize"));
  }
});
function clearRoute() {
  clearLocation();
  pickingOrigin = false;
  if (map) {map.setDefaultCursor("default"); if (routeLayers.length) map.remove(routeLayers);}
  routeLayers = [];
}
function fitRoute() {
  if (map && routeLayers.length && navigationId === null) map.setFitView(routeLayers, true, [70, routeBottom, 40, 60], 18);
}
async function convertPosition(origin) {
  if (validPosition(origin)) return origin;
  if (origin?.coordinate_system !== "WGS84" || !Number.isFinite(origin.longitude) || !Number.isFinite(origin.latitude) || Math.abs(origin.longitude) > 180 || Math.abs(origin.latitude) > 90) throw new Error("origin");
  return timed(new Promise((resolve, reject) => AMap.convertFrom([origin.longitude,origin.latitude], "gps", (status, value) => {
    const point = value?.locations?.[0];
    if (status === "complete" && point) resolve({longitude:point.lng,latitude:point.lat,coordinate_system:"GCJ02"});
    else reject(new Error("conversion"));
  })), "conversion timeout");
}
async function planWalking(data) {
  const id = data.request_id;
  try {
    const destination = placeRecords.get(data.destination_place_id);
    if (!destination || !validPosition(destination.position)) throw new Error("destination");
    const origin = await convertPosition(data.origin);
    if (id !== routeId) return;
    if (!validPosition(origin)) throw new Error("origin");
    await timed(new Promise((resolve) => AMap.plugin("AMap.Walking", resolve)), "plugin timeout");
    if (id !== routeId) return;
    const route = await timed(new Promise((resolve, reject) => {
      new AMap.Walking().search([origin.longitude, origin.latitude], [destination.position.longitude, destination.position.latitude], (status, value) => {
        if (status === "complete" && value?.routes?.length) resolve(value.routes[0]);
        else reject(new Error("no route"));
      });
    }), "route timeout");
    if (id !== routeId) return;
    const path = route.steps?.flatMap((step) => step.path || []);
    if (!path?.length || !Number.isFinite(route.distance) || !Number.isFinite(route.time)) throw new Error("invalid route");
    const line = new AMap.Polyline({path, isOutline: true, outlineColor: "#fff", borderWeight: 2, strokeWeight: 6, strokeColor: "#347451", strokeOpacity: 1, zIndex: 150, lineJoin: "round"});
    const endpoint = (position, text) => {
      const content = document.createElement("span"); content.className = "route-marker"; content.textContent = text;
      return new AMap.Marker({position, content, anchor: "center", zIndex: 200});
    };
    routeLayers = [line, endpoint(path[0], "起"), endpoint(path[path.length - 1], "终")];
    map.add(routeLayers); fitRoute();
    let count = 0;
    const stepEnds = route.steps.map(step => {count += (step.path || []).length; return Math.max(0,count - 1);});
    notify("route-result", {request_id:id, status:"success", distance:route.distance, time:route.time,
      steps:route.steps.map(step => String(step.instruction || "继续沿路线步行")),
      geometry:path.map(point => [point.lng,point.lat]), step_ends:stepEnds});
  } catch {
    if (id === routeId) {clearRoute(); notify("route-result", {request_id: id, status: "error"});}
  }
}
async function placeSearch() {
  await timed(new Promise(resolve => AMap.plugin("AMap.PlaceSearch", resolve)), "place plugin timeout");
  return new AMap.PlaceSearch({city:"成都",pageSize:10,pageIndex:1,extensions:"base"});
}
function serialisePoi(poi) {
  if (!poi?.location || !/^[A-Za-z0-9]{8,32}$/.test(poi.id || "") || typeof poi.name !== "string") return null;
  const position = {longitude:poi.location.lng,latitude:poi.location.lat,coordinate_system:"GCJ02"};
  if (!validPosition(position) || AMap.GeometryUtil.distance(CAMPUS_CENTER,[position.longitude,position.latitude]) > 2400) return null;
  return {poi_id:poi.id,name:poi.name.slice(0,120),address:typeof poi.address === "string" ? poi.address.slice(0,300) : "",position};
}
async function searchPlaces(data) {
  const id = data.request_id;
  try {
    const service = await placeSearch();
    if (id !== discoveryId) return;
    const value = await timed(new Promise((resolve,reject) => service.searchNearBy(data.query,CAMPUS_CENTER,2000,(status,value) => {
      if (status === "complete") resolve(value);
      else if (status === "no_data") resolve({poiList:{pois:[]}});
      else reject(new Error("place search"));
    })), "place search timeout");
    if (id === discoveryId) notify("place-search-result", {request_id:id,status:"success",places:(value.poiList?.pois || []).map(serialisePoi).filter(Boolean)});
  } catch {if (id === discoveryId) notify("place-search-result", {request_id:id,status:"error",places:[]});}
}
async function selectHotspot(event) {
  if (!/^[A-Za-z0-9]{8,32}$/.test(event.id || "") || pickingOrigin || pickingDestination) return;
  const id = discoveryId, selection = ++hotspotSequence;
  try {
    const service = await placeSearch();
    const value = await timed(new Promise((resolve,reject) => service.getDetails(event.id,(status,value) => {
      if (status === "complete" && value?.poiList?.pois?.length) resolve(value.poiList.pois[0]);
      else reject(new Error("place detail"));
    })), "place detail timeout");
    if (id === discoveryId && selection === hotspotSequence) notify("poi-selection", {request_id:id,place:serialisePoi(value)});
  } catch {if (id === discoveryId && selection === hotspotSequence) notify("poi-selection", {request_id:id,place:null});}
}
function clearLocation() {
  navigationId = null; locationSequence++;
  if (map && locationLayer) map.remove(locationLayer);
  locationLayer = null;
}
function followPosition(position) {
  map.setCenter(position);
  map.panBy(0,-Math.min(routeBottom*.5,window.innerHeight*.27));
}
async function updateLocation(data) {
  const id = navigationId, sequence = ++locationSequence;
  try {
    const position = await convertPosition(data.position);
    if (id !== navigationId || sequence !== locationSequence || data.request_id !== routeId) return;
    if (!locationLayer) {
      const dot = document.createElement("span"); dot.className = "guidance-location"; dot.setAttribute("aria-label","我的位置");
      locationLayer = new AMap.Marker({position:[position.longitude,position.latitude],content:dot,anchor:"center",zIndex:300});
      map.add(locationLayer);
    } else locationLayer.setPosition([position.longitude,position.latitude]);
    if (followingLocation) followPosition([position.longitude,position.latitude]);
    notify("guidance-position", {request_id:routeId,navigation_id:id,position,accuracy:data.accuracy,status:"success"});
  } catch {if (id === navigationId && sequence === locationSequence) notify("guidance-position", {request_id:routeId,navigation_id:id,status:"error"});}
}
notify("frame-ready");
