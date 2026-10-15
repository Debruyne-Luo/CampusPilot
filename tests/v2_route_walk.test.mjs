import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const w = await import("../backend/src/campuspilot/web_assets/v2/route-walk.mjs");
const near = (a, b, eps, msg) => assert.ok(Math.abs(a - b) <= eps, `${msg || ""} ${a} ≉ ${b}`);

// An L-shaped walk: ~111 m north, then ~96 m east (at 30.67°N).
const L = [[104.14, 30.67], [104.14, 30.671], [104.141, 30.671]];

test("track length and interpolation along an L-shaped route", () => {
  const t = w.buildTrack([...L, L[2], [NaN, 1]]); // duplicate and invalid points dropped
  assert.equal(t.pts.length, 3);
  near(t.cum[1], 111.2, 0.5); near(t.total, 111.2 + 95.7, 1);
  const mid = w.pointAt(t, 55.6);
  near(mid.lat, 30.6705, 1e-6); near(mid.lng, 104.14, 1e-9); near(mid.bearing, 0, 0.01, "north");
  const turned = w.pointAt(t, 150);
  near(turned.bearing, 90, 0.01, "east"); assert.equal(turned.index, 1); assert.equal(turned.done, false);
  assert.equal(w.pointAt(t, 1e6).done, true);
  assert.deepEqual([w.pointAt(t, -5).lng, w.pointAt(t, -5).lat], L[0]);
  assert.equal(w.pointAt(w.buildTrack([]), 3), null);
});

test("GPS fixes project onto the nearest segment", () => {
  const t = w.buildTrack(L);
  const p = w.project(t, [104.1401, 30.6705]); // ~10 m east of the first leg
  near(p.d, 55.6, 1); near(p.off, 9.6, 0.5);
  const q = w.project(t, [104.1405, 30.6712]); // ~22 m north of the second leg
  near(q.d, 111.2 + 47.9, 1); near(q.off, 22.2, 0.5);
});

test("heading eases toward turns across the 0/360 wrap, frame-rate independent", () => {
  assert.equal(w.easeBearing(NaN, 45, 0.016), 45);
  const a = w.easeBearing(350, 10, 0.35, 0.35); // one time constant ≈ 63% of the 20° turn
  near(a, (350 + 20 * (1 - Math.exp(-1))) % 360, 1e-9);
  let x = 350, y = 350;
  for (let i = 0; i < 60; i++) x = w.easeBearing(x, 10, 1 / 60);
  for (let i = 0; i < 30; i++) y = w.easeBearing(y, 10, 1 / 30);
  near(x, y, 1e-9, "60fps vs 30fps");
  near(w.bearing([104.14, 30.67], [104.13, 30.67]), 270, 0.01);
});

test("3D guide only with WebGL and headroom, else the 2D sprite", () => {
  assert.equal(w.canUse3d({ webgl: true, cores: 8, memory: 8 }), true);
  assert.equal(w.canUse3d({ webgl: true }), true);
  assert.equal(w.canUse3d({ webgl: false, cores: 8 }), false);
  assert.equal(w.canUse3d({ webgl: true, cores: 2 }), false);
  assert.equal(w.canUse3d({ webgl: true, memory: 2 }), false);
  assert.equal(w.canUse3d({ webgl: true, reducedMotion: true }), false);
});
