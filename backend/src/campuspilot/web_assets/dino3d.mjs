// 理小龙 guide on the map: an original low-poly dinosaur built from primitives in a
// Three.js AMap.GLCustomLayer, or a 2D sprite marker when 3D is unavailable.
// Loaded lazily by map-frame.js only when walking guidance starts. Three.js r162 is vendored:
// the last release that still renders into AMap's WebGL 1 context (r163 dropped WebGL 1).
const GREEN = 0x3fae6a, DARK = 0x2c8a51, BELLY = 0xa5e2bd, WHITE = 0xffffff, EYE = 0x1d2b22, CHEEK = 0xf6a5a5;
const HEIGHT_M = 16; // exaggerated so the guide reads at street zoom

export function buildDino(THREE) {
  const mat = (color) => new THREE.MeshLambertMaterial({ color, flatShading: true });
  const g = new THREE.Group(), body = new THREE.Group();
  const mesh = (geo, color, x, y, z) => { const m = new THREE.Mesh(geo, mat(color)); m.position.set(x, y, z); return m; };
  // Model units: 1 = 1/10 of the dino height. Faces +x, z up.
  const torso = mesh(new THREE.IcosahedronGeometry(3, 1), GREEN, 0, 0, 4.2); torso.scale.set(1.25, 0.95, 1);
  const belly = mesh(new THREE.IcosahedronGeometry(2.3, 1), BELLY, 1.2, 0, 3.7); belly.scale.set(0.9, 0.85, 1);
  const head = mesh(new THREE.IcosahedronGeometry(2.1, 1), GREEN, 3.4, 0, 7.4); head.scale.set(1.25, 1, 0.95);
  const snout = mesh(new THREE.IcosahedronGeometry(1.2, 0), GREEN, 5.4, 0, 6.8); snout.scale.set(1.2, 0.9, 0.7);
  const eyeL = mesh(new THREE.SphereGeometry(0.62, 8, 6), WHITE, 4.6, 1.15, 8.1), eyeR = eyeL.clone(); eyeR.position.y = -1.15;
  const pupilL = mesh(new THREE.SphereGeometry(0.34, 8, 6), EYE, 5.1, 1.25, 8.1), pupilR = pupilL.clone(); pupilR.position.y = -1.25;
  const cheekL = mesh(new THREE.SphereGeometry(0.42, 6, 4), CHEEK, 4.4, 1.6, 6.8), cheekR = cheekL.clone(); cheekR.position.y = -1.6;
  const tail = mesh(new THREE.ConeGeometry(1.3, 4.6, 6), GREEN, -4.6, 0, 3.2); tail.rotation.z = Math.PI / 2; tail.rotation.y = 0.3;
  body.add(torso, belly, head, snout, eyeL, eyeR, pupilL, pupilR, cheekL, cheekR, tail);
  // Back spikes in the avatar's darker green.
  [[-2.4, 6.4], [-0.6, 7.2], [1.4, 9.0], [3.0, 9.6]].forEach(([x, z], i) => {
    const s = mesh(new THREE.ConeGeometry(0.75, 1.6, 4), DARK, x, 0, z); s.rotation.x = Math.PI / 2; s.rotation.y = 0.25 - 0.15 * i; body.add(s);
  });
  const arm = (y) => { const a = mesh(new THREE.CapsuleGeometry(0.4, 1.2, 2, 6), DARK, 2.6, y, 4.6); a.rotation.y = 1.1; return a; };
  body.add(arm(1.6), arm(-1.6));
  const leg = (y) => {
    const pivot = new THREE.Group(); pivot.position.set(0.2, y, 2.6);
    const l = mesh(new THREE.CapsuleGeometry(0.75, 1.6, 2, 6), DARK, 0, 0, -1.3);
    const foot = mesh(new THREE.BoxGeometry(1.8, 1.1, 0.6), DARK, 0.5, 0, -2.6);
    pivot.add(l, foot); return pivot;
  };
  const legL = leg(1.3), legR = leg(-1.3);
  const shadow = new THREE.Mesh(new THREE.CircleGeometry(3.6, 20), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.18 }));
  shadow.position.z = 0.05; shadow.scale.set(1.3, 1, 1);
  g.add(body, legL, legR, shadow);
  return { group: g, body, legL, legR, tail };
}

export async function createGuide(map, { use3d }) {
  if (use3d) {
    try { return await create3d(map); } catch { /* fall through to the sprite */ }
  }
  return createSprite(map);
}

async function create3d(map) {
  const THREE = await import("/assets/vendor/three.module.min.js");
  const coords = map.customCoords;
  let center = map.getCenter().toArray(), renderer = null, camera = null, scene = null, dino = null, unit = 1;
  let pose = null, phase = 0, walking = false;
  const layer = new AMap.GLCustomLayer({
    zIndex: 140,
    init(gl) {
      camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 100, 1 << 30);
      renderer = new THREE.WebGLRenderer({ context: gl });
      renderer.autoClear = false;
      scene = new THREE.Scene();
      scene.add(new THREE.AmbientLight(0xffffff, 1.6));
      const sun = new THREE.DirectionalLight(0xffffff, 1.8); sun.position.set(-600, -900, 1500); scene.add(sun);
      dino = buildDino(THREE); scene.add(dino.group);
    },
    render() {
      if (!renderer || !pose) return;
      renderer.resetState();
      coords.setCenter(center);
      const { near, far, fov, up, lookAt, position } = coords.getCameraParams();
      camera.near = near; camera.far = far; camera.fov = fov;
      camera.position.set(...position); camera.up.set(...up); camera.lookAt(...lookAt);
      camera.updateProjectionMatrix();
      const [p, q] = coords.lngLatsToCoords([[pose.lng, pose.lat], [pose.lng, pose.lat + 0.0001]]);
      unit = Math.abs(q[1] - p[1]) / 11.12 || unit; // custom-coord units per metre here
      const s = (HEIGHT_M / 10) * unit;
      dino.group.position.set(p[0], p[1], 0);
      dino.group.scale.set(s, s, s);
      dino.group.rotation.z = Math.PI / 2 - (pose.bearing * Math.PI) / 180;
      const swing = walking ? Math.sin(phase) * 0.55 : 0;
      dino.legL.rotation.y = swing; dino.legR.rotation.y = -swing;
      dino.body.position.z = walking ? Math.abs(Math.cos(phase)) * 0.45 : 0;
      dino.body.rotation.x = walking ? Math.sin(phase) * 0.05 : 0;
      dino.tail.rotation.x = walking ? Math.sin(phase) * 0.25 : 0;
      renderer.render(scene, camera);
      renderer.resetState();
    },
  });
  map.add(layer);
  return {
    kind: "3d",
    setPose(next, isWalking, dt) {
      pose = next; walking = isWalking; if (walking) phase += dt * 9;
      if (!center || Math.abs(center[0] - next.lng) > 0.01 || Math.abs(center[1] - next.lat) > 0.01) center = [next.lng, next.lat];
      map.render();
    },
    destroy() { map.remove(layer); renderer?.dispose?.(); },
  };
}

function createSprite(map) {
  const img = document.createElement("img");
  img.src = "/assets/v2/dino.svg"; img.alt = ""; img.className = "guide-sprite"; img.width = 46; img.height = 46;
  const marker = new AMap.Marker({ content: img, anchor: "bottom-center", zIndex: 320, position: map.getCenter() });
  map.add(marker);
  return {
    kind: "sprite",
    setPose(next, walking) { marker.setPosition([next.lng, next.lat]); img.classList.toggle("walking", walking); },
    destroy() { map.remove(marker); },
  };
}
