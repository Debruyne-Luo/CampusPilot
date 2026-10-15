// Local frontend over the live public backend, in this isolated browser only.
// No server files change. Do not save answer text/cookies or production transcripts.
async (page) => {
  const errors=[];page.on('pageerror',e=>errors.push(e.name));
  const origin='https://cdutdino.pages.dev', local='http://127.0.0.1:8875';
  await page.route(`${origin}/assets/**`,async route=>{
    const u=new URL(route.request().url());
    const path=u.pathname.replace(/^\/assets\/v-[^/]+\//,'/assets/');
    const response=await page.request.get(local+path);
    await route.fulfill({response});
  });
  await page.route(`${origin}/?*`,async route=>{
    const response=await page.request.get(local+'/');await route.fulfill({response});
  });
  await page.setViewportSize({width:1440,height:900});
  await page.goto(origin+'/?desktop-review=1');
  await page.locator('#send:not([disabled])').waitFor();
  await page.locator('#map-frame').waitFor({state:'visible',timeout:20000});
  await page.screenshot({path:'output/playwright/live-map-home-1440.png',animations:'disabled'});
  await page.locator('#question').fill('校园卡丢了怎么补办？');await page.locator('#send').click();
  await page.locator('.handling-add').waitFor({timeout:90000});
  await page.locator('.handling-add').click();
  if(await page.locator('.handling-add').innerText()!=='查看清单')throw new Error('live save failed');
  await page.locator('#handling-entry').click();await page.locator('.handling-row').first().click();
  await page.locator('.handling-primary').click();
  await page.locator('#handling-toast button').click();
  if(await page.locator('.handling-primary').count()!==1)throw new Error('live undo failed');
  // Remove the public test task from this isolated browser again.
  await page.locator('.handling-primary').click();
  await page.locator('#desktop-chat').click();
  await page.locator('.place-row .chip.go').first().click();
  const chooser=page.locator('.origin-select');await chooser.waitFor({timeout:15000});
  const destination=await page.locator('#place-card strong').innerText();
  const options=await chooser.locator('option').evaluateAll(xs=>xs.map(x=>({value:x.value,label:x.textContent})));
  const from=options.find(x=>x.value&&x.label!==destination);if(!from)throw new Error('no origin available');
  await chooser.selectOption(from.value);
  await page.getByRole('button',{name:'开始步行引导',exact:true}).waitFor({timeout:20000});
  // Screenshot contains no production answer transcript: show the empty saved-task panel.
  await page.locator('#handling-entry').click();
  await page.screenshot({path:'output/playwright/live-route-1440.png',animations:'disabled'});
  const result={liveAnswer:true,saveAndUndo:true,route:true,guideModel:'unchanged baseline',pageErrors:errors.length};
  if(errors.length)throw new Error(`page errors: ${errors.join(',')}`);
  return result;
}
