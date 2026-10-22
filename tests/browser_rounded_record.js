// Uses the live answer already verified in the isolated review browser.
// Call with recording active only AFTER installing the redaction stylesheet.
async(page)=>{
  await page.bringToFront();
  if(await page.locator('#return-reading').isVisible()){await page.locator('#return-reading').click();await page.waitForTimeout(400);}
  for(let i=0;i<3&&await page.locator('#handling-panel').isVisible();i++)await page.locator('.handling-back').first().click();
  await page.locator('#thread').evaluate(el=>el.scrollTo({top:0,behavior:'instant'}));await page.waitForTimeout(700);
  const evidence=page.locator('details.citations').last();await evidence.scrollIntoViewIfNeeded();
  if(await evidence.evaluate(el=>el.open)){await evidence.locator(':scope > summary').evaluate(el=>el.click());await page.waitForTimeout(350);}
  await evidence.locator(':scope > summary').evaluate(el=>el.click());await page.waitForTimeout(800);
  await evidence.locator(':scope > summary').evaluate(el=>el.click());await page.waitForTimeout(400);
  await page.locator('.handling-add').click();await page.waitForTimeout(500);
  await page.locator('#handling-entry').click();await page.locator('.handling-row').first().click();await page.waitForTimeout(650);
  const tick=page.locator('.handling-items input').first();if(await tick.count()){await tick.check();await page.waitForTimeout(400);await tick.uncheck();}
  await page.locator('.handling-back').first().click();await page.locator('.handling-back').first().click();
  await page.locator('.place-row .chip.go').first().click();
  if(await page.locator('.origin-select').isVisible()){
    const chooser=page.locator('.origin-select');const options=await chooser.locator('option').evaluateAll(xs=>xs.map(x=>x.value).filter(Boolean));await chooser.selectOption(options[0]);
  }
  await page.getByRole('button',{name:'开始步行引导',exact:true}).waitFor({timeout:20000});await page.waitForTimeout(1000);
  await page.getByRole('button',{name:'换起点',exact:true}).click();await page.waitForTimeout(500);
  const chooser=page.locator('.origin-select');const dest=await page.locator('#place-card strong').innerText();
  const options=await chooser.locator('option').evaluateAll(xs=>xs.map(x=>({value:x.value,label:x.textContent})));const start=options.find(x=>x.value&&x.label!==dest);await chooser.selectOption(start.value);
  await page.getByRole('button',{name:'开始步行引导',exact:true}).waitFor({timeout:20000});await page.waitForTimeout(900);
  await page.locator('#route-overview').click();await page.waitForTimeout(800);
  await page.screenshot({path:'output/playwright/rounded-live-map-1440.png'});
  await page.locator('#return-reading').click();await page.waitForTimeout(700);
  await page.locator('#map-search').fill('图书馆');await page.locator('#search-results button').first().waitFor();await page.waitForTimeout(600);
  await page.locator('#search-results button').first().click();await page.waitForTimeout(1000);
  await page.locator('#return-reading').click();await page.waitForTimeout(500);
  return {recorded:'evidence, checklist, explicit place, real route, origin change, return, settings, search',productionText:'redacted before capture',dino:'not activated'};
}
