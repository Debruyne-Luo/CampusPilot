"use strict";
let map = null;
let markers = [];
let started = false;
let frameGeneration = null;
let placeRecords = new Map();
let routeId = 0, pickingOrigin = false, routeLayers = [], routeBottom = 200, requestedRouteBottom = 200;
let discoveryId = 0, pickingDestination = false, hotspotSequence = 0;
let routeGeometry = [], guide = null, dinoState = null, dinoRaf = 0, dinoToken = 0;
let markerLayer = null, selectedId = null, handledAt = 0;
const TOUCH = matchMedia("(pointer: coarse)").matches;
let navigationId = null, locationLayer = null, followingLocation = true, locationSequence = 0;
// Viewport only; not a service/office destination. Amap campus POI B001C7X6H7,
// https://ditu.amap.com/place/B001C7X6H7, retrieved 2026-10-08 (GCJ02).
const CAMPUS_CENTER = [104.147531, 30.675012];
const CAMPUS_ZOOM = 15;
// Campus bounding box (all recorded places, GCJ02) widened by about 1 km. The map cannot
// pan or zoom out beyond it, and taps / POIs / search hits / picks outside are ignored.
const AREA = {west: 104.139965 - 0.0105, east: 104.154625 + 0.0105, south: 30.670203 - 0.009, north: 30.683981 + 0.009};
const MIN_ZOOM = 15;
function inArea(lng, lat) {
  return lng >= AREA.west && lng <= AREA.east && lat >= AREA.south && lat <= AREA.north;
}
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
    map = new AMap.Map("map-view", {center: CAMPUS_CENTER, zoom: CAMPUS_ZOOM, zooms: [MIN_ZOOM, 20], viewMode: "3D", pitch: 0, isHotspot:true, rotateEnable:true,
      // Phones: skip 3D building blocks and keep the default canvas cheap while panning.
      // 3D view mode from the start (AMap cannot switch later); pitched only while guiding.
      showBuildingBlock: true, pitchEnable: false, WebGLParams: {preserveDrawingBuffer: false}});
    map.setLimitBounds(new AMap.Bounds([AREA.west, AREA.south], [AREA.east, AREA.north]));
    // Belt and braces: programmatic moves (and some SDK paths) can bypass limitBounds.
    map.on("moveend", () => {
      const c = map.getCenter(), lng = Math.min(AREA.east, Math.max(AREA.west, c.getLng())), lat = Math.min(AREA.north, Math.max(AREA.south, c.getLat()));
      if (lng !== c.getLng() || lat !== c.getLat()) map.setCenter([lng, lat], true);
    });
    markerLayer = new AMap.LabelsLayer({zooms: [3, 20], zIndex: 130, collision: false, allowCollision: true});
    map.add(markerLayer);
    await timed(new Promise((resolve) => map.on("complete", resolve)), "地图图像加载超时");
    map.on("click", (event) => {if (event.lnglat && Date.now() - handledAt > 450) pickPoint(event.lnglat);});
    map.on("hotspotclick", (event) => {handledAt = Date.now(); selectHotspot(event);});
    watchTaps(document.getElementById("map-view"));
    map.on("dragstart", () => {followingLocation = false;});
    map.on("resize", () => requestAnimationFrame(resizeRouteView));
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
  selectedId = placeId || null;
  for (const marker of markers) {
    const place = marker.getExtData();
    marker.setIcon(pinIcon(place, place.place_id === selectedId));
    marker.setzIndex(place.place_id === selectedId ? 200 : 100);
    marker.setText(markerText(place, place.place_id === selectedId));
  }
}
function fitMarkers() {
  // Keep points clear of the category chips (top) and the sheet / place card (bottom).
  const pts = markers.map((m) => m.getExtData().position);
  if (pts.length === 1) {map.setZoomAndCenter(17, [pts[0].longitude, pts[0].latitude]); return;}
  const lng = pts.map((p) => p.longitude), lat = pts.map((p) => p.latitude);
  const bottom = Math.min(Math.max(80, requestedRouteBottom) + 20, map.getSize().getHeight() * 0.45);
  map.setBounds(new AMap.Bounds([Math.min(...lng), Math.min(...lat)], [Math.max(...lng), Math.max(...lat)]), true, [150, bottom, 40, 40]);
  if (map.getZoom() > 17) map.setZoom(17);
}
window.addEventListener("message", (event) => {
  if (event.origin !== location.origin || event.source !== parent || event.data?.type !== "campuspilot-map") return;
  const data = event.data;
  if (started && !['init','ping'].includes(data.action) && data.frame_generation !== frameGeneration) return;
  if (data.action === "ping") notify("frame-ready");
  else if (data.action === "init" && !started && typeof data.config?.key === "string") {
    frameGeneration=data.frame_generation; started = true; init(data.config);
  } else if (data.action === "places" && map && Array.isArray(data.places)) {
    placeRecords = new Map(data.places.map((p) => [p.place_id, p]));
    markerLayer.clear(); markers = [];
    selectedId = data.selected_place_id || null;
    for (const place of data.places.slice(0, 100).filter((p) => validPosition(p.position))) {
      const selected = place.place_id === selectedId;
      const marker = new AMap.LabelMarker({position: [place.position.longitude, place.position.latitude],
        zIndex: selected ? 200 : 100, extData: place, icon: pinIcon(place, selected), text: markerText(place, selected)});
      const tap = () => {if (Date.now() - handledAt > 450) {handledAt = Date.now(); selectMarker(place);}};
      marker.on("click", tap); marker.on("touchend", tap);
      markers.push(marker);
    }
    markerLayer.add(markers); document.body.dataset.markers = String(markers.length);
    if (markers.length && data.fit !== false) fitMarkers();
    highlightMarker(data.selected_place_id);
  } else if (data.action === "center" && map && validPosition(data.position)) {
    highlightMarker(data.place_id);
    map.setZoomAndCenter(17, [data.position.longitude, data.position.latitude]);
    map.panBy(0, -Math.min(110, window.innerHeight * .16));
  } else if (data.action === "selection" && map) {
    highlightMarker(data.place_id);
  } else if (data.action === "route-clear" && Number.isSafeInteger(data.request_id)) {
    routeId = data.request_id; clearRoute();
  } else if (data.action === "route-pick-point" && map && pickingOrigin && data.request_id === routeId && Number.isFinite(data.x) && Number.isFinite(data.y)) {
    handledAt = Date.now(); pickPoint(map.containerToLngLat(new AMap.Pixel(data.x, data.y)));
  } else if (data.action === "route-pick" && map && Number.isSafeInteger(data.request_id)) {
    routeId = data.request_id; pickingOrigin = true; map.setDefaultCursor("crosshair");
  } else if (data.action === "route-request" && map && Number.isSafeInteger(data.request_id)) {
    routeId = data.request_id; clearRoute(); planWalking(data);
  } else if (data.action === 'nearby-origin' && map && Number.isSafeInteger(data.request_id)) {
    convertPosition(data.position).then(position => notify('nearby-origin-result', {request_id:data.request_id,status:'success',position}))
      .catch(() => notify('nearby-origin-result', {request_id:data.request_id,status:'error'}));
  } else if (data.action === "discovery-cancel" && Number.isSafeInteger(data.request_id)) {
    discoveryId = data.request_id; pickingDestination = false; hotspotSequence++;
    if (map && !pickingOrigin) map.setDefaultCursor("default");
  } else if (data.action === "destination-pick" && map && Number.isSafeInteger(data.request_id)) {
    discoveryId = data.request_id; pickingDestination = true; pickingOrigin = false; map.setDefaultCursor("crosshair");
  } else if (data.action === "place-search" && map && Number.isSafeInteger(data.request_id) && typeof data.query === "string" && data.query.length <= 120) {
    discoveryId = data.request_id; pickingDestination = false; searchPlaces(data);
  } else if (data.action === "guidance-start" && data.request_id === routeId && Number.isSafeInteger(data.navigation_id)) {
    navigationId = data.navigation_id; followingLocation = true;
  } else if (data.action === "dino-start" && map && routeGeometry.length > 1) {
    startDino(data);
  } else if (data.action === "dino-stop") {
    stopDino();
  } else if (data.action === "dino-mode" && guide && typeof data.demo === "boolean") {
    setDinoDemo(data.demo, data.speed);
  } else if (data.action === "guidance-stop" && data.navigation_id === navigationId) {
    clearLocation();
  } else if (data.action === "guidance-update" && data.request_id === routeId && data.navigation_id === navigationId && navigationId !== null) {
    updateLocation(data);
  } else if (data.action === "guidance-follow" && data.navigation_id === navigationId) {
    followingLocation = true;
    if (map && locationLayer) followPosition(locationLayer.getPosition());
  } else if (data.action === "route-insets" && map && Number.isFinite(data.bottom)) {
    requestedRouteBottom=data.bottom; resizeRouteView();
  } else if (data.action === "zoom" && map && (data.delta === 1 || data.delta === -1)) {
    map.setZoom(Math.max(3, Math.min(20, map.getZoom() + data.delta)));
  } else if (data.action === "overview" && map) {
    if (routeLayers.length) fitRoute();
    else if (markers.length) fitMarkers();
    else map.setZoomAndCenter(CAMPUS_ZOOM, CAMPUS_CENTER);
  } else if (data.action === "heading" && map && navigationId !== null) {
    applyHeading(data);
  } else if (data.action === "north-up" && map) {
    map.setRotation(0);
  } else if (data.action === "resize" && map) {
    window.dispatchEvent(new Event("resize"));
  }
});
function clearRoute() {
  clearLocation(); stopDino(); routeGeometry = [];
  pickingOrigin = false;
  if (map) {map.setDefaultCursor("default"); if (routeLayers.length) map.remove(routeLayers);}
  routeLayers = [];
}
function fitRoute() {
  if (map && routeLayers.length && navigationId === null) map.setFitView(routeLayers, true, [70, routeBottom, 40, 60], 18);
}
function resizeRouteView() {
  if (!map) return;
  routeBottom = Math.min(Math.max(80, requestedRouteBottom), Math.max(80,map.getSize().getHeight()-60));
  if (guide) return;
  if (navigationId !== null && followingLocation && locationLayer) followPosition(locationLayer.getPosition());
  else fitRoute();
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
    // A recorded place by ID, or an AMap POI / map point chosen by the user (GCJ02 only).
    const destination = data.destination_place_id ? placeRecords.get(data.destination_place_id)
      : (validPosition(data.destination_position) ? {position: data.destination_position} : null);
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
    const line = new AMap.Polyline({path, isOutline: true, outlineColor: "#fff", borderWeight: 2, strokeWeight: 6, strokeColor: "#347451", strokeOpacity: 1, zIndex: 150, lineJoin: "round", bubble: true});
    const endpoint = (position, text) => {
      const content = document.createElement("span"); content.className = "route-marker"; content.textContent = text;
      return new AMap.Marker({position, content, anchor: "center", zIndex: 200, bubble: true});
    };
    routeLayers = [line, endpoint(path[0], "起"), endpoint(path[path.length - 1], "终")];
    routeGeometry = path.map((point) => [point.lng, point.lat]);
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
  if (!validPosition(position) || !inArea(position.longitude, position.latitude)) return null;
  return {poi_id:poi.id,name:poi.name.slice(0,120),address:typeof poi.address === "string" ? poi.address.slice(0,300) : "",type:typeof poi.type === "string" ? poi.type.slice(0,120) : "",position};
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
function labelPoi(event) {
  if (typeof event?.name !== "string" || !event.name.trim() || !event.lnglat) return null;
  const position = {longitude: event.lnglat.getLng(), latitude: event.lnglat.getLat(), coordinate_system: "GCJ02"};
  if (!validPosition(position) || !inArea(position.longitude, position.latitude)) return null;
  return {poi_id: String(event.id || ""), name: event.name.slice(0, 120), address: "", position};
}
async function selectHotspot(event) {
  if (!event.lnglat || !inArea(event.lnglat.getLng(), event.lnglat.getLat())) return;
  if (pickingOrigin && event.lnglat) {
    // A POI label swallows the plain map click; use the label as the picked origin.
    const position = {longitude:event.lnglat.lng, latitude:event.lnglat.lat, coordinate_system:"GCJ02"};
    if (validPosition(position)) {
      pickingOrigin = false; map.setDefaultCursor("default");
      notify("route-origin", {request_id:routeId, position, name:typeof event.name === "string" ? event.name.slice(0,60) : undefined});
    }
    return;
  }
  if (!/^[A-Za-z0-9]{8,32}$/.test(event.id || "") || pickingOrigin || pickingDestination) return;
  const id = discoveryId, selection = ++hotspotSequence;
  try {
    const service = await placeSearch();
    const value = await timed(new Promise((resolve,reject) => service.getDetails(event.id,(status,value) => {
      if (status === "complete" && value?.poiList?.pois?.length) resolve(value.poiList.pois[0]);
      else reject(new Error("place detail"));
    })), "place detail timeout");
    if (id === discoveryId && selection === hotspotSequence) notify("poi-selection", {request_id:id,place:serialisePoi(value) || labelPoi(event)});
  } catch {
    // Many base-map labels have no place-detail record; the label itself is enough for a card.
    if (id === discoveryId && selection === hotspotSequence) notify("poi-selection", {request_id:id,place:labelPoi(event)});
  }
}
let arrowAngle = 0, hasHeading = false;
function applyHeading(data) {
  // arrow: screen rotation of the user arrow; rotation: AMap clockwise map rotation.
  if (!Number.isFinite(data.arrow) || !Number.isFinite(data.rotation)) return;
  if (guide) {if (Number.isFinite(data.heading_value)) dinoState.compass = data.heading_value; return;}
  arrowAngle = data.arrow; hasHeading = true;
  const dot = locationLayer?.getContent?.();
  if (dot instanceof Element) {dot.style.setProperty("--arrow", arrowAngle + "deg"); dot.classList.add("has-heading");}
  if (map && Math.abs(((map.getRotation() - data.rotation + 540) % 360) - 180) > 2) map.setRotation(data.rotation, true);
}
function clearLocation() {
  navigationId = null; locationSequence++; hasHeading = false;
  if (map && map.getRotation()) map.setRotation(0);
  if (map && locationLayer) map.remove(locationLayer);
  locationLayer = null;
}
function followPosition(position) {
  // Center the fix in the visible strip above the card in one camera operation.
  // A queued pan after setCenter could finish behind an expanded mobile card.
  const height=map.getSize().getHeight(), point=map.lngLatToContainer(position);
  if (!height) return;
  const visibleY=(60+Math.max(60,height-routeBottom))/2;
  const center=map.containerToLngLat(new AMap.Pixel(point.getX(),point.getY()+height/2-visibleY));
  map.setCenter(center,true);
}
async function updateLocation(data) {
  const id = navigationId, sequence = ++locationSequence;
  try {
    const position = await convertPosition(data.position);
    if (id !== navigationId || sequence !== locationSequence || data.request_id !== routeId) return;
    if (!locationLayer) {
      const dot = document.createElement("span"); dot.className = "guidance-location"; dot.setAttribute("aria-label","我的位置");
      const arrow = document.createElement("i"); arrow.className = "guidance-arrow"; arrow.setAttribute("aria-hidden","true"); dot.append(arrow);
      dot.style.setProperty("--arrow", arrowAngle + "deg"); dot.classList.toggle("has-heading", hasHeading);
      locationLayer = new AMap.Marker({position:[position.longitude,position.latitude],content:dot,anchor:"center",zIndex:300});
      map.add(locationLayer);
    } else locationLayer.setPosition([position.longitude,position.latitude]);
    if (guide && !dinoState.demo) dinoState.gps = [position.longitude, position.latitude];
    else if (followingLocation && !guide) followPosition([position.longitude,position.latitude]);
    notify("guidance-position", {request_id:routeId,navigation_id:id,position,accuracy:data.accuracy,status:"success"});
  } catch {if (id === navigationId && sequence === locationSequence) notify("guidance-position", {request_id:routeId,navigation_id:id,status:"error"});}
}
// ---- lightweight markers: one WebGL label layer, SVG pins as images ------------------
const GLYPHS = {
  dining: ["#d9772b", "M5 11h14a7 7 0 0 1-14 0zM9.5 4.5c-.8 1.2.8 2-.2 3.3M14.5 4.5c-.8 1.2.8 2-.2 3.3"],
  library: ["#3a6ccf", "M4 5.5h5.5A2.5 2.5 0 0 1 12 8v11a2 2 0 0 0-2-2H4zM20 5.5h-5.5A2.5 2.5 0 0 0 12 8v11a2 2 0 0 1 2-2h6z"],
  teaching: ["#3b7a53", "M4 9.5 12 5l8 4.5M6 10v8M10 10v8M14 10v8M18 10v8M4 19h16"],
  office: ["#6656b3", "M6 19V6h12v13M4 19h16M9 9h2M13 9h2M9 12.5h2M13 12.5h2M10.5 19v-3h3v3"],
  parcel: ["#b07f22", "M4 8 12 4l8 4v8l-8 4-8-4zM4 8l8 4 8-4M12 12v8"],
  medical: ["#d24848", "M10 5h4v5h5v4h-5v5h-4v-5H5v-4h5z"],
  card: ["#2a8796", "M3.5 6.5h17v11h-17zM3.5 10h17M7 14.5h4"],
  service: ["#56636c", "M12 7.5v.2M12 11v6"],
};
function glyphOf(place) {
  if (GLYPHS[place.glyph]) return place.glyph;
  return {dining: "dining", library: "library", teaching: "teaching", office: "office"}[place.category] || "service";
}
const iconCache = new Map();
function pinIcon(place, selected) {
  const glyph = glyphOf(place), key = glyph + (selected ? "!" : "");
  if (!iconCache.has(key)) {
    const [color, path] = GLYPHS[glyph], r = selected ? 15 : 12, cy = selected ? 17 : 19;
    // 44x48 image: the transparent margin is the (invisible) tap target around a small pin.
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="48" viewBox="0 0 44 48">`
      + `<path d="M22 ${cy + r + 9} l-5-${7} h10z" fill="${color}"/>`
      + `<circle cx="22" cy="${cy}" r="${r + 1.5}" fill="#fff"/><circle cx="22" cy="${cy}" r="${r}" fill="${selected ? "#1f3d2b" : color}"/>`
      + `<g transform="translate(${22 - r * .62} ${cy - r * .62}) scale(${r * 1.24 / 24})" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${path}"/></g></svg>`;
    iconCache.set(key, {type: "image", image: "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg), size: [44, 48], anchor: "bottom-center"});
  }
  return iconCache.get(key);
}
function markerText(place, selected) {
  return {content: String(place.name).slice(0, 14), direction: "bottom", offset: [0, -2], zooms: selected ? [3, 20] : [17, 20],
    style: {fontSize: 12, fontWeight: selected ? "bold" : "normal", fillColor: "#1d2a22", strokeColor: "#ffffff", strokeWidth: 3, padding: [0, 0]}};
}
function selectMarker(place) {
  if (pickingOrigin) {
    pickingOrigin = false; map.setDefaultCursor("default");
    notify("route-origin", {request_id: routeId, position: place.position, name: place.name});
    return;
  }
  highlightMarker(place.place_id); pickingDestination = false;
  notify("select", {place_id: place.place_id});
}
function pickPoint(lnglat) {
  const position = {longitude: lnglat.lng ?? lnglat.getLng(), latitude: lnglat.lat ?? lnglat.getLat(), coordinate_system: "GCJ02"};
  if (!validPosition(position)) return false;
  if (!inArea(position.longitude, position.latitude)) return pickingOrigin || pickingDestination; // silently ignored
  if (pickingOrigin) {
    pickingOrigin = false; map.setDefaultCursor("default");
    notify("route-origin", {request_id: routeId, position});
  } else if (pickingDestination) {
    pickingDestination = false; map.setDefaultCursor("default");
    notify("map-destination", {request_id: discoveryId, position});
  } else return false;
  return true;
}
// iOS Safari does not always turn a tap on the map canvas into an AMap "click" (or a
// POI "hotspotclick"). Recognise a short, still touch ourselves; the SDK's own handlers
// (marker / hotspot) get a short head start and win when they fire.
function watchTaps(el) {
  let start = null;
  el.addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    start = e.touches.length === 1 ? {x: t.clientX, y: t.clientY, time: Date.now()} : null;
  }, {passive: true, capture: true});
  el.addEventListener("touchmove", (e) => {
    const t = e.touches[0];
    if (start && Math.hypot(t.clientX - start.x, t.clientY - start.y) > 10) start = null;
  }, {passive: true, capture: true});
  el.addEventListener("touchend", (e) => {
    if (!start || e.touches.length || Date.now() - start.time > 600) {start = null; return;}
    const {x, y} = start, at = Date.now(); start = null;
    setTimeout(() => {
      if (!map || handledAt >= at) return;
      const rect = el.getBoundingClientRect(), lnglat = map.containerToLngLat(new AMap.Pixel(x - rect.left, y - rect.top));
      handledAt = Date.now();
      if (!pickPoint(lnglat)) nearestPoi(lnglat);
    }, 320);
  }, {passive: true, capture: true});
}
// A base-map label (e.g. 综合实验大楼) tapped on a phone: resolve the nearest AMap POI.
// The place API needs keywords; an OR-list of common campus words covers labelled buildings.
const TAP_KEYWORDS = "成都理工大学|楼|馆|中心|食堂|餐厅|驿站|学院|门|超市|医院";
async function nearestPoi(lnglat) {
  if (!inArea(lnglat.getLng(), lnglat.getLat())) return;
  const id = discoveryId, selection = ++hotspotSequence;
  try {
    const service = await placeSearch();
    const center = [lnglat.getLng(), lnglat.getLat()];
    const value = await timed(new Promise((resolve, reject) => service.searchNearBy(TAP_KEYWORDS, center, 60, (status, v) => {
      if (status === "complete") resolve(v); else if (status === "no_data") resolve(null); else reject(new Error("nearby"));
    })), "nearby timeout");
    const pois = (value?.poiList?.pois || []).filter((p) => p.location && !/公交/.test(p.type || ""));
    pois.sort((a, b) => AMap.GeometryUtil.distance(center, a.location) - AMap.GeometryUtil.distance(center, b.location));
    const best = pois[0] && AMap.GeometryUtil.distance(center, pois[0].location) <= 45 ? serialisePoi(pois[0]) : null;
    if (best && id === discoveryId && selection === hotspotSequence) notify("poi-selection", {request_id: id, place: best});
  } catch { /* a tap on empty ground is fine */ }
}
// ---- 理小龙 guide: pitched 3D camera following a dinosaur along the route -------------
async function startDino(data) {
  stopDino();
  const token = ++dinoToken;
  const [{createGuide}, walk] = await Promise.all([import("/assets/dino3d.mjs"), import("/assets/v2/route-walk.mjs")]);
  if (token !== dinoToken) return;
  const track = walk.buildTrack(routeGeometry);
  if (track.pts.length < 2) return;
  const gl = (() => {try {return !!document.createElement("canvas").getContext("webgl2");} catch {return false;}})();
  const use3d = walk.canUse3d({webgl: gl && AMap.Browser?.isWebGL !== false, cores: navigator.hardwareConcurrency,
    memory: navigator.deviceMemory, reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches});
  const created = await createGuide(map, {use3d: data.guide === "3d" ? gl && AMap.Browser?.isWebGL !== false : data.guide === "sprite" ? false : use3d});
  if (token !== dinoToken) {created.destroy(); return;}
  guide = created;
  const start = walk.pointAt(track, 0);
  dinoState = {walk, track, demo: data.demo === true, speed: clampSpeed(data.speed), d: 0, shown: {...start},
    bearing: start.bearing, compass: null, gps: null, arrived: false, last: performance.now(), introUntil: performance.now() + 950};
  document.body.dataset.guide = guide.kind;
  map.setStatus({dragEnable: false, zoomEnable: true, rotateEnable: true, pitchEnable: true}); // pitch/rotation are no-ops while disabled
  map.setZoomAndCenter(18.6, [start.lng, start.lat], false, 900);
  map.setRotation((360 - start.bearing) % 360, false, 900);
  if (guide.kind === "3d") map.setPitch(58, false, 900);
  notify("dino-ready", {kind: guide.kind});
  dinoRaf = requestAnimationFrame(dinoFrame);
}
const clampSpeed = (v) => (Number.isFinite(v) ? Math.min(30, Math.max(1, v)) : 9);
function setDinoDemo(demo, speed) {
  dinoState.demo = demo; if (Number.isFinite(speed)) dinoState.speed = clampSpeed(speed);
  if (!demo) dinoState.gps = null;
}
function dinoFrame(now) {
  if (!guide || !dinoState) return;
  const s = dinoState, {walk, track} = s, dt = Math.min(0.1, (now - s.last) / 1000); s.last = now;
  let target, walking = false;
  if (s.demo) {
    if (!s.arrived) {s.d = Math.min(track.total, s.d + s.speed * dt); walking = s.d < track.total;}
    target = walk.pointAt(track, s.d);
  } else if (s.gps) {
    // Snap the GPS fix onto the route when it is close; otherwise use the raw fix.
    const near = walk.project(track, s.gps);
    target = near.off < 25 ? walk.pointAt(track, near.d) : {lng: s.gps[0], lat: s.gps[1], bearing: s.bearing};
    if (near.off < 25) s.d = near.d;
    const moved = walk.meters([s.shown.lng, s.shown.lat], [target.lng, target.lat]);
    walking = moved > 0.4;
  } else target = s.shown;
  // Ease the shown position toward the target (GPS jumps glide), heading toward the travel
  // direction or the compass when standing still.
  const k = s.demo ? 1 : 1 - Math.exp(-dt / 0.6);
  s.shown = {lng: s.shown.lng + (target.lng - s.shown.lng) * k, lat: s.shown.lat + (target.lat - s.shown.lat) * k};
  const want = !s.demo && !walking && Number.isFinite(s.compass) ? s.compass : target.bearing;
  s.bearing = walk.easeBearing(s.bearing, want, dt, s.demo ? 0.3 : 0.5);
  guide.setPose({lng: s.shown.lng, lat: s.shown.lat, bearing: s.bearing}, walking, dt);
  // Camera behind and above: the dino stays a little below the screen centre, heading up.
  if (now > s.introUntil) {
    map.setRotation((360 - s.bearing) % 360, true);
    map.setCenter(aheadOf(s.shown, s.bearing, 22), true);
  }
  if (!s.arrived && track.total - s.d < (s.demo ? 0.5 : 12)) {
    s.arrived = true; notify("dino-arrived");
  }
  dinoRaf = requestAnimationFrame(dinoFrame);
}
function aheadOf(p, bearing, metres) {
  const r = bearing * Math.PI / 180, dLat = metres * Math.cos(r) / 111320, dLng = metres * Math.sin(r) / (111320 * Math.cos(p.lat * Math.PI / 180));
  return [p.lng + dLng, p.lat + dLat];
}
function stopDino() {
  dinoToken++;
  if (dinoRaf) cancelAnimationFrame(dinoRaf);
  dinoRaf = 0;
  if (guide) {
    guide.destroy(); guide = null; dinoState = null; delete document.body.dataset.guide;
    if (map) {
      map.setPitch(0, true); map.setRotation(0, true);
      map.setStatus({dragEnable: true, zoomEnable: true, rotateEnable: true, pitchEnable: false});
    }
  }
}
notify("frame-ready");
