import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from '../backend/src/campuspilot/web_assets/vendor/three.module.min.js';

const source = readFileSync(new URL('../backend/src/campuspilot/web_assets/dino3d.mjs', import.meta.url), 'utf8')
  .replace('export async function createGuide', 'async function createGuide')
  .replace('await import("/assets/vendor/three.module.min.js")', 'testThree')
  .replace("await import('/assets/vendor/GLTFLoader.js')", '{GLTFLoader: TestLoader}');

// Synthetic geometry verifies the map contract independently of the GLB authoring axes.
function fixture(front) {
  const scene = new THREE.Group();
  const geometry = new THREE.BoxGeometry(2, 4, 2);
  const counts = {geometry: 0, material: 0, secondMaterial: 0, texture: 0, secondTexture: 0, image: 0};
  const image = {close: () => counts.image++};
  const texture = new THREE.Texture(image);
  const secondTexture = new THREE.Texture(image);
  const material = new THREE.MeshStandardMaterial({map: texture, normalMap: texture});
  const secondMaterial = new THREE.MeshStandardMaterial({map: secondTexture});
  scene.add(new THREE.Mesh(geometry, [material, secondMaterial]));
  scene.add(new THREE.Mesh(geometry, material));
  for (const [name, resource] of Object.entries({geometry, material, secondMaterial, texture, secondTexture})) {
    resource.addEventListener('dispose', () => counts[name]++);
  }
  return {scene, animations: [], front: new THREE.Vector3(...front), counts};
}

function harness({failed = [], model = fixture([0, 0, 1])} = {}) {
  const requests = [], added = [], removed = [];
  let rendered = null, rendererDisposals = 0, mapRenders = 0;
  class Renderer {
    resetState() {}
    render(scene) { rendered = scene; }
    dispose() { rendererDisposals++; }
  }
  class Layer { constructor(options) { this.options = options; } }
  class Marker {
    constructor(options) { this.options = options; }
    setPosition(position) { this.position = position; }
  }
  const map = {
    customCoords: {
      setCenter() {},
      getCameraParams: () => ({near: 1, far: 1000000, fov: 60, up: [0, 0, 1], lookAt: [0, 0, 0], position: [100, 100, 100]}),
      lngLatsToCoords: points => points.map(([lng, lat]) => [lng * 100000, lat * 100000]),
    },
    getCenter: () => ({toArray: () => [0, 0]}),
    getSize: () => ({width: 1000, height: 800}),
    add(layer) { added.push(layer); layer.options?.init?.({canvas: {}}); },
    remove(layer) { removed.push(layer); },
    render() { mapRenders++; added[0]?.options?.render?.(); },
  };
  const context = vm.createContext({
    testThree: {...THREE, WebGLRenderer: Renderer},
    TestLoader: class { async parseAsync() { return model; } },
    AMap: {GLCustomLayer: Layer, Marker},
    fetch: async url => {
      requests.push(url);
      return {ok: !failed.includes(url), arrayBuffer: async () => new ArrayBuffer(0)};
    },
    AbortSignal,
    window: {innerWidth: 1000, innerHeight: 800},
    document: {createElement: () => ({classList: {toggle() {}}})},
  });
  vm.runInContext(source + '\nglobalThis.createGuideForTest = createGuide;', context);
  return {
    create: () => context.createGuideForTest(map, {use3d: true}), model, requests, added, removed,
    rendered: () => rendered,
    rendererDisposals: () => rendererDisposals,
    mapRenders: () => mapRenders,
  };
}

const graduateUrl = '/assets/models/graduate-dino.glb';
const fallbackUrl = '/assets/models/cdutdino-guide.glb';
const near = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 1e-8, `${message}: ${actual} vs ${expected}`);

function assertHeading(h, bearing, x, y) {
  const direction = h.model.front.clone().applyQuaternion(h.model.scene.getWorldQuaternion(new THREE.Quaternion()));
  near(direction.x, x, `bearing ${bearing} forward x`);
  near(direction.y, y, `bearing ${bearing} forward y`);
  near(direction.z, 0, `bearing ${bearing} horizontal forward`);
}

test('default graduate model faces the route, stands on the ground and has the guide height', async () => {
  const h = harness(), guide = await h.create();
  assert.equal(guide.kind, '3d');
  assert.deepEqual(h.requests, [graduateUrl]);
  guide.setPose({lng: 0, lat: 0, bearing: 0}, false, .016);
  assertHeading(h, 0, 0, 1);
  const anchor = h.rendered().children.find(child => child.isGroup);
  const box = new THREE.Box3().setFromObject(anchor);
  near(box.min.z, 0, 'ground contact');
  near(box.max.z, 14 * 10 / 11.12, '14 metre guide height');
  guide.setPose({lng: 0, lat: 0, bearing: 90}, false, .016);
  assertHeading(h, 90, 1, 0);
  guide.destroy();
});

test('failed graduate download preserves fallback model forward axis', async () => {
  const h = harness({failed: [graduateUrl], model: fixture([1, 0, 0])});
  const guide = await h.create();
  assert.equal(guide.kind, '3d');
  assert.deepEqual(h.requests, [graduateUrl, fallbackUrl]);
  guide.setPose({lng: 0, lat: 0, bearing: 0}, false, .016);
  assertHeading(h, 0, 0, 1);
  guide.setPose({lng: 0, lat: 0, bearing: 90}, false, .016);
  assertHeading(h, 90, 1, 0);
  guide.destroy();
});

test('both unavailable models fall back to a usable sprite', async () => {
  const h = harness({failed: [graduateUrl, fallbackUrl]});
  const guide = await h.create();
  assert.equal(guide.kind, 'sprite');
  assert.deepEqual(h.requests, [graduateUrl, fallbackUrl]);
  guide.setPose({lng: 1, lat: 2, bearing: 90}, true, .016);
  assert.deepEqual(Array.from(h.added[0].position), [1, 2]);
  guide.destroy();
  assert.deepEqual(h.removed, h.added);
});

test('destroy releases shared geometry, materials, textures and image bitmaps once, including repeated calls', async () => {
  const h = harness(), guide = await h.create();
  guide.setPose({lng: 0, lat: 0, bearing: 0}, false, .016);
  guide.destroy();
  guide.destroy();
  assert.deepEqual(h.model.counts, {geometry: 1, material: 1, secondMaterial: 1, texture: 1, secondTexture: 1, image: 1});
  assert.equal(h.rendererDisposals(), 1);
  assert.deepEqual(h.removed, h.added);
  const renders = h.mapRenders();
  guide.setPose({lng: 0, lat: 0, bearing: 0}, true, .016);
  assert.equal(h.mapRenders(), renders, 'destroyed guide cannot request more map frames');
});
