// Real public Walking geometry; ALL GPS fixes, timestamps and errors are SYNTHETIC.
// No device location is requested. These checks do not replace physical walking/iOS QA.
async (page) => {
  const check=(ok,label)=>{if(!ok) throw new Error(label);};
  const errors=[], onError=error=>errors.push(error.name);
  page.on('pageerror',onError);
  await page.setViewportSize({width:390,height:844});
  await page.goto('http://127.0.0.1:8767/classic');
  await page.waitForFunction(()=>mapState === 'ready');
  await page.locator('#place-query').fill('珙桐');
  await page.getByRole('button',{name:'开始查询',exact:true}).click();
  await page.getByRole('button',{name:'查看路线',exact:true}).click();
  await page.locator('#route-origin').selectOption('cdut:place:east-library');
  await page.getByText('参考路线 · 步行至建筑',{exact:true}).waitFor({timeout:25000});
  const frame=page.frames().find(f=>f.url().endsWith('/map-view'));
  const geometry=await frame.evaluate(()=>map.getAllOverlays('polyline')[0].getPath().map(p=>[p.lng,p.lat]));
  await page.evaluate(()=>{
    window.guidanceFixture={watch:navigator.geolocation.watchPosition,clear:navigator.geolocation.clearWatch,
      now:Date.now,time:Date.now(),watches:[],cleared:0,throwWatch:false};
    Date.now=()=>guidanceFixture.time;
    navigator.geolocation.watchPosition=(ok,fail)=>{
      if (guidanceFixture.throwWatch) throw new DOMException('SYNTHETIC unavailable','SecurityError');
      guidanceFixture.watches.push({ok,fail});return 77; // Deliberately reuse the native watch ID.
    };
    navigator.geolocation.clearWatch=()=>guidanceFixture.cleared++;
  });
  await frame.evaluate(()=>{
    window.guidanceConvert=AMap.convertFrom;window.guidanceConversions=0;
    AMap.convertFrom=(point,_system,callback)=>{
      window.guidanceConversions++;
      callback('complete',{locations:[new AMap.LngLat(...point)]});
    };
  });
  const fix=async(point=geometry[0],accuracy=5,advance=7000,index=-1,age=0)=>{
    await page.evaluate(({point,accuracy,advance,index,age})=>{
      guidanceFixture.time+=advance;
      guidanceFixture.watches.at(index).ok({timestamp:Date.now()-age,coords:{longitude:point[0],latitude:point[1],accuracy}});
    },{point,accuracy,advance,index,age});
  };
  const fail=index=>page.evaluate(index=>guidanceFixture.watches.at(index).fail({code:1}),index);
  const start=()=>page.getByRole('button',{name:'开始步行引导',exact:true}).click();
  const resume=()=>page.getByRole('button',{name:/^(继续引导|重试定位)$/}).click();
  const status=()=>page.locator('.guidance-box [role="status"]').innerText();
  const count=()=>frame.evaluate(()=>window.guidanceConversions);
  try {
    await start();await fix();await page.locator('.guidance-progress').waitFor();
    await frame.waitForFunction(()=>locationLayer && map.lngLatToContainer(locationLayer.getPosition()).getY() < map.getSize().getHeight()-routeBottom);
    const card=await page.locator('#journey-card').boundingBox(), dot=await frame.locator('.guidance-location').boundingBox();
    check(dot.y+dot.height+9 < card.y,'followed fix stays above the expanded card');
    const before=await page.locator('.guidance-progress').innerText();
    await page.getByRole('button',{name:'收起路线卡片',exact:true}).click();
    const compact=await page.locator('#journey-card').boundingBox();
    check(compact.height < card.height*.8,'compact guidance leaves more map space');
    check(await page.getByRole('button',{name:'展开路线卡片',exact:true}).getAttribute('aria-expanded') === 'false','toggle exposes collapsed state');
    check(await page.locator('.guidance-progress').isVisible() && await page.getByRole('button',{name:'暂停引导',exact:true}).isVisible(),'compact guidance keeps progress and pause');
    await page.screenshot({path:'output/playwright/guidance-compact-synthetic.png'});
    await page.getByRole('button',{name:'展开路线卡片',exact:true}).click();
    check(await page.evaluate(()=>guidanceFixture.watches.length) === 1,'card toggle never restarts GPS');
    await page.setViewportSize({width:360,height:640});
    await frame.waitForFunction(()=>map.getSize().getWidth() < 360 && map.getSize().getHeight() < 400);
    await frame.waitForFunction(()=>locationLayer && map.lngLatToContainer(locationLayer.getPosition()).getY() < map.getSize().getHeight()-routeBottom);
    const smallCard=await page.locator('#journey-card').boundingBox(), smallDot=await frame.locator('.guidance-location').boundingBox();
    check(smallDot.y+smallDot.height+9 < smallCard.y,'resize keeps the followed fix above the small-phone card');
    await page.getByRole('button',{name:'收起路线卡片',exact:true}).click();
    await page.screenshot({path:'output/playwright/guidance-compact-small-synthetic.png'});
    await page.getByRole('button',{name:'展开路线卡片',exact:true}).click();
    await page.setViewportSize({width:390,height:844});

    await page.getByRole('button',{name:'暂停引导',exact:true}).click();
    const conversions=await count();await fix(geometry.at(-1),5,7000,0);await fail(0);
    check(await status() === '步行引导已暂停。','late error never overwrites a pause');
    check(await count() === conversions,'paused fixes never reach the provider');
    await resume();
    check(await page.locator('.guidance-progress').innerText() === before,'resume preserves last route progress');
    await fail(0);await fix(geometry.at(-1),5,7000,0);
    check(await status() === '正在获取当前位置…' && await count() === conversions,'old watcher stays invalid after watch ID reuse');
    await fix();await page.getByText('按参考路线步行，留意现场道路与入口。',{exact:true}).waitFor();
    const validCount=await count();
    await fix(geometry[0],-1);await fix(geometry[0],5,7000,-1,16000);await fix(geometry[0],5,7000,-1,-3000);
    check(await count() === validCount,'negative accuracy, stale and future fixes are ignored');
    await fail(-1);await page.getByText('定位权限未允许，可继续查看分步指引。',{exact:true}).waitFor();
    await fix();check(await count() === validCount,'error-state fixes remain inactive');
    await resume();check(await page.locator('.guidance-progress').innerText() === before,'error retry retains progress');
    await fix();await page.getByText('按参考路线步行，留意现场道路与入口。',{exact:true}).waitFor();

    await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
    await fail(-1);
    check(await status() === '页面已离开前台，步行引导已暂停。','late errors cannot undo visibility pause');
    const watches=await page.evaluate(()=>guidanceFixture.watches.length);
    check(watches === 3,'returning to the foreground never restarts GPS automatically');
    await page.evaluate(()=>guidanceFixture.throwWatch=true);await resume();
    await page.getByText('暂未取得有效定位，请重试或查看分步指引。',{exact:true}).waitFor();
    await page.evaluate(()=>guidanceFixture.throwWatch=false);await resume();await fix();
    await page.getByText('按参考路线步行，留意现场道路与入口。',{exact:true}).waitFor();

    // Simulate the existing map-failure callback during an active real reference route.
    await page.evaluate(()=>{mapState='failed';Journey.failed();});
    await page.getByText('地图暂不可用，已保留分步指引。',{exact:true}).waitFor();
    check(!await page.evaluate(()=>Guidance.active()),'map failure stops the GPS watcher');
    check(await page.locator('.route-instructions li').count() > 0 && await page.locator('.route-instructions').getAttribute('open') !== null,'map failure preserves open text directions');
    check(await page.getByRole('button',{name:'开始步行引导',exact:true}).isDisabled(),'guidance cannot start against a failed map');
    await page.evaluate(()=>{mapState='ready';Journey.ready();});
    await page.getByText('参考路线 · 步行至建筑',{exact:true}).waitFor({timeout:25000});
    check(await page.evaluate(()=>guidanceFixture.watches.length) === watches+1,'map recovery replans without restarting GPS');

    await start();await fix();await page.locator('.guidance-progress').waitFor();
    await page.getByRole('button',{name:'收起路线卡片',exact:true}).click();
    const away=[geometry[0][0]+.003,geometry[0][1]+.003];
    await fix(away);await page.getByText('正在确认定位，请留意地图上的当前位置。',{exact:true}).waitFor();
    await fix(away);await page.getByRole('button',{name:'从当前位置重新规划',exact:true}).click();
    await page.getByText('参考路线 · 步行至建筑',{exact:true}).waitFor({timeout:25000});
    check(await page.locator('.route-status').isVisible() && !await page.locator('#journey-card').evaluate(node=>node.classList.contains('route-compact')),'replanning expands the card and exposes the result');
    await start();
    await frame.evaluate(()=>{AMap.convertFrom=(_point,_system,callback)=>window.guidanceDelayed=callback;});
    await fix();await frame.waitForFunction(()=>typeof window.guidanceDelayed === 'function');
    await page.getByRole('button',{name:'退出路线',exact:true}).click();
    await frame.waitForFunction(()=>navigationId === null && !locationLayer && !map.getAllOverlays('polyline').length);
    await frame.evaluate(point=>window.guidanceDelayed('complete',{locations:[new AMap.LngLat(...point)]}),geometry[0]);
    await fix();await fail(-1);
    check(!await page.evaluate(()=>Guidance.active()),'exit ignores delayed conversion, fixes and errors');
    check(await frame.evaluate(()=>navigationId === null && !locationLayer && !map.getAllOverlays('polyline').length),'exit never redraws stale location or route');
    check(!await page.locator('#journey-card').evaluate(node=>node.classList.contains('route-compact')),'new route starts with the full card');
    check(!errors.length,'no page script errors');
    const report={passed:true,scenarios:['card collapse and follow visibility','small-phone resize','no GPS restart on card toggle','pause stale error','preserved progress','reused watcher ID','invalid/stale/future fixes','error retry','visibility pause','synchronous GPS failure','map failure text fallback','map recovery without GPS','compact off-route replan','exit stale cleanup']};
    await page.evaluate(report=>window.guidanceFailureReport=report,report);return report;
  } finally {
    await page.evaluate(()=>{
      Guidance.stop();navigator.geolocation.watchPosition=guidanceFixture.watch;
      navigator.geolocation.clearWatch=guidanceFixture.clear;Date.now=guidanceFixture.now;delete window.guidanceFixture;
    });
    await frame.evaluate(()=>{AMap.convertFrom=window.guidanceConvert;['guidanceConvert','guidanceConversions','guidanceDelayed'].forEach(k=>delete window[k]);});
    page.off('pageerror',onError);
  }
}
