// Run with the existing Playwright CLI against a local phase2 + lexical server.
async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw new Error('Local server required');
  const root = 'output/playwright/taste-audit-20261021';
  const errors = [], geometry = [];
  page.on('pageerror', e => errors.push(e.message));
  page.setDefaultTimeout(12000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.reload();
  await page.locator('#send:not([disabled])').waitFor();
  await page.locator('#theme-light').click();
  await page.locator('[data-question="校园卡丢了怎么补办？"]').click();
  await page.locator('.answer .conclusion').waitFor();
  if (await page.locator('.answer .conclusion strong').count() === 0) throw new Error('Bold labels missing');
  if ((await page.locator('.answer .conclusion').innerText()).includes('**')) throw new Error('Raw bold markers');
  if (await page.locator('h1').count() !== 1) throw new Error('Stable workspace title missing');
  await page.locator('#thread').evaluate(el => el.scrollTop = 0);
  await page.screenshot({ path: `${root}/after-answer-1440.png` });
  for (const width of [360, 390, 760, 761, 768, 1024, 1279, 1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: width < 761 ? 844 : 900 });
    await page.waitForTimeout(350);
    const g = await page.evaluate(() => {
      const rect = s => { const r = document.querySelector(s).getBoundingClientRect(); return { x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom }; };
      return { width:innerWidth, overflow:document.documentElement.scrollWidth > innerWidth,
        chat:rect('.chat'), map:rect('.mapwrap'), send:rect('#send'),
        radius:getComputedStyle(document.querySelector('.mapwrap')).borderRadius,
        weight:getComputedStyle(document.querySelector('.conclusion')).fontWeight,
        controls:[...document.querySelectorAll('header button,#send,.row-actions button')].map(el=>({name:el.textContent,...(() => {const r=el.getBoundingClientRect();return {width:r.width,height:r.height};})()})) };
    });
    if (g.overflow || g.send.right > width || g.send.bottom > (width < 761 ? 844 : 900)) throw new Error(`Overflow at ${width}: ${JSON.stringify(g)}`);
    if (g.weight !== '400') throw new Error('Body text is bold');
    if (g.radius !== (width <= 760 ? '0px' : '26px')) throw new Error('Map radius changed');
    if (width === 768 && (Math.abs(g.chat.width-360)>1 || Math.abs(g.map.width-360)>1)) throw new Error(`Tablet lanes: ${JSON.stringify(g)}`);
    if (g.controls.some(c=>c.width<44 || c.height<44)) throw new Error(`Small target at ${width}`);
    geometry.push(g);
    if ([390,768].includes(width)) { await page.locator('#thread').evaluate(el=>el.scrollTop=0); await page.screenshot({path:`${root}/after-answer-${width}.png`}); }
  }
  await page.setViewportSize({width:1440,height:900});
  await page.locator('.place-name').first().click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-392)<1);
  if(await page.locator('.place-name').first().getAttribute('aria-pressed')!=='true') throw new Error('Selected place semantics');
  await page.locator('#return-reading').click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-540)<1);
  await page.locator('#thread').evaluate(el=>el.scrollTop=0);
  await page.screenshot({path:`${root}/after-selected-1440.png`});
  await page.locator('#question').focus();
  await page.locator('#desktop-map').click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-392)<1);
  await page.screenshot({path:`${root}/after-map-expanded-1440.png`});
  if ((await page.locator('#context-answer').innerText()).includes('**')) throw new Error('Summary markers');
  await page.locator('#return-reading').click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-540)<1);
  // Reverse while the width tween is in progress.
  await page.locator('#desktop-map').click();
  await page.locator('#return-reading').click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-540)<1);
  await page.locator('#theme-dark').click();
  await page.locator('#thread').evaluate(el=>el.scrollTop=0);
  await page.screenshot({path:`${root}/after-dark-1440.png`});
  const contrast = await page.evaluate(() => {
    const lum = c => { const v=c.match(/[\d.]+/g).slice(0,3).map(Number).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4;});return v[0]*.2126+v[1]*.7152+v[2]*.0722; };
    return ['#send','.place-row .chip.go','.conclusion','.kicker'].map(selector=>{
      const el=document.querySelector(selector),s=getComputedStyle(el);let bg=s.backgroundColor,p=el;
      while(bg==='rgba(0, 0, 0, 0)' && p.parentElement){p=p.parentElement;bg=getComputedStyle(p).backgroundColor;}
      const a=lum(s.color),b=lum(bg);return {selector,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
    });
  });
  if (contrast.some(x=>x.ratio<4.5)) throw new Error(`Low contrast: ${JSON.stringify(contrast)}`);
  await page.locator('#theme-light').click();
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.locator('#desktop-map').click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-392)<1);
  await page.locator('#return-reading').click();
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#sheet-handle').click();
  await page.waitForFunction(()=>document.body.classList.contains('sheet-collapsed'));
  await page.locator('#sheet-handle').click();
  await page.locator('#handling-entry').click();
  await page.locator('.handling-empty').waitFor();
  await page.screenshot({path:`${root}/after-checklist-empty-390.png`});
  if(errors.length) throw new Error(errors.join('\n'));
  return {geometry,contrast,pageErrors:errors.length,mapWidths:[540,392],reversal:true,reducedMotion:true,sheetToggle:true};
}
