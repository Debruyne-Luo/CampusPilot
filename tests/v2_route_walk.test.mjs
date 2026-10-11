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

test("statue guide model: glossy teal sauropod with cap, animated, about 6k triangles", async () => {
  const THREE = await import("../backend/src/campuspilot/web_assets/vendor/three.module.min.js");
  const { buildDino, poseDino } = await import("../backend/src/campuspilot/web_assets/dino3d.mjs");
  const d = buildDino(THREE);
  let tris = 0, phong = 0;
  const colors = new Set();
  d.group.traverse((o) => {
    if (!o.geometry) return;
    tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3;
    if (o.material.isMeshPhongMaterial) { phong++; assert.notEqual(o.material.flatShading, true); }
    colors.add(o.material.color.getHex());
  });
  assert.ok(tris < 6100, `triangles ${tris}`); assert.ok(phong > 10);
  for (const c of [0x6fc2bd, 0x15181c, 0xf2c230, 0x8c3f22, 0x1f3550]) assert.ok(colors.has(c), c.toString(16));
  // Long neck: the head sits high above the body.
  const top = new THREE.Vector3(); d.group.updateMatrixWorld(true); d.head.getWorldPosition(top);
  assert.ok(top.z > 7, `head z ${top.z}`); assert.equal(d.legs.length, 4);
  poseDino(d, Math.PI / 2, true, 0.05);
  assert.ok(d.legL.rotation.y > 0.4 && d.legR.rotation.y < -0.4 && d.legs[3].rotation.y > 0.4 && d.body.position.z >= 0);
  assert.equal(d.eyes[0].scale.z, 0.12); // blinking at t % 3.2 < 0.12
  poseDino(d, 0, false, 1);
  assert.equal(d.legL.rotation.y, 0); assert.equal(d.eyes[0].scale.z, 1);
});
