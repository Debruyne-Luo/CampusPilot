// Actual touch events and provider lookups in Chromium mobile emulation, not a physical phone.
async(page)=>{
  const context=await page.context().browser().newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,
    userAgent:'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36'});
  try {
    const mobile=await context.newPage();await mobile.goto('http://127.0.0.1:8767/');
    await mobile.waitForFunction(()=>mapState==='ready');
    const frame=mobile.frames().find(f=>f.url().endsWith('/map-view'));
    await frame.waitForFunction(()=>placeRecords.size===20);
    const id=await frame.evaluate(async()=>{
      const service=await placeSearch();
      const poi=await new Promise((resolve,reject)=>service.searchNearBy('攻坚楼',CAMPUS_CENTER,2000,(status,result)=>status==='complete' ? resolve(result.poiList.pois[0]) : reject(new Error('Real provider POI unavailable'))));
      window.nativeHotspots=[];map.on('hotspotclick',event=>window.nativeHotspots.push({id:event.id,name:event.name}));
      map.setZoomAndCenter(18,poi.location);return poi.id;
    });
    await mobile.waitForTimeout(1200);
    const box=await frame.locator('#map-view').boundingBox();
    await frame.locator('#map-view').tap({position:{x:box.width/2,y:box.height/2}});
    await mobile.locator('#journey-card').getByRole('heading',{name:/攻坚楼/}).waitFor({timeout:15000});
    if (!await frame.evaluate(id=>window.nativeHotspots.some(e=>e.id===id),id)) throw new Error('Native touch hotspot missing');
    await mobile.screenshot({path:'output/playwright/touch-hotspot-after.png'});
    await mobile.locator('.mobile-modes [data-workspace="assistant"]').tap();
    await mobile.locator('#question').tap();
    if (!await mobile.evaluate(()=>visualViewport.scale===1)) throw new Error('Composer caused page zoom');
    await mobile.screenshot({path:'output/playwright/assistant-mobile-welcome.png'});
    await page.evaluate(()=>{window.touchReport={passed:true,mobile_emulation:true,native_hotspot:true,input_scale:1};});
  } finally {await context.close();}
}
