// 理小龙 guide on the map: an original dinosaur built from primitives in a
// Three.js AMap.GLCustomLayer, or a 2D sprite marker when 3D is unavailable.
// Loaded lazily by map-frame.js only when walking guidance starts. Three.js r162 is vendored:
// the last release that still renders into AMap's WebGL 1 context (r163 dropped WebGL 1).
// Modelled on the CDUT campus dinosaur statues: a cartoon sauropod in glossy teal with a
// cream belly stripe, brown and navy spots, brown toe claws and a graduation cap.
const TEAL = 0x6fc2bd, CREAM = 0xf6efd8, BROWN = 0x8c3f22, NAVY = 0x1f3550, BLACK = 0x15181c, GOLD = 0xf2c230;
const WHITE = 0xffffff, PUPIL = 0x1b1d22;
const HEIGHT_M = 16; // exaggerated so the guide reads at street zoom

/**
 * 理小龙 as the campus statue, facing +x with z up, about 10 model units tall (cap included):
 * stout body on four short legs, a long smooth neck rising to a bulbous head with a wide
 * snout and gentle smile, big oval eyes, a short tapered tail. Glossy Phong shading,
 * under 6k triangles. Returns the parts the walk cycle animates.
 */
export function buildDino(THREE) {
  const mats = new Map();
  const gloss = (color, shininess = 70) => {
    const key = color + ":" + shininess;
    if (!mats.has(key)) mats.set(key, new THREE.MeshPhongMaterial({ color, shininess, specular: 0x3a4a4a }));
    return mats.get(key);
  };
  const flat = (color) => new THREE.MeshBasicMaterial({ color });
  const sphere = (r, w = 16, h = 12) => new THREE.SphereGeometry(r, w, h);
  const mesh = (geo, material, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(geo, material); m.position.set(x, y, z); return m; };
  const root = new THREE.Group(), body = new THREE.Group();

  // Body: a stout rounded barrel, cream chest.
  const torso = mesh(sphere(1, 22, 14), gloss(TEAL), -0.35, 0, 2.6); torso.scale.set(1.95, 1.5, 1.6);
  const chest = mesh(sphere(1, 16, 10), gloss(CREAM, 40), 0.85, 0, 2.55); chest.scale.set(0.95, 1.12, 1.35);
  body.add(torso, chest);

  // Short tapered tail sweeping back, slightly raised.
  const tail = new THREE.Group(); tail.position.set(-2.1, 0, 2.55);
  const tailCone = mesh(new THREE.ConeGeometry(0.95, 2.3, 18), gloss(TEAL), -1.0, 0, 0);
  tailCone.rotation.z = Math.PI / 2;
  tail.rotation.y = -0.18; // tip slightly raised
  tail.add(tailCone);
  body.add(tail);

  // Neck: a smooth tube up from the chest, with the cream stripe on its front.
  const neckPivot = new THREE.Group(); neckPivot.position.set(1.1, 0, 3.4);
  const curve = new THREE.CatmullRomCurve3([[-0.5, 0, -1.3], [0.15, 0, 0.5], [0.45, 0, 1.9], [0.6, 0, 3.4], [0.55, 0, 4.3]].map((p) => new THREE.Vector3(...p)));
  const neck = mesh(new THREE.TubeGeometry(curve, 18, 1.02, 16, false), gloss(TEAL));
  const stripeCurve = new THREE.CatmullRomCurve3(curve.points.slice(0, 4).map((p, i) => p.clone().add(new THREE.Vector3(0.5, 0, i === 0 ? 0.5 : 0))));
  const stripe = mesh(new THREE.TubeGeometry(stripeCurve, 12, 0.62, 10, false), gloss(CREAM, 40));
  neckPivot.add(neck, stripe);
  body.add(neckPivot);

  // Head: bulbous cranium and a wide, long snout; the head group bobs on the neck.
  const head = new THREE.Group(); head.position.set(0.7, 0, 4.1); neckPivot.add(head);
  const cranium = mesh(sphere(1, 20, 16), gloss(TEAL), -0.15, 0, 0.45); cranium.scale.set(1.6, 1.5, 1.45);
  const snout = mesh(sphere(1, 18, 12), gloss(TEAL), 1.35, 0, -0.1); snout.scale.set(1.35, 1.3, 0.95);
  // Gentle smile across the front of the snout (a lower half-ring), plus two nostrils.
  const smile = mesh(new THREE.TorusGeometry(0.7, 0.055, 4, 16, Math.PI), flat(0x2b5c58), 2.5, 0, -0.08);
  smile.rotation.set(-Math.PI / 2, Math.PI / 2, 0);
  const nostril = (y) => mesh(sphere(0.08, 8, 6), flat(0x3f8f8a), 2.66, y, 0.35);
  head.add(cranium, snout, smile, nostril(0.32), nostril(-0.32));
  // Big oval eyes high on the cranium: white with a dark pupil and a highlight; scale to blink.
  const eye = (y) => {
    const g = new THREE.Group(); g.position.set(0.55, y, 1.15); g.rotation.z = y > 0 ? 0.6 : -0.6;
    const rim = mesh(sphere(0.62, 12, 8), flat(WHITE)); rim.scale.set(0.42, 0.85, 1.05);
    const pupil = mesh(sphere(0.5, 10, 8), flat(PUPIL), 0.12, 0.04, -0.06); pupil.scale.set(0.4, 0.68, 0.9);
    const glint = mesh(sphere(0.1, 8, 6), flat(WHITE), 0.3, -0.05, 0.2);
    g.add(rim, pupil, glint); return g;
  };
  const eyeL = eye(0.98), eyeR = eye(-0.98);
  head.add(eyeL, eyeR);
  // Graduation cap: black skullcap, square board, gold tassel.
  const cap = new THREE.Group(); cap.position.set(-0.3, 0, 1.85); cap.rotation.y = -0.15;
  const skull = mesh(new THREE.CylinderGeometry(1.1, 1.18, 0.7, 24), gloss(BLACK, 90)); skull.rotation.x = Math.PI / 2;
  const board = mesh(new THREE.BoxGeometry(3.1, 3.1, 0.14), gloss(BLACK, 90), 0, 0, 0.42); board.rotation.z = Math.PI / 4;
  const button = mesh(sphere(0.12, 8, 6), gloss(GOLD), 0, 0, 0.45);
  const cord = mesh(new THREE.CylinderGeometry(0.04, 0.04, 1.85, 6), gloss(GOLD), 0, 0.92, 0.42);
  const tassel = new THREE.Group(); tassel.position.set(0, 1.85, 0.4);
  const string = mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.9, 6), gloss(GOLD), 0, 0, -0.45); string.rotation.x = Math.PI / 2;
  const fringe = mesh(new THREE.ConeGeometry(0.2, 0.8, 10), gloss(GOLD), 0, 0, -1.2); fringe.rotation.x = Math.PI / 2;
  tassel.add(string, mesh(sphere(0.12, 8, 6), gloss(GOLD), 0, 0, -0.85), fringe);
  cap.add(skull, board, button, cord, tassel);
  head.add(cap);

  // Spots along the back and tail: brown buttons and a few small navy dots, on the surface.
  const spot = (parent, cx, cy, cz, rx, ry, rz, u, v, r, color) => {
    const n = new THREE.Vector3(Math.cos(v) * Math.cos(u), Math.cos(v) * Math.sin(u), Math.sin(v));
    const m = mesh(new THREE.CircleGeometry(r, 16), gloss(color, 90), cx + n.x * (rx + 0.02), cy + n.y * (ry + 0.02), cz + n.z * (rz + 0.02)); m.lookAt(m.position.clone().add(n)); parent.add(m);
  };
  const T = { cx: -0.35, cy: 0, cz: 2.6, rx: 1.95, ry: 1.5, rz: 1.6 };
  for (const side of [1, -1]) {
    [[2.3, 0.85, 0.24], [2.75, 0.5, 0.26], [2.05, 0.35, 0.2], [3.0, 0.15, 0.22], [1.75, 0.75, 0.18]]
      .forEach(([u, v, r]) => spot(body, T.cx, T.cy, T.cz, T.rx, T.ry, T.rz, side * u, v, r, BROWN));
    [[2.5, 0.7], [2.95, 0.85], [2.4, 0.15]].forEach(([u, v]) => spot(body, T.cx, T.cy, T.cz, T.rx, T.ry, T.rz, side * u, v, 0.11, NAVY));
    [[-0.55, 0.62, 0.17], [-1.25, 0.42, 0.13]].forEach(([x, r, rad]) => {
      const m = mesh(new THREE.CircleGeometry(rad, 16), gloss(BROWN, 90), x, side * r, 0.25);
      m.rotation.x = -side * Math.PI / 2; tail.add(m);
    });
  }

  // Four short sturdy legs; the hip pivots swing, feet carry brown toe claws.
  const leg = (x, y) => {
    const pivot = new THREE.Group(); pivot.position.set(x, y, 1.75);
    pivot.add(mesh(new THREE.CapsuleGeometry(0.66, 0.85, 3, 10), gloss(TEAL), 0, 0, -0.85).rotateX(Math.PI / 2));
    for (const dy of [-0.3, 0, 0.3]) {
      const claw = mesh(sphere(0.19, 7, 4), gloss(BROWN, 90), 0.55, dy, -1.62); claw.scale.set(1.2, 1, 0.8); pivot.add(claw);
    }
    return pivot;
  };
  const legs = [leg(0.95, 0.9), leg(0.95, -0.9), leg(-1.45, 0.9), leg(-1.45, -0.9)];
  const shadow = mesh(new THREE.CircleGeometry(2.8, 32), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.16, depthWrite: false }), 0, 0, 0.03);
  shadow.scale.set(1.45, 0.85, 1);
  root.add(body, ...legs, shadow);
  return { group: root, body, neck: neckPivot, head, tail, tassel, legs, legL: legs[0], legR: legs[1], eyes: [eyeL, eyeR] };
}

/** Walk / idle pose at phase (radians of the step cycle) and time t (seconds, for blinking). */
export function poseDino(dino, phase, walking, t) {
  const s = walking ? Math.sin(phase) : 0, c = walking ? Math.cos(phase) : 0;
  // Diagonal pairs move together (front-left with back-right).
  const [fl, fr, bl, br] = dino.legs;
  fl.rotation.y = br.rotation.y = s * 0.5; fr.rotation.y = bl.rotation.y = -s * 0.5;
  dino.body.position.z = walking ? Math.abs(c) * 0.22 : Math.sin(t * 2) * 0.04; // bounce / breathe
  dino.body.rotation.x = s * 0.04;
  dino.neck.rotation.y = walking ? -0.04 + c * 0.05 : Math.sin(t * 1.2) * 0.02; // neck bob
  dino.head.rotation.y = walking ? -c * 0.06 : 0;
  dino.tail.rotation.z = Math.sin(phase * 0.5 + 1) * (walking ? 0.3 : 0.1) + Math.sin(t * 1.3) * 0.04;
  dino.tassel.rotation.y = walking ? s * 0.25 : 0;
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
