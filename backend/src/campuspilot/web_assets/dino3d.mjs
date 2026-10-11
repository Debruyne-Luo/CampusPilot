// 理小龙 guide on the map: an original low-poly dinosaur built from primitives in a
// Three.js AMap.GLCustomLayer, or a 2D sprite marker when 3D is unavailable.
// Loaded lazily by map-frame.js only when walking guidance starts. Three.js r162 is vendored:
// the last release that still renders into AMap's WebGL 1 context (r163 dropped WebGL 1).
// Palette from v2/dino.svg (the 理小龙 avatar).
const GREEN = 0x3fae6a, DARK = 0x2c8a51, BELLY = 0xa5e2bd, WHITE = 0xffffff, EYE = 0x1d2b22, CHEEK = 0xf6a5a5;
const HEIGHT_M = 16; // exaggerated so the guide reads at street zoom

/**
 * Chibi 理小龙, facing +x with z up, 10 model units tall: a big round head (~40% of the
 * height), a chubby body, stubby legs, small arms, a short rounded tail and small spikes.
 * Smooth toon shading; under 5k triangles. Returns the parts the walk cycle animates.
 */
export function buildDino(THREE) {
  const ramp = new THREE.DataTexture(new Uint8Array([150, 150, 150, 255, 215, 215, 215, 255, 255, 255, 255, 255]), 3, 1);
  ramp.minFilter = ramp.magFilter = THREE.NearestFilter; ramp.needsUpdate = true;
  const mats = new Map();
  const mat = (color) => { if (!mats.has(color)) mats.set(color, new THREE.MeshToonMaterial({ color, gradientMap: ramp })); return mats.get(color); };
  const flat = (color) => new THREE.MeshBasicMaterial({ color });
  const sphere = (r, w = 16, h = 10) => new THREE.SphereGeometry(r, w, h);
  const mesh = (geo, material, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(geo, material); m.position.set(x, y, z); return m; };
  const root = new THREE.Group(), body = new THREE.Group(), head = new THREE.Group();

  // Body: chubby egg with a pale belly patch.
  const torso = mesh(sphere(2.25, 20, 12), mat(GREEN), 0, 0, 2.95); torso.scale.set(1.05, 1, 1.08);
  const belly = mesh(sphere(1.7, 16, 10), mat(BELLY), 1.42, 0, 2.6); belly.scale.set(0.62, 0.95, 0.98);
  // Short rounded tail: two shrinking spheres sweeping back and up.
  const tail = new THREE.Group(); tail.position.set(-1.9, 0, 2.2);
  tail.add(mesh(sphere(1.05, 12, 8), mat(GREEN), -0.45, 0, 0), mesh(sphere(0.62, 10, 8), mat(GREEN), -1.35, 0, 0.35));
  // Small arms.
  const arm = (y) => { const a = mesh(new THREE.CapsuleGeometry(0.3, 0.55, 3, 8), mat(GREEN), 1.55, y, 3.35); a.rotation.set(y > 0 ? -0.5 : 0.5, 0.9, 0); return a; };
  const armL = arm(1.45), armR = arm(-1.45);
  body.add(torso, belly, tail, armL, armR);
  // Small back spikes in the darker green, standing on the surface normal.
  const spikeOn = (parent, cx, cz, radius, theta, r) => {
    const pivot = new THREE.Group(); pivot.position.set(cx, 0, cz); pivot.rotation.y = -theta;
    const spike = mesh(new THREE.ConeGeometry(r, r * 1.7, 10), mat(DARK), 0, 0, radius + r * 0.5); spike.rotation.x = Math.PI / 2;
    pivot.add(spike); parent.add(pivot);
  };
  [[0.75, 0.5], [1.15, 0.44], [1.55, 0.36]].forEach(([theta, r]) => spikeOn(body, 0, 2.95, 2.3, theta, r));
  // Head (~4 units of the 10): round, slightly wide, with a soft muzzle.
  head.position.set(0.55, 0, 7.05);
  const skull = mesh(sphere(2.05, 22, 14), mat(GREEN)); skull.scale.set(1.02, 1.08, 0.97);
  const muzzle = mesh(sphere(1.15, 14, 10), mat(GREEN), 1.45, 0, -0.55); muzzle.scale.set(0.9, 1.15, 0.78);
  head.add(skull, muzzle);
  [[-0.05, 0.5], [0.4, 0.46]].forEach(([theta, r]) => spikeOn(head, 0, 0, 2.05, theta, r));
  // Big eyes with highlights; the eye group scales flat to blink.
  const eye = (y) => {
    const g = new THREE.Group(); g.position.set(1.62, y, 0.35); g.rotation.z = y > 0 ? 0.32 : -0.32;
    const white = mesh(sphere(0.62, 12, 8), flat(WHITE)); white.scale.set(0.55, 1, 1.12);
    const pupil = mesh(sphere(0.42, 10, 6), flat(EYE), 0.2, y > 0 ? -0.05 : 0.05, -0.04); pupil.scale.set(0.5, 1, 1.1);
    const glint = mesh(sphere(0.14, 8, 6), flat(WHITE), 0.42, y > 0 ? -0.18 : -0.08, 0.22);
    const glint2 = mesh(sphere(0.07, 6, 4), flat(WHITE), 0.42, y > 0 ? 0.08 : 0.16, -0.14);
    g.add(white, pupil, glint, glint2); return g;
  };
  const eyeL = eye(0.72), eyeR = eye(-0.72);
  const cheek = (y) => { const c = mesh(sphere(0.34, 10, 6), new THREE.MeshBasicMaterial({ color: CHEEK, transparent: true, opacity: 0.85 }), 1.75, y, -0.4); c.scale.set(0.35, 1, 0.62); return c; };
  // Smile: a half torus on the muzzle.
  const smile = mesh(new THREE.TorusGeometry(0.36, 0.07, 6, 16, Math.PI), flat(EYE), 2.42, 0, -0.62);
  smile.rotation.set(-Math.PI / 2, Math.PI / 2, 0); // onto the front face, arc curving down
  head.add(eyeL, eyeR, cheek(1.3), cheek(-1.3), smile);
  body.add(head);

  // Stubby legs with rounded feet; pivots sit at the hips.
  const leg = (y) => {
    const pivot = new THREE.Group(); pivot.position.set(0.1, y, 1.25);
    const thigh = mesh(new THREE.CapsuleGeometry(0.62, 0.35, 3, 10), mat(GREEN), 0, 0, -0.45);
    const foot = mesh(sphere(0.66, 12, 8), mat(DARK), 0.3, 0, -1.0); foot.scale.set(1.25, 0.95, 0.5);
    pivot.add(thigh, foot); return pivot;
  };
  const legL = leg(0.95), legR = leg(-0.95);
  const shadow = mesh(new THREE.CircleGeometry(2.6, 32), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.16, depthWrite: false }), 0, 0, 0.03);
  shadow.scale.set(1.25, 1, 1);
  root.add(body, legL, legR, shadow);
  return { group: root, body, head, legL, legR, armL, armR, tail, eyes: [eyeL, eyeR] };
}

/** Walk / idle pose at phase (radians of the step cycle) and time t (seconds, for blinking). */
export function poseDino(dino, phase, walking, t) {
  const s = walking ? Math.sin(phase) : 0, c = walking ? Math.cos(phase) : 0;
  dino.legL.rotation.y = s * 0.6; dino.legR.rotation.y = -s * 0.6;
  dino.body.position.z = walking ? Math.abs(c) * 0.32 : Math.sin(t * 2) * 0.06; // bounce / breathe
  dino.body.rotation.x = s * 0.09; // waddle side to side
  dino.head.rotation.x = -s * 0.05;
  dino.tail.rotation.z = Math.sin(phase * 0.5 + 1) * (walking ? 0.35 : 0.12) + Math.sin(t * 1.3) * 0.05;
  dino.armL.rotation.y = 0.9 - s * 0.35; dino.armR.rotation.y = 0.9 + s * 0.35;
  // Blink for ~0.12 s every ~3.2 s.
  const blink = (t % 3.2) < 0.12 ? 0.12 : 1;
  for (const e of dino.eyes) e.scale.z = blink;
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
      scene.add(new THREE.HemisphereLight(0xffffff, 0x9fb8a6, 1.9));
      const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(-600, -900, 1500); scene.add(sun);
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
      poseDino(dino, phase, walking, performance.now() / 1000);
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
