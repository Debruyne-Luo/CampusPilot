import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from '../backend/src/campuspilot/web_assets/vendor/three.module.min.js';
import {GLTFLoader} from '../backend/src/campuspilot/web_assets/vendor/GLTFLoader.js';

test('authored GLB has bounded geometry, usable surfaces and a real four-leg walk loop',async()=>{
  const bytes=await readFile(new URL('../backend/src/campuspilot/web_assets/models/cdutdino-guide.glb',import.meta.url));
  assert.ok(bytes.length<1_500_000,'lazy model download budget');
  const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length),'');
  let tris=0;
  gltf.scene.traverse(o=>{if(!o.geometry)return;const p=o.geometry.attributes.position;assert.ok(Array.from(p.array).every(Number.isFinite));assert.ok(o.geometry.attributes.normal);tris+=(o.geometry.index?.count||p.count)/3;});
  assert.ok(tris<50000,`triangle budget: ${tris}`);
  const legs=['front_left','front_right','rear_left','rear_right'].map(n=>gltf.scene.getObjectByName(n));
  assert.ok(legs.every(Boolean));
  const mixer=new THREE.AnimationMixer(gltf.scene);
  for(const c of gltf.animations){assert.ok(c.duration>0 && c.duration<2);mixer.clipAction(c).play();}
  const q=legs.map(l=>l.quaternion.clone());mixer.update(.25);
  legs.forEach((l,i)=>assert.ok(l.quaternion.angleTo(q[i])>.1,'every leg walks'));
  assert.ok(legs[0].quaternion.angleTo(legs[3].quaternion)<.01,'diagonal feet stay in phase');
  assert.ok(legs[0].quaternion.angleTo(legs[1].quaternion)>.3,'opposite feet alternate');
  mixer.stopAllAction();mixer.uncacheRoot(gltf.scene);
});
