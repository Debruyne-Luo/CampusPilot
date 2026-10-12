import test from "node:test";
import assert from "node:assert/strict";
const base = "../backend/src/campuspilot/web_assets/v2/";
const geo = await import(base + "geo.mjs");
const { initialOrigin, reduceOrigin, routeOrigin, originLabel } = await import(base + "origin.mjs");
const hd = await import(base + "heading.mjs");
const { initialSheet, reduceSheet } = await import(base + "sheet.mjs");
const { visiblePlaces, searchPlaces } = await import(base + "places.mjs");

const gcj = (longitude, latitude, extra = {}) => ({ longitude, latitude, coordinate_system: "GCJ02", ...extra });
const near = (a, b, eps) => assert.ok(Math.abs(a - b) <= eps, `${a} ≉ ${b}`);

test("WGS84 fixes are shifted to GCJ02 in China and distances are in metres", () => {
  const w = { longitude: 104.1475, latitude: 30.675, coordinate_system: "WGS84" };
  const g = geo.toGcj02(w);
  assert.equal(g.coordinate_system, "GCJ02");
  const shift = geo.distanceMeters(gcj(w.longitude, w.latitude), g);
  assert.ok(shift > 200 && shift < 800, `GCJ shift ${shift}`); // ~0.5 km in Chengdu
  assert.deepEqual(geo.toGcj02({ longitude: 2.35, latitude: 48.85, coordinate_system: "WGS84" }), gcj(2.35, 48.85));
  assert.equal(geo.toGcj02({ longitude: 999, latitude: 0, coordinate_system: "WGS84" }), null);
  near(geo.distanceMeters(gcj(104.14, 30.67), gcj(104.15, 30.67)), 957, 5);
  assert.equal(geo.formatDistance(347), "350 米");
  assert.equal(geo.formatDistance(1540), "1.5 公里");
  assert.equal(geo.formatDistance(NaN), "");
});

test("places rank nearest-first with a recommendation only when the origin is known", () => {
  const places = [
    { place_id: "far", position: gcj(104.16, 30.68) },
    { place_id: "none", position: null },
    { place_id: "close", position: gcj(104.1476, 30.6751) },
  ];
  const unknown = geo.rankPlaces(places, null);
  assert.deepEqual(unknown.rows.map((r) => r.place.place_id), ["far", "none", "close"]);
  assert.equal(unknown.recommended, null);
  const ranked = geo.rankPlaces(places, gcj(104.1475, 30.675));
  assert.deepEqual(ranked.rows.map((r) => r.place.place_id), ["close", "far", "none"]);
  assert.equal(ranked.recommended.place_id, "close");
  assert.equal(ranked.rows[2].distance, null);
});

test("origin selection: GPS, map point, place; manual choices win over later GPS", () => {
  let s = initialOrigin();
  assert.equal(routeOrigin(s), null);
  assert.equal(originLabel(s), "未设置起点");
  const fix = { longitude: 104.1475, latitude: 30.675, coordinate_system: "WGS84" };
  s = reduceOrigin(s, { type: "gps", position: fix });
  assert.equal(s.source, "gps"); assert.deepEqual(routeOrigin(s), fix);
  s = reduceOrigin(s, { type: "pick-start" });
  assert.equal(originLabel(s), "在地图上点选起点…");
  s = reduceOrigin(s, { type: "map", position: gcj(104.15, 30.676), label: "地图选点" });
  assert.equal(s.source, "map"); assert.equal(s.picking, false); assert.equal(originLabel(s), "从 地图选点 出发");
  assert.equal(reduceOrigin(s, { type: "gps", position: fix }), s, "manual origin is not overwritten by GPS");
  const lib = { place_id: "lib", name: "东区图书馆", position: gcj(104.1515, 30.6761) };
  s = reduceOrigin(s, { type: "place", place: lib });
  assert.equal(s.source, "place"); assert.equal(s.placeId, "lib"); assert.deepEqual(routeOrigin(s), gcj(104.1515, 30.6761));
  assert.equal(reduceOrigin(s, { type: "place", place: { place_id: "x", position: null } }), s);
  s = reduceOrigin(s, { type: "use-gps" });
  assert.equal(routeOrigin(s), null);
  s = reduceOrigin(reduceOrigin(s, { type: "gps", position: fix }), { type: "gps-denied" });
  assert.equal(s.source, "none");
  assert.equal(reduceOrigin(initialOrigin(), { type: "map", position: { longitude: "x" } }).position, null);
});

test("heading: iOS compass, Android absolute alpha, wrap-around smoothing, GPS fallback", () => {
  assert.equal(hd.headingFromEvent({ webkitCompassHeading: 370 }), 10);
  assert.equal(hd.headingFromEvent({ absolute: true, alpha: 90 }), 270);
  assert.equal(hd.headingFromEvent({ absolute: true, alpha: 90 }, 90), 0); // landscape
  assert.equal(hd.headingFromEvent({ absolute: false, alpha: 90 }), null);
  assert.equal(hd.headingFromEvent(null), null);
  assert.equal(hd.delta(350, 10), 20); assert.equal(hd.delta(10, 350), -20);
  const s = hd.smoothHeading(350, 10, 0.5);
  assert.equal(s, 0, "smooths across north instead of swinging through 180");
  assert.equal(hd.smoothHeading(null, 45), 45);
  assert.equal(hd.smoothHeading(45, NaN), 45);
  assert.equal(hd.courseFromFix({ heading: 90, speed: 1.2 }), 90);
  assert.equal(hd.courseFromFix({ heading: 90, speed: 0.2 }), null, "course is noise when standing still");
  assert.deepEqual(hd.viewRotation(90, true), { map: 270, arrow: 0 });
  assert.deepEqual(hd.viewRotation(90, false), { map: 0, arrow: 90 });
  assert.equal(hd.needsPermission({ requestPermission() {} }), true);
  assert.equal(hd.needsPermission(undefined), false);
  let now = 0;
  const t = hd.createHeadingTracker({ now: () => now, staleMs: 3000, factor: 1 });
  assert.equal(t.gps({ heading: 180, speed: 2 }), 180); assert.equal(t.source, "gps");
  now = 10; assert.equal(t.compass({ webkitCompassHeading: 90 }), 90); assert.equal(t.source, "compass");
  now = 1000; assert.equal(t.gps({ heading: 270, speed: 2 }), 90, "fresh compass wins over GPS course");
  now = 5000; assert.notEqual(t.gps({ heading: 270, speed: 2 }), 90, "stale compass yields to GPS course");
});

test("bottom sheet: swipe, flick, guidance auto-collapse and restore", () => {
  let s = initialSheet();
  assert.equal(s.state, "expanded");
  assert.equal(reduceSheet(s, { type: "drag-end", dy: 10 }), s, "small drags are ignored");
  s = reduceSheet(s, { type: "drag-end", dy: 80 }); assert.equal(s.state, "collapsed");
  s = reduceSheet(s, { type: "drag-end", dy: -20, velocity: -0.9 }); assert.equal(s.state, "expanded", "flick up expands");
  s = reduceSheet(s, { type: "guidance-start" }); assert.deepEqual([s.state, s.guiding], ["collapsed", true]);
  s = reduceSheet(s, { type: "drag-end", dy: -80 }); assert.equal(s.state, "expanded", "user can still peek during guidance");
  assert.equal(reduceSheet(s, { type: "guidance-start" }), s);
  s = reduceSheet(s, { type: "guidance-stop" }); assert.deepEqual([s.state, s.guiding], ["expanded", false]);
  s = reduceSheet(reduceSheet(reduceSheet(initialSheet(), { type: "toggle" }), { type: "guidance-start" }), { type: "guidance-stop" });
  assert.equal(s.state, "collapsed", "restores the state from before guidance");
  assert.equal(reduceSheet(s, { type: "focus-input" }).state, "expanded");
});

test("map shows hotspots plus revealed places; chips show a whole category; search", () => {
  const places = [
    { place_id: "a", name: "珙桐餐厅", aliases: ["珙桐食堂"], category: "dining", hotspot: true },
    { place_id: "b", name: "逸夫楼", aliases: [], category: "teaching", hotspot: false },
    { place_id: "c", name: "香樟餐厅", aliases: ["香樟食堂"], category: "dining", hotspot: false },
  ];
  assert.deepEqual(visiblePlaces(places).map((p) => p.place_id), ["a"]);
  assert.deepEqual(visiblePlaces(places, "all", new Set(["b"])).map((p) => p.place_id), ["a", "b"]);
  assert.deepEqual(visiblePlaces(places, "all", new Set(), "c").map((p) => p.place_id), ["a", "c"]);
  assert.deepEqual(visiblePlaces(places, "dining").map((p) => p.place_id), ["a", "c"]);
  assert.deepEqual(searchPlaces(places, "食堂").map((p) => p.place_id), ["a", "c"]);
  assert.deepEqual(searchPlaces(places, "逸夫楼").map((p) => p.place_id), ["b"]);
  assert.deepEqual(searchPlaces(places, " 香樟 ").map((p) => p.place_id), ["c"]);
  assert.deepEqual(searchPlaces(places, ""), []);
});
