import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { toGcj02 } from "../backend/src/campuspilot/web_assets/v2/geo.mjs";

// All coordinates, fixes and SDK failures below are synthetic; no device GPS/network.
const assets = new URL("../backend/src/campuspilot/web_assets/", import.meta.url);
function frame() {
  const messages = [];
  const context = vm.createContext({
    matchMedia: () => ({ matches: false }), window: { addEventListener() {} },
    location: { origin: "https://synthetic.invalid" }, parent: { postMessage: m => messages.push(m) },
    AMap: { convertFrom() { throw new Error("SYNTHETIC provider outage"); } },
    setTimeout, clearTimeout,
  });
  const file = fileURLToPath(new URL("map-frame.js", assets));
  new vm.Script(readFileSync(file, "utf8"), {
    filename: file, importModuleDynamically: vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER,
  }).runInContext(context);
  return { context, messages, run: code => vm.runInContext(code, context) };
}

test("GPS conversion succeeds without AMap service and agrees with distance ranking", async () => {
  const f = frame();
  const fix = { longitude: 104.14, latitude: 30.67, coordinate_system: "WGS84" };
  f.context.fix = fix;
  assert.deepEqual(await f.run("convertPosition(fix)"), toGcj02(fix));
  assert.notEqual((await f.run("convertPosition(fix)")).longitude, fix.longitude);
});

test("GCJ02 stays unchanged and invalid/unknown coordinate systems are rejected", async () => {
  const f = frame();
  const p = { longitude: 1, latitude: 1, coordinate_system: "GCJ02" };
  f.context.fix = p;
  assert.equal(await f.run("convertPosition(fix)"), p);
  for (const bad of [null, { ...p, coordinate_system: "BD09" }, { ...p, longitude: NaN },
    { ...p, coordinate_system: "WGS84", latitude: 91 }]) {
    f.context.fix = bad;
    await assert.rejects(f.run("convertPosition(fix)"), /origin/);
  }
});

test("late conversion after navigation exit cannot draw or report a stale location", async () => {
  const f = frame();
  f.run("navigationId=7; routeId=4; convertPosition=()=>new Promise(resolve=>globalThis.finish=resolve)");
  const update = f.run("updateLocation({request_id:4, accuracy:5, position:{}})");
  f.run("clearLocation()");
  f.context.finish({ longitude: 1, latitude: 1, coordinate_system: "GCJ02" });
  await update;
  assert.equal(f.messages.filter(m => m.action === "guidance-position").length, 0);
  assert.equal(f.run("locationLayer"), null);
});

class Element {
  constructor(tag, text) { this.tag = tag; this.textContent = text; this.children = []; this.handlers = {}; this.classList = { add() {} }; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute() {}
  addEventListener(name, fn) { this.handlers[name] = fn; }
}
function guidance() {
  const slot = new Element("div"), messages = [], watches = [], cleared = [];
  const context = vm.createContext({
    window: { isSecureContext: true, addEventListener() {} },
    document: { querySelector: s => s === ".guidance-slot" ? slot : null, getElementById: () => null, addEventListener() {} },
    navigator: { geolocation: { watchPosition: (ok, fail) => { watches.push({ok, fail}); return 77; }, clearWatch: id => cleared.push(id) } },
    element: (tag, text) => new Element(tag, text), sendToMap: m => messages.push(m),
  });
  vm.runInContext(readFileSync(new URL("guidance.js", assets), "utf8"), context);
  const api = context.window.Guidance;
  api.start({ requestId: 4, target: {name: "SYNTHETIC"}, route: {
    geometry: [[1, 1], [1.001, 1]], stepEnds: [1], distance: 111, time: 80, steps: ["SYNTHETIC step"],
  }});
  return { api, slot, messages, watches, cleared };
}

test("failed location update stops GPS and offers an immediate retry, ignoring stale callbacks", () => {
  const g = guidance(), start = g.messages.find(m => m.action === "guidance-start");
  g.api.receive({ request_id: 4, navigation_id: start.navigation_id, status: "error" });
  assert.deepEqual(g.cleared, [77]);
  const nodes = g.slot.children[0].children;
  assert.ok(nodes.some(n => n.textContent === "当前位置暂时无法更新，请重试定位或查看分步指引。"));
  const retry = nodes.find(n => n.textContent === "重试定位");
  assert.ok(retry);
  retry.handlers.click();
  assert.equal(g.watches.length, 2);
  const before = g.messages.length;
  g.watches[0].ok({timestamp: Date.now(), coords: {longitude: 1, latitude: 1, accuracy: 5}});
  g.watches[0].fail({code: 1});
  g.api.receive({ request_id: 4, navigation_id: start.navigation_id, status: "error" });
  assert.equal(g.messages.length, before);
  assert.ok(g.slot.children[0].children.some(n => n.textContent === "正在获取当前位置…"));
  g.watches[1].ok({timestamp: Date.now(), coords: {longitude: 1, latitude: 1, accuracy: 5}});
  assert.equal(g.messages.at(-1).action, "guidance-update");
});
