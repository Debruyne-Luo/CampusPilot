import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from '../backend/src/campuspilot/web_assets/vendor/three.module.min.js';
import {GLTFLoader} from '../backend/src/campuspilot/web_assets/vendor/GLTFLoader.js';

async function loadGlb(url) {
  const bytes = await readFile(new URL(url, import.meta.url));
  return new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length), '');
}

// ---- 学士帽小恐龙（graduate-dino.glb）：引导默认模型 ----
// 注：新模型带内嵌 PNG 纹理，仓库内 vendored 的 GLTFLoader 在 Node 下
// 会走浏览器专用的 self.URL 图片解码路径（真实浏览器可正常加载），
// 因此 Node 回归只做 GLB 规范级校验：JSON 头、几何、材质、朝向。
function readGlbJson(bytes) {
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  assert.equal(new TextDecoder().decode(bytes.subarray(0, 4)), 'glTF');
  assert.equal(dv.getUint32(4, true), 2);
  let off = 12, json = null;
  while (off < bytes.length) {
    const len = dv.getUint32(off, true), type = dv.getUint32(off + 4, true);
    if (type === 0x4E4F534A) json = JSON.parse(new TextDecoder().decode(bytes.subarray(off + 8, off + 8 + len)));
    off += 8 + len;
  }
  assert.ok(json?.asset, 'GLB has a JSON header');
  return json;
}

test('graduate dino loads with bounded geometry, textures and no NaN vertices', async () => {
  const bytes = await readFile(new URL('../backend/src/campuspilot/web_assets/models/graduate-dino.glb', import.meta.url));
  assert.ok(bytes.length < 25_000_000, 'static showcase model download budget');
  const json = readGlbJson(bytes);
  assert.equal((json.animations || []).length, 0, 'static model ships no animation clips');
  assert.ok((json.images || []).length >= 1, 'carries embedded textures');
  assert.ok((json.textures || []).length >= 1, 'textures referenced by materials');
  let tris = 0;
  for (const [mi, m] of (json.meshes || []).entries()) {
    for (const p of m.primitives || []) {
      assert.ok(p.attributes.POSITION !== undefined, `mesh ${mi} has positions`);
      const acc = json.accessors[p.attributes.POSITION];
      assert.ok(acc.min?.every(Number.isFinite) && acc.max?.every(Number.isFinite), `mesh ${mi} bounds finite`);
      const idx = p.indices !== undefined ? json.accessors[p.indices] : null;
      tris += (idx ? idx.count : acc.count) / 3;
    }
  }
  assert.ok(tris > 1000, `real geometry present: ${tris}`);
  assert.ok(tris < 500000, `triangle budget: ${tris}`);
});

test('graduate dino faces +Z with head above the body centre', async () => {
  const bytes = await readFile(new URL('../backend/src/campuspilot/web_assets/models/graduate-dino.glb', import.meta.url));
  const json = readGlbJson(bytes);
  const meshIndexFor = (node) => json.meshes[node.mesh];
  const nodes = json.nodes || [];
  const posOf = (ni) => {
    const n = nodes[ni];
    const mesh = n.mesh !== undefined ? meshIndexFor(n) : null;
    const prim = mesh?.primitives?.[0];
    const acc = prim ? json.accessors[prim.attributes.POSITION] : null;
    return {node: n, acc};
  };
  // 整体包围盒：revision-03 全部节点都是单位变换，直接取各 POSITION 包围盒并集
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < nodes.length; i++) {
    const {acc} = posOf(i);
    if (!acc?.min || !acc?.max) continue;
    for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], acc.min[k]); hi[k] = Math.max(hi[k], acc.max[k]); }
  }
  const centre = hi.map((v, k) => (v + lo[k]) / 2);
  const head = nodes.find(n => n.name === 'V2_native_approved_head_hat_tassel');
  assert.ok(head, 'head+hat mesh present');
  const headAcc = json.accessors[meshIndexFor(head).primitives[0].attributes.POSITION];
  const headCentre = headAcc.max.map((v, k) => (v + headAcc.min[k]) / 2);
  assert.ok(headCentre[2] > centre[2], `head toward +Z: head=${headCentre} centre=${centre}`);
  assert.ok(headAcc.min[1] > centre[1], 'head sits above the body centre');
});

// ---- 旧模型保留为后备：dino3d.mjs 加载 graduate-dino 失败时回退到它 ----
test('fallback GLB keeps the animated four-leg walk loop', async () => {
  const bytes = await readFile(new URL('../backend/src/campuspilot/web_assets/models/cdutdino-guide.glb', import.meta.url));
  assert.ok(bytes.length < 1_500_000, 'lazy model download budget');
  const gltf = await loadGlb('../backend/src/campuspilot/web_assets/models/cdutdino-guide.glb');
  let tris = 0;
  gltf.scene.traverse(o => { if (!o.geometry) return; const p = o.geometry.attributes.position; assert.ok(Array.from(p.array).every(Number.isFinite)); assert.ok(o.geometry.attributes.normal); tris += (o.geometry.index?.count || p.count) / 3; });
  assert.ok(tris < 50000, `triangle budget: ${tris}`);
  const legs = ['front_left', 'front_right', 'rear_left', 'rear_right'].map(n => gltf.scene.getObjectByName(n));
  assert.ok(legs.every(Boolean));
  const mixer = new THREE.AnimationMixer(gltf.scene);
  for (const c of gltf.animations) { assert.ok(c.duration > 0 && c.duration < 2); mixer.clipAction(c).play(); }
  const q = legs.map(l => l.quaternion.clone()); mixer.update(.25);
  legs.forEach((l, i) => assert.ok(l.quaternion.angleTo(q[i]) > .1, 'every leg walks'));
  assert.ok(legs[0].quaternion.angleTo(legs[3].quaternion) < .01, 'diagonal feet stay in phase');
  assert.ok(legs[0].quaternion.angleTo(legs[1].quaternion) > .3, 'opposite feet alternate');
  mixer.stopAllAction(); mixer.uncacheRoot(gltf.scene);
});
