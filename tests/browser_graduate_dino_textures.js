// Run after browser_rounded_preview.js; the real frame CSP must remain enabled.
async page => {
  const errors = [];
  const onConsole = message => { if (message.type() === 'error') errors.push(message.text()); };
  page.on('console', onConsole);
  try {
    const frame = page.frames().find(candidate => new URL(candidate.url()).pathname === '/map-view');
    if (!frame) throw new Error('Map frame is not ready');
    const report = await frame.evaluate(async () => {
      const {GLTFLoader} = await import('/assets/vendor/GLTFLoader.js');
      const response = await fetch('/assets/models/graduate-dino.glb');
      if (!response.ok) throw new Error('Graduate model download failed');
      const gltf = await new GLTFLoader().parseAsync(await response.arrayBuffer(), '');
      const geometries = new Set(), materials = new Set(), textures = new Set();
      gltf.scene.traverse(object => {
        if (object.geometry) geometries.add(object.geometry);
        for (const material of object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : []) {
          materials.add(material);
          for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
        }
      });
      const images = [...textures].map(texture => ({width: texture.image?.width || 0, height: texture.image?.height || 0}));
      const imageSources = new Set([...textures].map(texture => texture.image));
      for (const texture of textures) texture.dispose();
      for (const material of materials) material.dispose();
      for (const geometry of geometries) geometry.dispose();
      for (const source of imageSources) source?.close?.();
      return {meshes: geometries.size, textures: textures.size, images};
    });
    if (report.textures < 4 || report.images.some(image => image.width < 1 || image.height < 1)) {
      throw new Error('Embedded model textures did not decode: ' + JSON.stringify(report));
    }
    if (errors.length) throw new Error('Model texture console errors: ' + errors.join('; '));
    return {...report, consoleErrors: errors.length};
  } finally {
    page.off('console', onConsole);
  }
}
