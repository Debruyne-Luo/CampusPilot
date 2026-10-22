export async function createGuide(map, { use3d }) {
  if (use3d) {
    try { return await create3d(map); } catch { /* fall through to the sprite */ }
  }
  return createSprite(map);
}

async function create3d(map) {
  const THREE = await import("/assets/vendor/three.module.min.js");
  const {GLTFLoader}=await import('/assets/vendor/GLTFLoader.js');
  // 学士帽小恐龙（revision-03 assembly/scene.glb）。旧的 cdutdino-guide.glb
  // 保留为加载失败时的后备，详见 DESIGN.md。
  let gltf = null, modelYaw = 0;
  const models = [
    {url: '/assets/models/graduate-dino.glb', yaw: Math.PI / 2},
    {url: '/assets/models/cdutdino-guide.glb', yaw: 0},
  ];
  for (const {url, yaw} of models) {
    try {
      const response = await fetch(url, {signal: AbortSignal.timeout(url.includes('graduate') ? 60000 : 15000)});
      if (response.ok) { gltf = await new GLTFLoader().parseAsync(await response.arrayBuffer(), ''); modelYaw = yaw; break; }
    } catch { /* try the next url (timeout or network) */ }
  }
  if (!gltf) throw new Error('Guide model unavailable');
  // glTF is Y-up; AMap custom coordinates are Z-up. 新模型前方 +Z，
  // 先绕 Y 转 +90° 对齐 +X；旧模型本就朝 +X，保持其原始偏航。
  // 再整体 X 翻 +90° 立起，两个模型均沿地图坐标 +X 前进。
  gltf.scene.rotateY(modelYaw);
  const model = new THREE.Group(); model.rotation.x = Math.PI / 2; model.add(gltf.scene);
  // 模型局部最低点落到地面 z=0，避免半个身子埋进地图。
  const lifted = new THREE.Group(); lifted.add(model);
  const anchor = new THREE.Group(); anchor.add(lifted);
  const box = new THREE.Box3().setFromObject(anchor);
  const sizeMeasured = box.getSize(new THREE.Vector3());
  lifted.position.z = -box.min.z;
  const height = sizeMeasured.z;
  // 有动画的模型逐步播放步态；静态模型（新恐龙）用整组轻微起伏近似行走反馈。
  const mixer = gltf.animations.length ? new THREE.AnimationMixer(gltf.scene) : null;
  if (mixer) for (const clip of gltf.animations) mixer.clipAction(clip).play();
  const liftBase = lifted.position.z, bobAmp = mixer ? 0 : height * 0.03; // static dino: ±3% height bob
  let bobPhase = 0;
  const coords = map.customCoords;
  let center = map.getCenter().toArray(), renderer = null, camera = null, scene = null, dino = null, unit = 1;
  let pose = null, destroyed = false;
  const layer = new AMap.GLCustomLayer({
    zIndex: 140,
    init(gl) {
      camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 100, 1 << 30);
      renderer = new THREE.WebGLRenderer({ canvas:gl.canvas, context: gl });
      renderer.autoClear = false;
      scene = new THREE.Scene();
      scene.add(new THREE.HemisphereLight(0xfffaf0, 0xb3aa98, 1.7));
      const sun = new THREE.DirectionalLight(0xffffff, 2.2); sun.position.set(-600, -900, 1500); scene.add(sun);
      const rim = new THREE.DirectionalLight(0xe8f4ff, 0.8); rim.position.set(900, 700, 600); scene.add(rim);
      dino = {group:anchor}; scene.add(anchor);
    },
    render() {
      if (destroyed || !renderer || !pose) return;
      renderer.resetState();
      coords.setCenter(center);
      const { near, far, fov, up, lookAt, position } = coords.getCameraParams();
      camera.near = near; camera.far = far; camera.fov = fov;
      const size=map.getSize();camera.aspect=size.width/size.height;
      camera.position.set(...position); camera.up.set(...up); camera.lookAt(...lookAt);
      camera.updateProjectionMatrix();
      const [p, q] = coords.lngLatsToCoords([[pose.lng, pose.lat], [pose.lng, pose.lat + 0.0001]]);
      unit = Math.abs(q[1] - p[1]) / 11.12 || unit; // custom-coord units per metre here
      const s = (14 / height) * unit;
      dino.group.position.set(p[0], p[1], 0);
      dino.group.scale.set(s, s, s);
      dino.group.rotation.z = Math.PI / 2 - (pose.bearing * Math.PI) / 180;
      renderer.render(scene, camera);
      renderer.resetState();
    },
  });
  map.add(layer);
  return {
    kind: "3d",
    setPose(next, isWalking, dt) {
      if (destroyed) return;
      pose = next;
      if (mixer) { if (isWalking) mixer.update(dt); }
      else if (bobAmp) { // static dino: gentle vertical bob + sway only while walking
        if (isWalking) { bobPhase += dt * 6; lifted.position.z = liftBase + Math.abs(Math.sin(bobPhase)) * bobAmp; model.rotation.z = Math.sin(bobPhase) * 0.02; }
        else { lifted.position.z = liftBase; model.rotation.z = 0; }
      }
      if (!center || Math.abs(center[0] - next.lng) > 0.01 || Math.abs(center[1] - next.lat) > 0.01) center = [next.lng, next.lat];
      map.render();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      map.remove(layer); if (mixer) { mixer.stopAllAction(); mixer.uncacheRoot(gltf.scene); }
      const geometries = new Set(), materials = new Set(), textures = new Set();
      gltf.scene.traverse(o => {
        if (o.geometry) geometries.add(o.geometry);
        for (const material of o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : []) {
          materials.add(material);
          for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
        }
      });
      const images = new Set();
      for (const texture of textures) {
        images.add(texture.image);
        texture.dispose();
      }
      // Texture.dispose releases GPU memory; ImageBitmap pixel buffers need close().
      for (const image of images) image?.close?.();
      for (const material of materials) material.dispose();
      for (const geometry of geometries) geometry.dispose();
      // The GL context belongs to AMap: never forceContextLoss or resize its canvas.
      renderer?.dispose?.();
    },
  };
}

function createSprite(map) {
  const img = document.createElement("img");
  img.src = "/assets/v2/brand-icon.png"; img.alt = "理小龙引导（二维兼容模式）"; img.className = "guide-sprite"; img.width = 46; img.height = 46;
  const marker = new AMap.Marker({ content: img, anchor: "bottom-center", zIndex: 320, position: map.getCenter() });
  map.add(marker);
  return {
    kind: "sprite",
    setPose(next, walking) { marker.setPosition([next.lng, next.lat]); img.classList.toggle("walking", walking); },
    destroy() { map.remove(marker); },
  };
}
