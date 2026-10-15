// Run after browser_guide_cycle.js, which leaves a real public route ready.
async page=>{
  const frame=page.frames().find(f=>f.url().includes('/map-view'));
  const start=()=>page.getByRole('button',{name:/^开始(路线演示|步行引导)$/}).click();
  const stop=()=>page.getByRole('button',{name:/^结束(演示|引导)$/}).click();
  const ready=()=>page.getByRole('button',{name:/^开始(路线演示|步行引导)$/}).waitFor();
  // Loading can finish after a rapid stop. No late layer may take over the map.
  await page.route('**/models/cdutdino-guide.glb',async r=>{await new Promise(ok=>setTimeout(ok,900));await r.fallback();});
  await start();await stop();await ready();await page.waitForTimeout(1500);
  if(await frame.evaluate(()=>!!guide || !!dinoState || !map.getStatus().dragEnable))throw new Error('late guide survived stop');
  await page.unroute('**/models/cdutdino-guide.glb');
  // A failed GLB is explicit 2D fallback and still exits cleanly.
  await page.route('**/models/cdutdino-guide.glb',r=>r.fulfill({status:503,body:'SYNTHETIC model unavailable'}));
  await start();await frame.waitForFunction(()=>guide?.kind==='sprite');await stop();await ready();
  await page.unroute('**/models/cdutdino-guide.glb');
  await page.emulateMedia({reducedMotion:'reduce'});await start();
  await frame.waitForFunction(()=>guide?.kind==='sprite');
  const bearing=await frame.evaluate(()=>map.getRotation());await page.waitForTimeout(1100);
  if(await frame.evaluate(()=>map.getRotation())!==bearing)throw new Error('reduced motion camera moved');
  await stop();await ready();await page.emulateMedia({reducedMotion:'no-preference'});
  const widths=[];
  for(const width of [1280,1920,390]){
    await page.setViewportSize({width,height:900});await page.waitForTimeout(450);
    if(width<760) {await page.locator('#sheet-handle').click();await page.waitForTimeout(350);}
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('horizontal overflow '+width);
    await start();await frame.waitForFunction(()=>guide?.kind==='3d');await page.waitForTimeout(1100);
    await page.screenshot({path:`output/playwright/dino/map-demo-${width}.png`});
    await stop();await ready();await frame.waitForFunction(()=>!guide && !dinoRaf && map.getStatus().dragEnable);
    widths.push(width);
  }
  await page.setViewportSize({width:1440,height:900});await start();await frame.waitForFunction(()=>!!guide);
  await page.getByRole('button',{name:'退出路线',exact:true}).click();
  await frame.waitForFunction(()=>!guide && !routeGeometry.length && map.getStatus().dragEnable);
  if(await page.locator('#route-note').isVisible())throw new Error('route exit kept stale controls');
  return {cancelDuringLoad:true,modelFailureFallback:true,reducedMotion:true,widths,exitRoute:true};
}
