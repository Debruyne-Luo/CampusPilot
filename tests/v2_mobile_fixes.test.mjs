import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const base = "../backend/src/campuspilot/web_assets/v2/";
const sh = await import(base + "sheet.mjs");
const { glyphFor, filterList } = await import(base + "places.mjs");
const gcj = (longitude, latitude) => ({ longitude, latitude, coordinate_system: "GCJ02" });

test("sheet follows the finger within bounds with a soft rubber band", () => {
  assert.equal(sh.sheetOffset("expanded", 540, 66), 0);
  assert.equal(sh.sheetOffset("collapsed", 540, 66), 474);
  assert.equal(sh.dragOffset(0, 120, 474), 120);
  assert.equal(sh.dragOffset(474, -200, 474), 274);
  assert.ok(sh.dragOffset(0, -100, 474) < 0 && sh.dragOffset(0, -100, 474) >= -24);
  assert.ok(sh.dragOffset(474, 400, 474) <= 474 + 24);
  assert.equal(sh.visibleHeight(540, 474), 66);
});

test("release velocity uses the recent samples and a flick beats position", () => {
  assert.equal(sh.releaseVelocity([[0, 10]]), 0);
  near(sh.releaseVelocity([[0, 0], [500, 0], [550, 40], [600, 100]]), 1, 1e-9);
  const s = sh.initialSheet();
  // Dragged only slightly (position says expanded) but flicked down: collapse.
  assert.equal(sh.reduceSheet(s, { type: "drag-end", dy: -100, velocity: 0.9 }).state, "collapsed");
  const c = { ...s, state: "collapsed" };
  assert.equal(sh.reduceSheet(c, { type: "drag-end", dy: 100, velocity: -0.9 }).state, "expanded");
  assert.equal(sh.reduceSheet(c, { type: "drag-end", dy: -100, velocity: 0 }).state, "expanded");
  assert.equal(sh.reduceSheet(s, { type: "collapse" }).state, "collapsed");
  assert.equal(sh.reduceSheet(s, { type: "noop" }), s);
});
function near(a, b, eps) { assert.ok(Math.abs(a - b) <= eps, `${a} ≉ ${b}`); }

test("pin glyphs are recognisable per category", () => {
  assert.equal(glyphFor({ category: "service", tags: ["parcel"], name: "菜鸟驿站" }), "parcel");
  assert.equal(glyphFor({ category: "service", name: "校医院" }), "medical");
  assert.equal(glyphFor({ category: "service", name: "校园一卡通中心" }), "card");
  assert.equal(glyphFor({ category: "dining", name: "芙蓉食堂" }), "dining");
  assert.equal(glyphFor({ category: "library", name: "水上图书馆" }), "library");
  assert.equal(glyphFor({ category: "teaching", name: "逸夫楼" }), "teaching");
  assert.equal(glyphFor({ category: "office", name: "行政楼" }), "office");
  assert.equal(glyphFor({}), "service");
});

test("a category chip lists its located places, hotspots first; 全部 lists none", () => {
  const places = [
    { place_id: "a", name: "A", category: "dining", position: gcj(104.1, 30.6) },
    { place_id: "b", name: "B", category: "dining", hotspot: true, position: gcj(104.1, 30.6) },
    { place_id: "c", name: "C", category: "dining", position: null },
    { place_id: "d", name: "D", category: "office", position: gcj(104.1, 30.6) },
  ];
  assert.deepEqual(filterList(places, "dining").map((p) => p.place_id), ["b", "a"]);
  assert.deepEqual(filterList(places, "all"), []);
});

test("map frame uses one label layer (no per-marker DOM) and handles iOS taps", async () => {
  const src = await readFile(new URL("../backend/src/campuspilot/web_assets/map-frame.js", import.meta.url), "utf8");
  assert.match(src, /AMap\.LabelsLayer/);
  assert.match(src, /AMap\.LabelMarker/);
  assert.doesNotMatch(src, /new AMap\.Marker\(\{position: \[place/);
  assert.match(src, /touchend/);
  assert.match(src, /route-pick-point/);
});
