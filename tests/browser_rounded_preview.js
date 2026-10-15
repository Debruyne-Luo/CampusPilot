// Open the local candidate against real services in this isolated browser only.
// Does not send a question, store transcripts, or modify the deployed site.
async(page)=>{
  const origin='https://cdutdino.pages.dev',local='http://127.0.0.1:8875';
  await page.unrouteAll({behavior:'wait'});
  await page.route(`${origin}/assets/**`,async route=>{
    const path=new URL(route.request().url()).pathname.replace(/^\/assets\/v-[^/]+\//,'/assets/');
    await route.fulfill({response:await page.request.get(local+path)});
  });
  await page.route(`${origin}/?*`,async route=>route.fulfill({response:await page.request.get(local+'/')}));
  // The user preview follows its window. Fixed viewports belong only in QA scripts.
  const cdp=await page.context().newCDPSession(page);
  await cdp.send('Emulation.clearDeviceMetricsOverride');
  await page.goto(origin+'/?desktop-review=1');
  await page.locator('#send:not([disabled])').waitFor();
  await page.frameLocator('#map-frame').locator('body[data-markers]').waitFor({timeout:25000});
  await page.evaluate(()=>{document.title='本地交互预览（未发布）· 理小龙';});
  await page.bringToFront();
  return {ready:true,localCandidate:true,realMap:true,questionSent:false};
}
