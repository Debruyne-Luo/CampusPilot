export async function createGuide(map, { use3d }) {
  if (use3d) {
    try { return await create3d(map); } catch { /* fall through to the sprite */ }
  }
  return createSprite(map);
}

async function create3d(map) {
  const THREE = await import("/assets/vendor/three.module.min.js");
  const {GLTFLoader}=await import('/assets/vendor/GLTFLoader.js');
  const response=await fetch('/assets/models/cdutdino-guide.glb',{signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw new Error('Guide model unavailable');
  const gltf=await new GLTFLoader().parseAsync(await response.arrayBuffer(),'');
  // glTF is Y-up; AMap custom coordinates are Z-up. Authored forward axis is +X.
  const model=new THREE.Group();model.rotation.x=Math.PI/2;model.add(gltf.scene);
  const anchor=new THREE.Group();anchor.add(model);
  const height=new THREE.Box3().setFromObject(anchor).getSize(new THREE.Vector3()).z;
  const mixer=new THREE.AnimationMixer(gltf.scene);
  for(const clip of gltf.animations)mixer.clipAction(clip).play();
  const coords = map.customCoords;
  let center = map.getCenter().toArray(), renderer = null, camera = null, scene = null, dino = null, unit = 1;
  let pose = null;
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
      if (!renderer || !pose) return;
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
      pose = next; if (isWalking) mixer.update(dt);
      if (!center || Math.abs(center[0] - next.lng) > 0.01 || Math.abs(center[1] - next.lat) > 0.01) center = [next.lng, next.lat];
      map.render();
    },
    destroy() {
      map.remove(layer);mixer.stopAllAction();mixer.uncacheRoot(gltf.scene);
      gltf.scene.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material])m.dispose();}});
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
