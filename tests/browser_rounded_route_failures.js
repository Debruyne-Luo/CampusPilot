// Inject failure only into the isolated AMap Walking client, restore it in finally.
async(page)=>{
  const frame=page.frames().find(f=>f.url().includes('/map-view'));
  await frame.evaluate(()=>{window.originalWalking=AMap.Walking;AMap.Walking=class{search(a,b,done){window.delayedRoute=()=>done('error',{});}};});
  try{
    await page.locator('#place-card .chip.go').click();await page.locator('#route-note').filter({hasText:'正在规划'}).waitFor();
    await page.locator('#map-search').fill('餐厅');await page.locator('#search-results button').first().waitFor();await page.locator('#search-results button').first().click();
    await frame.evaluate(()=>window.delayedRoute?.());await page.waitForTimeout(300);
    if(await page.locator('#route-note').isVisible())throw new Error('cancelled route left waiting or stale error');
    await frame.evaluate(()=>{AMap.Walking=class{search(a,b,done){queueMicrotask(()=>done('error',{}));}};});
    await page.locator('#place-card .chip.go').click();await page.locator('#route-note').filter({hasText:'暂未取得步行路线'}).waitFor();
    if(!(await page.getByRole('button',{name:'换起点',exact:true}).isEnabled()))throw new Error('route failure has no recovery');
    await page.screenshot({path:'output/playwright/rounded-route-error-1440.png'});
    return {cancelledSettles:true,lateErrorIgnored:true,routeFailureActionable:true};
  }finally{await frame.evaluate(()=>{AMap.Walking=window.originalWalking;delete window.originalWalking;delete window.delayedRoute;});}
}
