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

test("guide is code-built (no model files) and Three.js is only loaded lazily", async () => {
  const dino = await readFile(new URL("../backend/src/campuspilot/web_assets/dino3d.mjs", import.meta.url), "utf8");
  const frame = await readFile(new URL("../backend/src/campuspilot/web_assets/map-frame.js", import.meta.url), "utf8");
  const shell = await readFile(new URL("../backend/src/campuspilot/web_assets/v2/index.html", import.meta.url), "utf8");
  assert.doesNotMatch(dino, /GLTFLoader|\.glb|\.gltf|\.fbx|\.obj["']/);
  assert.match(dino, /GLCustomLayer/); assert.match(dino, /import\("\/assets\/vendor\/three\.module\.min\.js"\)/);
  assert.doesNotMatch(dino, /^import /m);
  assert.match(frame, /import\("\/assets\/dino3d\.mjs"\)/);
  assert.doesNotMatch(shell + frame, /<script[^>]+three/);
  assert.doesNotMatch(frame, /AMap\.Buildings/);
});

test("statue guide model: one smooth glossy skin, cap, spots, animated, under 28k triangles", async () => {
  const THREE = await import("../backend/src/campuspilot/web_assets/vendor/three.module.min.js");
  const { buildDino, poseDino } = await import("../backend/src/campuspilot/web_assets/dino3d.mjs");
  const d = buildDino(THREE);
  let tris = 0, standard = 0;
  const colors = new Set();
  d.group.traverse((o) => {
    if (!o.geometry) return;
    tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3;
    if (o.material.isMeshStandardMaterial) standard++;
    if (o !== d.skin) colors.add(o.material.color.getHex());
  });
  assert.ok(tris < 28000, `triangles ${tris}`); assert.ok(standard > 10);
  assert.ok(d.skin.material.onBeforeCompile && d.skin.material.roughness < 0.45);
  for (const c of [0x1d1c20, 0xf0b13f, 0x7c3a22, 0x24324f, 0x6b331d]) assert.ok(colors.has(c), c.toString(16));
  // The skin is one closed surface: every edge is shared by exactly two triangles.
  const idx = d.skin.geometry.index.array, edges = new Map();
  for (let i = 0; i < idx.length; i += 3) for (let k = 0; k < 3; k++) {
    const a = idx[i + k], b = idx[i + ((k + 1) % 3)], key = a < b ? a + "," + b : b + "," + a;
    edges.set(key, (edges.get(key) || 0) + 1);
  }
  const open = [...edges.values()].filter((n) => n !== 2).length;
  assert.ok(open < edges.size * 0.002, `open edges ${open}`);
  // Head is large (≈36% of height) and sits on a short neck.
  d.skin.geometry.computeBoundingBox();
  assert.ok(d.skin.geometry.boundingBox.max.z > 9.8 && d.skin.geometry.boundingBox.min.z > -0.2);
  assert.equal(d.legs.length, 4);
  const before = d.skin.geometry.attributes.position.array.slice();
  poseDino(d, Math.PI / 2, true, 0.05);
  assert.ok(d.legL.rotation.y > 0.4 && d.legR.rotation.y < -0.4 && d.legs[3].rotation.y > 0.4);
  const after = d.skin.geometry.attributes.position.array;
  let moved = 0; for (let i = 0; i < after.length; i++) if (Math.abs(after[i] - before[i]) > 1e-3) moved++;
  assert.ok(moved > 1000, "walk pose bends the skin");
  assert.equal(d.eyes[0].scale.y, 0.12); // blinking at t % 3.2 < 0.12
  poseDino(d, 0, false, 1);
  assert.equal(d.legL.rotation.y, 0); assert.equal(d.eyes[0].scale.y, 1);
});
