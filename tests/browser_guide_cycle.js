// Public campus route only; no conversation or personal location is used.
async page=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.reload();await page.locator('#send:not([disabled])').waitFor();
  await page.frameLocator('#map-frame').locator('body[data-markers]').waitFor({timeout:25000});
  await page.evaluate(()=>{window.gpsCalls=0; navigator.geolocation.getCurrentPosition=()=>{window.gpsCalls++;};navigator.geolocation.watchPosition=()=>{window.gpsCalls++;return 99;};});
  await page.locator('#map-search').fill('图书馆');await page.locator('#search-results button').first().click();
  await page.locator('#place-card .chip.go').click();
  await page.locator('.origin-select').selectOption('cdut:place:gongtong-dining');
  await page.getByRole('button',{name:'开始路线演示',exact:true}).waitFor({timeout:25000});
  const frame=page.frames().find(f=>f.url().includes('/map-view'));
  await page.getByRole('button',{name:'开始路线演示',exact:true}).click();
  await frame.locator('body[data-guide]').waitFor({timeout:25000});
  await page.waitForTimeout(1300);
  const kind=await frame.locator('body').getAttribute('data-guide');
  await page.getByRole('button',{name:'暂停演示',exact:true}).click();
  await frame.waitForFunction(()=>dinoState?.paused===true);
  const d=await frame.evaluate(()=>dinoState.d);await page.waitForTimeout(650);
  if(await frame.evaluate(()=>dinoState.d)!==d)throw new Error('pause did not stop demo');
  await page.getByRole('button',{name:'继续演示',exact:true}).click();await page.waitForTimeout(650);
  if(await frame.evaluate(()=>dinoState.d)<=d)throw new Error('resume did not advance');
  await page.screenshot({path:'output/playwright/dino/map-demo-1440.png'});
  for(let i=0;i<3;i++){
    await page.getByRole('button',{name:'结束演示',exact:true}).click();
    await page.getByRole('button',{name:'开始路线演示',exact:true}).waitFor();await page.waitForTimeout(200);
    const clean=await frame.evaluate(()=>({guide:!!guide,raf:dinoRaf,drag:map.getStatus().dragEnable,pitch:map.getPitch()}));
    if(clean.guide || clean.raf || !clean.drag || clean.pitch)throw new Error('exit did not restore map: '+JSON.stringify(clean));
    await page.getByRole('button',{name:'开始路线演示',exact:true}).click();await frame.locator('body[data-guide]').waitFor();
  }
  await page.getByRole('button',{name:'结束演示',exact:true}).click();
  const gps=await page.evaluate(()=>window.gpsCalls);
  if(gps || errors.length)throw new Error(JSON.stringify({gps,errors}));
  return {kind,cycles:3,pauseResume:true,desktopGPSRequests:gps,pageErrors:errors.length};
}
