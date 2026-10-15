// Run after browser_wayfinding_live.js in the same isolated browser.
// Never serialise production content, map keys, cookies, or response bodies.
async(page)=>{
  const showChat=async()=>{if(await page.locator('#return-reading').isVisible()){await page.locator('#return-reading').click();await page.waitForTimeout(350);}for(let i=0;i<3&&await page.locator('#handling-panel').isVisible();i++)await page.locator('.handling-back').first().click();};
  await page.bringToFront();
  const check=(value,name)=>{if(!value)throw new Error(name);};
  const frame=page.frames().find(f=>f.url().includes('/map-view'));
  const checks=[];
  await showChat();await page.waitForTimeout(400);
  await page.locator('#question').fill('未发送的验证草稿');await page.locator('#question').focus();await page.mouse.move(0,0);
  const cites=page.locator('details.citations').last();
  await cites.evaluate(el=>{el.open=false;el.scrollIntoView({block:'center'});});
  await cites.locator(':scope > summary').evaluate(el=>el.click());await page.waitForTimeout(60);
  await cites.locator(':scope > summary').evaluate(el=>el.click());await page.waitForTimeout(280);
  await page.waitForFunction(()=>{const x=[...document.querySelectorAll('details.citations')].at(-1);return !x.open&&!x.style.height;},{},{timeout:2000});checks.push('disclosure reversal');
  await cites.locator(':scope > summary').evaluate(el=>el.click());await page.waitForTimeout(250);
  const before=await page.locator('#thread').evaluate(el=>el.scrollTop);
  await page.locator('#desktop-map').click();await page.waitForTimeout(80);
  await page.locator('#return-reading').evaluate(el=>el.click());await page.waitForTimeout(350);
  check(Math.abs((await page.locator('.chat').boundingBox()).width-540)<2,'reverse layout width');
  check(Math.abs(await page.locator('#thread').evaluate(el=>el.scrollTop)-before)<3,'reading restored');
  check(await cites.evaluate(el=>el.open),'disclosure retained');
  check(await page.locator('#question').inputValue()==='未发送的验证草稿','draft retained');checks.push('layout reversal, draft, evidence and reading restore');
  await page.locator('#desktop-map').click();await page.waitForTimeout(350);await page.locator('#map-search').press('Escape');
  await page.locator('#route-overview').click();await page.waitForTimeout(500);
  const visible=await frame.evaluate(()=>{
    const [top,bottom,left,right]=avoidEdges(),s=map.getSize();
    return routeGeometry.length>0&&[routeGeometry[0],routeGeometry.at(-1)].every(p=>{const q=map.lngLatToContainer(p);return q.x>=left-3&&q.x<=s.getWidth()-right+3&&q.y>=top-3&&q.y<=s.getHeight()-bottom+3;});
  });check(visible,'route endpoints avoid overlays');checks.push('route endpoints avoid overlays');
  await page.screenshot({path:'output/playwright/rounded-live-map-1440.png',mask:[page.locator('#context-question'),page.locator('#context-answer')],maskColor:'#dbe2e8'});
  const preserved=await frame.evaluate(()=>{window.testCenter=map.getCenter().toArray();window.testZoom=map.getZoom();window.testMarkers=new Map(markerById);return true;});
  await page.locator('#map-search').focus();await page.waitForTimeout(150);
  check(await frame.evaluate(()=>map.getCenter().toArray().every((v,i)=>Math.abs(v-window.testCenter[i])<1e-7)&&map.getZoom()===window.testZoom),'focus camera unchanged');
  await page.locator('#map-search').fill('图书馆');await page.locator('#search-results button').first().waitFor();
  await page.locator('#search-results button').first().click();await page.waitForTimeout(100);
  await page.locator('#map-search').fill('餐厅');await page.locator('#search-results button').first().waitFor();
  const lastLabel=await page.locator('#search-results button b').first().innerText();
  await page.locator('#search-results button').first().click();await page.waitForTimeout(500);
  check(await page.locator('#place-card strong').innerText()===lastLabel,'latest selected place');
  check(await frame.evaluate(()=>[...window.testMarkers].filter(([id])=>markerById.has(id)).every(([id,m])=>markerById.get(id)===m)),'marker identity stable');checks.push('search focus stable, latest selection, marker reuse');
  // An actual pointer drag during a camera move must cancel automatic ownership.
  await page.locator('#route-overview').click();await page.waitForTimeout(70);
  const box=await page.locator('#map-frame').boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.4);await page.mouse.down();
  await page.mouse.move(box.x+box.width*.6,box.y+box.height*.48,{steps:8});await page.mouse.up();await page.waitForTimeout(500);
  check(await frame.evaluate(()=>cameraMode==='manual'),'drag cancels camera');
  await frame.evaluate(()=>{window.testCenter=map.getCenter().toArray();window.testZoom=map.getZoom();});
  await page.evaluate(()=>window.sendToMap({action:'places',places:[]}));await page.waitForTimeout(300);
  check(await frame.evaluate(()=>map.getCenter().toArray().every((v,i)=>Math.abs(v-window.testCenter[i])<1e-7)&&map.getZoom()===window.testZoom),'data cannot take manual camera');checks.push('drag interrupts camera; new data keeps manual view');
  await page.locator('#desktop-settings').click();await page.locator('#reduce-motion').check();await page.keyboard.press('Escape');
  await page.locator('#return-reading').click();
  check(Math.abs((await page.locator('.chat').boundingBox()).width-540)<2,'reduced motion instant');
  check(await frame.evaluate(()=>reduceMotion===true),'reduced motion camera');
  await page.locator('#desktop-settings').click();await page.locator('#reduce-motion').uncheck();await page.keyboard.press('Escape');
  await page.locator('#desktop-settings').focus();await page.keyboard.press('Enter');check(await page.locator('#reading-settings').isVisible(),'keyboard settings');await page.keyboard.press('Escape');
  check(await page.locator('#desktop-settings').evaluate(el=>el===document.activeElement),'dialog focus returned');checks.push('reduced motion and keyboard focus');
  await page.locator('#question').fill('');
  return {passed:true,checks,browser:await page.context().browser().version()};
}
