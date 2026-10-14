# Three.js GLTF loader

GLTFLoader.js and BufferGeometryUtils.js are from Three.js r162, matching the existing vendored runtime. MIT license: [THREE-LICENSE.md](THREE-LICENSE.md).

- https://github.com/mrdoob/three.js/blob/r162/examples/jsm/loaders/GLTFLoader.js
- https://github.com/mrdoob/three.js/blob/r162/examples/jsm/utils/BufferGeometryUtils.js

Only imports were changed to local relative paths. No external CDN runs in the browser. No compressed mesh or texture decoder dependencies are used.
