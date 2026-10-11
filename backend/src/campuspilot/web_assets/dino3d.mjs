// 理小龙 guide on the map: an original code-built dinosaur in a
// Three.js AMap.GLCustomLayer, or a 2D sprite marker when 3D is unavailable.
// Loaded lazily by map-frame.js only when walking guidance starts. Three.js r162 is vendored:
// the last release that still renders into AMap's WebGL 1 context (r163 dropped WebGL 1).
// Modelled on the CDUT campus dinosaur statues (理小龙 in a mortarboard).
//
// Proportions measured from the four reference photos (front view a46…, 3/4 side eab…,
// rear 3/4 d42…; pixel spans on 768x1024 downscales, statue height excl. cap = 680-700 px):
//   head (crown → chin)        245 px  ≈ 36% of height;  head width ≈ head height (260 px)
//   head length (back → snout) 250 px  ≈ 1.0 × head height; snout bulb ≈ 1/3 head height
//   neck: visible chin → shoulder ≈ 130 px ≈ 0.55 × head height (≈1.1× with the flare into
//         the chest); narrowest width 140 px ≈ 0.54 × head width, flaring smoothly into the body
//   body: pear/egg, widest low (≈1.0 × head width), top of back at ≈ 50% of height
//   legs: visible ≈ 15% of height, width ≈ 0.35 × head width, set ≈ 0.55 × head width apart
//   tail: short, ≈ 0.8 × head height past the rump, tapering to a blunt round tip
//   eyes: big ovals high on the crown (centre ≈ 20% below the crown), ≈ 0.23 × head width each
//   mortarboard diagonal ≈ head width; tassel hangs on the statue's left to ≈ 80% of head height
// In model units (height 10 excl. cap, feet at z = 0, facing +x, z up) that gives:
//   head z 6.4–10, neck waist r ≈ 1.0 at z ≈ 6.1, body z 1.5–5.0, legs below z ≈ 1.6.
//
// The body, neck, head, tail, legs, toe claws and spots are ONE signed-distance field
// (ellipsoids / tapered capsules joined with smooth-min), polygonised once with surface nets,
// projected onto the surface and shaded with gradient normals — no seams between parts.
// A per-pixel mask in the skin shader paints the crisp cream belly; spots and claws are domes. Animation bends the mesh on the CPU
// (head nod, tail sway, leg swing) with smooth per-vertex weights.
const TEAL = 0x7cc4be, CREAM = 0xfdf0d2, BROWN = 0x7c3a22, NAVY = 0x24324f, CLAW = 0x6b331d;
const BLACK = 0x1d1c20, GOLD = 0xf0b13f, WHITE = 0xf8f7f2, PUPIL = 0x17191f;
const HEIGHT_M = 16; // exaggerated so the guide reads at street zoom

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const smin = (a, b, k) => { const h = Math.max(k - Math.abs(a - b), 0) / k; return Math.min(a, b) - h * h * k * 0.25; };
const smax = (a, b, k) => -smin(-a, -b, k);
function ell(x, y, z, c, r) {
  const X = (x - c[0]) / r[0], Y = (y - c[1]) / r[1], Z = (z - c[2]) / r[2];
  const k0 = Math.hypot(X, Y, Z), k1 = Math.hypot(X / r[0], Y / r[1], Z / r[2]);
  return k1 > 1e-9 ? (k0 * (k0 - 1)) / k1 : -Math.min(...r);
}
function cone(x, y, z, a, b, ra, rb) { // capsule whose radius tapers from ra to rb
  const bx = b[0] - a[0], by = b[1] - a[1], bz = b[2] - a[2];
  const h = clamp(((x - a[0]) * bx + (y - a[1]) * by + (z - a[2]) * bz) / (bx * bx + by * by + bz * bz), 0, 1);
  return Math.hypot(x - a[0] - bx * h, y - a[1] - by * h, z - a[2] - bz * h) - (ra + (rb - ra) * h);
}

const LEGS = [[0.75, 1.38], [0.75, -1.38], [-2.05, 1.3], [-2.05, -1.3]]; // splayed // hip x, y (front L/R, back L/R)
const HIP_Z = 2.0, HEAD_PIVOT = [0.45, 0, 5.6], TAIL_PIVOT = [-2.3, 0, 3.2];

function baseShape(x, y, z) {
  const far = ell(x, y, z, [-0.9, 0, 4.9], [4.7, 3.3, 5.9]);
  if (far > 0.4) return far;
  let d = smin(ell(x, y, z, [-0.45, 0, 2.5], [2.25, 2.6, 1.3]), ell(x, y, z, [-0.75, 0, 3.55], [2.1, 1.7, 1.45]), 0.9); // pear body
  d = smin(d, ell(x, y, z, [0.55, 0, 3.6], [1.25, 1.6, 1.35]), 0.7); // chest
  for (const s of [1, -1]) d = smin(d, ell(x, y, z, [-0.55, s * 1.45, 2.35], [1.9, 1.15, 1.0]), 0.6); // flanks over the legs
  d = smin(d, cone(x, y, z, [0.5, 0, 4.0], [0.35, 0, 6.5], 1.5, 0.98), 0.9); // short neck, waist ≈ 0.5 head width
  d = smin(d, ell(x, y, z, [0.15, 0, 8.05], [1.85, 2.2, 2.0]), 0.6); // round cranium, wider than the body
  d = smin(d, ell(x, y, z, [1.75, 0, 7.95], [1.25, 1.75, 0.95]), 0.6); // wide rounded snout
  d = smin(d, ell(x, y, z, [2.45, 0, 7.72], [0.55, 1.45, 0.42]), 0.35); // fuller upper lip
  d = smin(d, cone(x, y, z, [-2.3, 0, 3.2], [-4.4, 0, 3.55], 1.1, 0.4), 0.8); // tail
  for (const [lx, ly] of LEGS) {
    let leg = cone(x, y, z, [lx, ly, HIP_Z], [lx + 0.05, ly * 1.06, 0.7], 0.74, 0.7);
    leg = smin(leg, ell(x, y, z, [lx + 0.18, ly * 1.07, 0.42], [0.88, 0.8, 0.5]), 0.4); // rounded foot
    d = smin(d, leg, 0.55);
  }
  return smax(d, -z, 0.3); // flat, softly rounded soles
}

function gradient(f, x, y, z, e = 0.02) {
  const gx = f(x + e, y, z) - f(x - e, y, z), gy = f(x, y + e, z) - f(x, y - e, z), gz = f(x, y, z + e) - f(x, y, z - e);
  const l = Math.hypot(gx, gy, gz) || 1;
  return [gx / l, gy / l, gz / l];
}
function surfacePoint(f, from, dir) { // march from inside along dir to the surface
  let [x, y, z] = from; const l = Math.hypot(...dir), [dx, dy, dz] = dir.map((v) => v / l);
  for (let t = 0, i = 0; i < 80; i++) { const d = f(x, y, z); if (d > 0) break; t = Math.max(0.02, -d); x += dx * t; y += dy * t; z += dz * t; }
  for (let i = 0; i < 4; i++) { const d = f(x, y, z), g = gradient(f, x, y, z); x -= g[0] * d; y -= g[1] * d; z -= g[2] * d; }
  return { p: [x, y, z], n: gradient(f, x, y, z) };
}

function buildField() {
  const spots = [], claws = [], dents = [];
  const add = (list, f, from, dir, r, color, sink) => {
    const { p, n } = surfacePoint(f, from, dir);
    list.push({ c: p.map((v, i) => v - n[i] * r * sink), p, n, r, color });
  };
  // Spots along the back and tail (brown domes, a few small navy dots), mirrored.
  for (const s of [1, -1]) {
    for (const [az, el, r, color] of [
      [92, 40, 0.3, BROWN], [112, 58, 0.26, BROWN], [122, 26, 0.33, BROWN], [146, 48, 0.28, BROWN], [152, 14, 0.3, BROWN],
      [100, 8, 0.27, BROWN], [168, 34, 0.26, BROWN], [132, 70, 0.22, BROWN], [104, 66, 0.13, NAVY], [134, 40, 0.13, NAVY],
      [138, 4, 0.12, NAVY], [160, 60, 0.12, NAVY], [112, 30, 0.12, NAVY]]) {
      const a = (az * Math.PI) / 180, e = (el * Math.PI) / 180;
      add(spots, baseShape, [-0.7, 0, 3.2], [Math.cos(a) * Math.cos(e), s * Math.sin(a) * Math.cos(e), Math.sin(e)], r, color, 0.55);
    }
    for (const [x, r, color] of [[-3.0, 0.24, BROWN], [-3.75, 0.18, BROWN], [-3.35, 0.1, NAVY]]) {
      const zc = 3.2 + ((x + 2.3) / -2.1) * 0.35;
      add(spots, baseShape, [x, 0, zc], [0, s * 0.75, 0.65], r, color, 0.55);
    }
  }
  // Three rounded claws on the front of each foot.
  for (const [lx, ly] of LEGS) for (const a of [-0.62, 0, 0.62]) {
    add(claws, baseShape, [lx + 0.18, ly * 1.06, 0.3], [Math.cos(a), Math.sin(a), -0.1], 0.25, CLAW, 0.55);
  }
  // Eye sockets (shallow inset ovals) and the smile crease across the snout.
  const eyes = [1, -1].map((s) => surfacePoint(baseShape, [0.8, s * 0.52, 8.95], [1, s * 0.36, 0.5]));
  for (const e of eyes) dents.push({ c: e.p.map((v, i) => v + e.n[i] * 0.55), r: 0.76 });
  const smile = [];
  for (let i = 0; i <= 12; i++) {
    const y = -1.2 + (2.4 * i) / 12, z = 7.3 + 0.5 * (y / 1.2) ** 2; // deeper smile under the lip
    smile.push(surfacePoint(baseShape, [1.4, y * 0.8, z], [1, y * 0.4, 0.15]).p);
  }
  const nostrils = [1, -1].map((s) => surfacePoint(baseShape, [1.8, s * 0.34, 8.3], [1, s * 0.2, 0.25]).p);
  const field = (x, y, z) => {
    let d = baseShape(x, y, z);
    if (d > 0.6) return d;
    for (const e of dents) d = smax(d, -(Math.hypot(x - e.c[0], y - e.c[1], z - e.c[2]) - e.r), 0.14);
    if (x > 1.5 && z > 7.2 && z < 8.8) {
      for (const n of nostrils) d = smax(d, -(Math.hypot(x - n[0], y - n[1], z - n[2]) - 0.11), 0.08);
    }
    return d;
  };
  return { field, spots, claws, eyes, smile };
}

/** Surface nets: one vertex per sign-changing cell, quads across sign-changing grid edges. */
function surfaceNet(f, lo, hi, h) {
  const nx = Math.ceil((hi[0] - lo[0]) / h) + 1, ny = Math.ceil((hi[1] - lo[1]) / h) + 1, nz = Math.ceil((hi[2] - lo[2]) / h) + 1;
  const v = new Float32Array(nx * ny * nz), at = (i, j, k) => i + nx * (j + ny * k);
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) v[at(i, j, k)] = f(lo[0] + i * h, lo[1] + j * h, lo[2] + k * h);
  const cx = nx - 1, cy = ny - 1, cell = new Int32Array(cx * cy * (nz - 1)).fill(-1), cAt = (i, j, k) => i + cx * (j + cy * k);
  const pos = [], idx = [];
  const corner = new Float32Array(8);
  for (let k = 0; k < nz - 1; k++) for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
    let neg = 0;
    for (let n = 0; n < 8; n++) { corner[n] = v[at(i + (n & 1), j + ((n >> 1) & 1), k + (n >> 2))]; if (corner[n] < 0) neg++; }
    if (neg === 0 || neg === 8) continue;
    let sx = 0, sy = 0, sz = 0, m = 0;
    for (let a = 0; a < 8; a++) for (const bit of [1, 2, 4]) {
      if (a & bit) continue;
      const b = a | bit, va = corner[a], vb = corner[b];
      if ((va < 0) === (vb < 0)) continue;
      const t = va / (va - vb);
      sx += (a & 1) + (bit === 1 ? t : 0); sy += ((a >> 1) & 1) + (bit === 2 ? t : 0); sz += (a >> 2) + (bit === 4 ? t : 0); m++;
    }
    cell[cAt(i, j, k)] = pos.length / 3;
    pos.push(lo[0] + (i + sx / m) * h, lo[1] + (j + sy / m) * h, lo[2] + (k + sz / m) * h);
  }
  const quad = (a, b, c, d, flip) => {
    if (a < 0 || b < 0 || c < 0 || d < 0) return;
    if (flip) idx.push(a, c, b, a, d, c); else idx.push(a, b, c, a, c, d);
  };
  for (let k = 1; k < nz - 1; k++) for (let j = 1; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) {
    const a = v[at(i, j, k)], b = v[at(i + 1, j, k)]; if ((a < 0) === (b < 0)) continue;
    quad(cell[cAt(i, j - 1, k - 1)], cell[cAt(i, j, k - 1)], cell[cAt(i, j, k)], cell[cAt(i, j - 1, k)], !(a < 0));
  }
  for (let k = 1; k < nz - 1; k++) for (let j = 0; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    const a = v[at(i, j, k)], b = v[at(i, j + 1, k)]; if ((a < 0) === (b < 0)) continue;
    quad(cell[cAt(i - 1, j, k - 1)], cell[cAt(i - 1, j, k)], cell[cAt(i, j, k)], cell[cAt(i, j, k - 1)], !(a < 0));
  }
  for (let k = 0; k < nz - 1; k++) for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
    const a = v[at(i, j, k)], b = v[at(i, j, k + 1)]; if ((a < 0) === (b < 0)) continue;
    quad(cell[cAt(i - 1, j - 1, k)], cell[cAt(i, j - 1, k)], cell[cAt(i, j, k)], cell[cAt(i - 1, j, k)], !(a < 0));
  }
  return { pos: new Float32Array(pos), idx };
}

/** Skinning: [bone, weight] — 0 rigid, 1 head, 2 tail, 3.. legs; weights fade smoothly. */
function skinOf(x, y, z) {
  if (z > HEAD_PIVOT[2]) return [1, smooth(HEAD_PIVOT[2], 6.9, z)];
  if (x < TAIL_PIVOT[0] + 0.2 && z > 1.8) return [2, smooth(TAIL_PIVOT[0] + 0.2, -3.6, x)];
  if (z < HIP_Z) {
    let best = 0, bd = Infinity;
    LEGS.forEach(([lx, ly], li) => { const dd = Math.hypot(x - lx, y - ly); if (dd < bd) { bd = dd; best = li; } });
    if (bd < 1.25) return [3 + best, smooth(HIP_Z, 1.15, z) * smooth(1.25, 0.9, bd)];
  }
  return [0, 0];
}

let baked = null; // the field is polygonised once per page
function bake(THREE, step) {
  if (baked && baked.step === step) return baked;
  const { field, spots, claws, eyes, smile } = buildField();
  const { pos, idx } = surfaceNet(field, [-5.0, -2.95, -0.15], [3.3, 2.95, 10.3], step);
  const n = pos.length / 3, nor = new Float32Array(n * 3);
  const bone = new Uint8Array(n), weight = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let x = pos[3 * i], y = pos[3 * i + 1], z = pos[3 * i + 2];
    for (let s = 0; s < 1; s++) { const d = field(x, y, z), g = gradient(field, x, y, z); x -= g[0] * d; y -= g[1] * d; z -= g[2] * d; }
    const g = gradient(field, x, y, z);
    pos.set([x, y, z], 3 * i); nor.set(g, 3 * i);
    [bone[i], weight[i]] = skinOf(x, y, z);
  }
  baked = { step, pos, nor, idx, bone, weight, eyes, spots, claws, smile };
  return baked;
}

/**
 * 理小龙 as the campus statue, facing +x with z up, 10 model units tall plus the cap.
 * One smooth glossy body (≈24k triangles) with inset eyes and a mortarboard.
 * Returns the parts the walk cycle animates; call poseDino to pose it.
 */
export function buildDino(THREE, { step = 0.16 } = {}) {
  const b = bake(THREE, step);
  const geo = new THREE.BufferGeometry();
  const position = new THREE.BufferAttribute(b.pos.slice(), 3), normal = new THREE.BufferAttribute(b.nor.slice(), 3);
  geo.setAttribute("position", position); geo.setAttribute("normal", normal);
  geo.setIndex(b.idx); geo.computeBoundingSphere();
  const skinMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.34, metalness: 0 });
  const tealL = new THREE.Color(TEAL), creamL = new THREE.Color(CREAM); // linear
  skinMat.onBeforeCompile = (sh) => {
    sh.uniforms.uTeal = { value: tealL }; sh.uniforms.uCream = { value: creamL };
    sh.vertexShader = "varying vec3 vOP;\nvarying vec3 vON;\n" + sh.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\nvOP = transformed; vON = objectNormal;");
    // Cream belly: the front of the neck and an oval on the chest, with a crisp per-pixel edge.
    sh.fragmentShader = "uniform vec3 uTeal;\nuniform vec3 uCream;\nvarying vec3 vOP;\nvarying vec3 vON;\nfloat ss(float a, float b, float v) { return a < b ? smoothstep(a, b, v) : 1.0 - smoothstep(b, a, v); }\n" +
      sh.fragmentShader.replace("#include <color_fragment>", `#include <color_fragment>
        vec3 bn = normalize(vON);
        float hw = 0.55 + 0.8 * ss(5.0, 3.3, vOP.z) - 0.75 * ss(2.9, 1.75, vOP.z) * ss(2.9, 1.75, vOP.z);
        float belly = ss(0.22, 0.26, bn.x) * ss(hw, hw - 0.035, abs(vOP.y)) * ss(1.7, 1.74, vOP.z) * ss(7.0, 6.96, vOP.z) * ss(-0.1, -0.06, vOP.x);
        diffuseColor.rgb *= mix(uTeal, uCream, belly);`);
  };
  skinMat.customProgramCacheKey = () => "cdutdino-skin";
  const skin = new THREE.Mesh(geo, skinMat);
  skin.frustumCulled = false;
  const gloss = (color, roughness = 0.3) => new THREE.MeshStandardMaterial({ color, roughness, metalness: 0 });
  const mesh = (geo2, m, x = 0, y = 0, z = 0) => { const o = new THREE.Mesh(geo2, m); o.position.set(x, y, z); return o; };
  const root = new THREE.Group(), body = new THREE.Group(); body.add(skin);

  // Head attachments ride on the neck pivot that also bends the head vertices.
  const neck = new THREE.Group(); neck.position.set(...HEAD_PIVOT); body.add(neck);
  const local = (p) => p.map((v, i) => v - HEAD_PIVOT[i]);
  const eyes = b.eyes.map(({ p, n }, side) => {
    const g = new THREE.Group(); g.position.set(...local(p.map((v, i) => v - n[i] * 0.1)));
    g.up.set(0, 0, 1); g.lookAt(new THREE.Vector3(...local(p)).add(new THREE.Vector3(...n)).add(neck.position).sub(neck.position));
    const sclera = mesh(new THREE.SphereGeometry(1, 24, 16), gloss(WHITE, 0.25)); sclera.scale.set(0.82, 0.44, 0.17); // almond
    const pupil = mesh(new THREE.SphereGeometry(1, 20, 14), gloss(PUPIL, 0.15), side ? 0.13 : -0.13, -0.05, 0.04); pupil.scale.set(0.52, 0.4, 0.16); // white crescent on the outer rim
    const glint = mesh(new THREE.SphereGeometry(0.07, 12, 8), new THREE.MeshBasicMaterial({ color: WHITE }), side ? -0.06 : 0.06, 0.11, 0.2);
    g.add(sclera, pupil, glint); g.rotation.z += side ? -0.32 : 0.32; neck.add(g); return g;
  });
  // Mortarboard: skullcap, square board turned 45°, gold button, cord and tassel.
  const cap = new THREE.Group(); cap.position.set(...local([0.0, 0, 10.05])); cap.rotation.y = -0.12;
  const skull = mesh(new THREE.CylinderGeometry(1.1, 1.18, 0.7, 40, 1), gloss(BLACK, 0.4)); skull.rotation.x = Math.PI / 2;
  const board = mesh(new THREE.BoxGeometry(2.9, 2.9, 0.12), gloss(BLACK, 0.4), 0, 0, 0.4); board.rotation.z = Math.PI / 4;
  const button = mesh(new THREE.SphereGeometry(0.11, 12, 8), gloss(GOLD), 0, 0, 0.48);
  const cord = mesh(new THREE.CylinderGeometry(0.035, 0.035, 2.0, 8), gloss(GOLD), 0, 1.0, 0.48);
  const tassel = new THREE.Group(); tassel.position.set(0, 2.02, 0.44); tassel.rotation.x = 0.32; // hangs clear of the head
  const string = mesh(new THREE.CylinderGeometry(0.045, 0.045, 1.3, 8), gloss(GOLD), 0, 0, -0.65); string.rotation.x = Math.PI / 2;
  const bead = mesh(new THREE.SphereGeometry(0.15, 14, 10), gloss(GOLD), 0, 0, -1.3);
  const fringe = mesh(new THREE.CylinderGeometry(0.1, 0.24, 1.15, 16, 1), gloss(GOLD, 0.55), 0, 0, -1.95); fringe.rotation.x = Math.PI / 2;
  tassel.add(string, bead, fringe);
  cap.add(skull, board, button, cord, tassel); neck.add(cap);

  const tail = new THREE.Object3D(); tail.position.set(...TAIL_PIVOT);
  const legs = LEGS.map(([x, y]) => { const o = new THREE.Object3D(); o.position.set(x, y, HIP_Z); return o; });
  const shadow = mesh(new THREE.CircleGeometry(3, 40), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.16, depthWrite: false }), -0.6, 0, 0.03);
  shadow.scale.set(1.55, 0.9, 1);
  root.add(body, shadow);

  // Crisp domes for the spots and toe claws, a fine crease for the smile; each rides the
  // bone of the skin under it so it follows the CPU deformation.
  const riders = [];
  const up = new THREE.Vector3(0, 1, 0);
  const dome = new THREE.SphereGeometry(1, 12, 4, 0, Math.PI * 2, 0, Math.PI / 2);
  const ride = (obj, at) => {
    const [bi, w] = skinOf(...at), pivot = new THREE.Group();
    const o = [null, HEAD_PIVOT, TAIL_PIVOT, ...LEGS.map(([x, y]) => [x, y, HIP_Z])][bi] || [0, 0, 0];
    pivot.position.set(...o); obj.position.sub(pivot.position); pivot.add(obj); body.add(pivot);
    riders.push({ pivot, bi, w });
  };
  const mats = new Map(), matOf = (hex, r = 0.28) => { if (!mats.has(hex)) mats.set(hex, gloss(hex, r)); return mats.get(hex); };
  for (const s of b.spots) {
    const m = new THREE.Mesh(dome, matOf(s.color)); m.position.set(...s.p.map((v, i) => v - s.n[i] * s.r * 0.12));
    m.quaternion.setFromUnitVectors(up, new THREE.Vector3(...s.n)); m.scale.set(s.r, s.r * 0.42, s.r); ride(m, s.p);
  }
  for (const c of b.claws) {
    const m = new THREE.Mesh(dome, matOf(CLAW, 0.35)); m.position.set(...c.p.map((v, i) => v - c.n[i] * c.r * 0.25));
    m.quaternion.setFromUnitVectors(up, new THREE.Vector3(...c.n)); m.scale.set(c.r * 1.1, c.r * 0.75, c.r * 0.95); ride(m, c.p);
  }
  const crease = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(b.smile.map((p) => new THREE.Vector3(p[0] - 0.02, p[1], p[2]))), 48, 0.055, 6, false),
    new THREE.MeshStandardMaterial({ color: 0x2f6965, roughness: 0.6 }));
  crease.position.set(0, 0, 0); neck.add(crease); crease.position.set(-HEAD_PIVOT[0], -HEAD_PIVOT[1], -HEAD_PIVOT[2]);

  const bones = [null, neck, tail, ...legs];
  let last = "";
  const deform = () => {
    const key = bones.map((o) => (o ? o.rotation.y.toFixed(3) + o.rotation.z.toFixed(3) : "")).join();
    if (key === last) return; last = key;
    const P = position.array, N = normal.array;
    for (let i = 0; i < b.bone.length; i++) {
      const o = bones[b.bone[i]], w = b.weight[i];
      const px = b.pos[3 * i], py = b.pos[3 * i + 1], pz = b.pos[3 * i + 2];
      const nx = b.nor[3 * i], ny = b.nor[3 * i + 1], nz = b.nor[3 * i + 2];
      if (!o || w === 0) { P[3 * i] = px; P[3 * i + 1] = py; P[3 * i + 2] = pz; N[3 * i] = nx; N[3 * i + 1] = ny; N[3 * i + 2] = nz; continue; }
      const ay = o.rotation.y * w, az = o.rotation.z * w, cy = Math.cos(ay), sy = Math.sin(ay), cz = Math.cos(az), sz = Math.sin(az);
      const ox = o.position.x, oy = o.position.y, oz = o.position.z;
      let x = px - ox, y = py - oy, z = pz - oz;
      let x1 = x * cy + z * sy, z1 = -x * sy + z * cy; // about y
      P[3 * i] = x1 * cz - y * sz + ox; P[3 * i + 1] = x1 * sz + y * cz + oy; P[3 * i + 2] = z1 + oz; // then about z
      x1 = nx * cy + nz * sy; z1 = -nx * sy + nz * cy;
      N[3 * i] = x1 * cz - ny * sz; N[3 * i + 1] = x1 * sz + ny * cz; N[3 * i + 2] = z1;
    }
    position.needsUpdate = true; normal.needsUpdate = true;
    for (const r of riders) { const o = bones[r.bi]; if (o) { r.pivot.rotation.y = o.rotation.y * r.w; r.pivot.rotation.z = o.rotation.z * r.w; } }
  };
  return { group: root, body, skin, neck, head: neck, tail, tassel, legs, legL: legs[0], legR: legs[1], eyes, deform };
}

/** Walk / idle pose at phase (radians of the step cycle) and time t (seconds, for blinking). */
export function poseDino(dino, phase, walking, t) {
  const s = walking ? Math.sin(phase) : 0, c = walking ? Math.cos(phase) : 0;
  // Diagonal pairs move together (front-left with back-right).
  const [fl, fr, bl, br] = dino.legs;
  fl.rotation.y = br.rotation.y = s * 0.42; fr.rotation.y = bl.rotation.y = -s * 0.42;
  dino.body.position.z = walking ? Math.abs(c) * 0.14 : Math.sin(t * 2) * 0.03; // bounce / breathe
  dino.body.rotation.x = s * 0.035; // slight waddle
  dino.neck.rotation.y = walking ? -0.03 + c * 0.06 : Math.sin(t * 1.2) * 0.025; // neck/head bob
  dino.tail.rotation.z = Math.sin(phase * 0.5 + 1) * (walking ? 0.28 : 0.08) + Math.sin(t * 1.3) * 0.04;
  dino.tassel.rotation.y = walking ? s * 0.22 : 0;
  const blink = (t % 3.2) < 0.12 ? 0.12 : 1; // blink ~0.12 s every 3.2 s
  for (const e of dino.eyes) e.scale.y = blink;
  dino.deform();
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
      scene.add(new THREE.HemisphereLight(0xfffaf0, 0xb3aa98, 1.7));
      const sun = new THREE.DirectionalLight(0xffffff, 2.2); sun.position.set(-600, -900, 1500); scene.add(sun);
      const rim = new THREE.DirectionalLight(0xe8f4ff, 0.8); rim.position.set(900, 700, 600); scene.add(rim);
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
