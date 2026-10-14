// Sanitised Chromium performance trace: no network/body/URL/screenshot arguments.
async(page)=>{
  await page.bringToFront();
  const cdp=await page.context().newCDPSession(page),events=[];
  const allowed=new Set(['RunTask','FunctionCall','UpdateLayoutTree','Layout','Paint','CompositeLayers','DrawFrame','BeginFrame','FireAnimationFrame','EventDispatch','AnimationFrame','AnimationFrame::Render']);
  cdp.on('Tracing.dataCollected',({value})=>{for(const e of value)if(allowed.has(e.name))events.push({name:e.name,cat:e.cat,ph:e.ph,ts:e.ts,dur:e.dur,pid:e.pid,tid:e.tid});});
  await cdp.send('Tracing.start',{categories:'devtools.timeline,disabled-by-default-devtools.timeline,benchmark',options:'record-as-much-as-possible'});
  await page.evaluate(()=>{window.frameSamples=[];window.longTasks=[];window.perfRunning=true;let previous;window.perfObserver=new PerformanceObserver(list=>window.longTasks.push(...list.getEntries().map(e=>e.duration)));window.perfObserver.observe({type:'longtask'});function tick(t){if(previous)window.frameSamples.push(t-previous);previous=t;if(window.perfRunning)requestAnimationFrame(tick);}requestAnimationFrame(tick);});
  for(let i=0;i<5;i++){
    if(await page.locator('#return-reading').isVisible())await page.locator('#return-reading').click();
    else await page.locator('#desktop-map').click();
    await page.waitForTimeout(500);
  }
  await page.locator('#route-overview').click();await page.waitForTimeout(550);
  const box=await page.locator('#map-frame').boundingBox();await page.mouse.move(box.x+box.width*.6,box.y+box.height*.45);await page.mouse.down();await page.mouse.move(box.x+box.width*.5,box.y+box.height*.55,{steps:15});await page.mouse.up();await page.waitForTimeout(700);
  const metrics=await page.evaluate(()=>{window.perfRunning=false;window.perfObserver.disconnect();const x=window.frameSamples.sort((a,b)=>a-b);return {samples:x.length,p50:x[Math.floor(x.length*.5)],p95:x[Math.floor(x.length*.95)],max:x.at(-1),over33:x.filter(x=>x>33.4).length,longTasks:window.longTasks.length,maxLongTask:Math.max(0,...window.longTasks),viewport:[innerWidth,innerHeight],dpr:devicePixelRatio,cores:navigator.hardwareConcurrency};});
  const complete=new Promise(resolve=>cdp.once('Tracing.tracingComplete',resolve));await cdp.send('Tracing.end');await complete;await cdp.detach();
  const tasks=events.filter(e=>e.name==='RunTask'&&e.dur),layouts=events.filter(e=>e.name==='Layout'&&e.dur);
  const summary={...metrics,browser:await page.context().browser().version(),traceEvents:events.length,traceTaskMaxMs:Math.max(0,...tasks.map(e=>e.dur/1000)),traceLayoutMaxMs:Math.max(0,...layouts.map(e=>e.dur/1000))};
  // Browser download API writes the sanitised trace, without Node FS or production data.
  const download=page.waitForEvent('download');await page.evaluate(data=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));a.download='performance-trace.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);},{traceEvents:events,metadata:summary});await(await download).saveAs('output/playwright/rounded-performance-trace.json');
  return summary;
}
